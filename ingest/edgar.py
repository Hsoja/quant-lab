"""Descarga de reportes 10-K desde SEC EDGAR, con hash del documento guardado.

Reglas (ver SPEC.md secciones 3 y 7):
- User-Agent con contacto obligatorio (EDGAR_CONTACT), nunca hardcodeado.
- 1 solicitud/segundo, con reintento y backoff si la SEC responde 429 o 5xx.
- El documento descargado es el HTML con iXBRL en línea: de ahí sale cada
  "frase_exacta" de una cita, nunca de un resumen.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
COMPANY_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{concept}.json"

REQUEST_TIMEOUT_SECONDS = 30
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024  # tope de tamaño: evita agotar memoria/disco
MIN_SECONDS_BETWEEN_REQUESTS = 1.0  # conservador frente al límite de la SEC (~10/s)
MAX_RETRIES = 3


class EdgarAccessError(Exception):
    """El acceso a EDGAR falló de forma que no se debe simular ni inventar."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class FilingRef:
    cik: str  # 10 dígitos, con ceros a la izquierda
    accession_number: str  # con guiones, ej. 0000064040-26-000013
    filing_date: str
    report_date: str  # fin del periodo que cubre el reporte, ej. 2025-12-31
    primary_document: str

    @property
    def accession_no_dashes(self) -> str:
        return self.accession_number.replace("-", "")

    @property
    def document_url(self) -> str:
        return (
            f"{ARCHIVES_BASE}/{int(self.cik)}/{self.accession_no_dashes}/"
            f"{self.primary_document}"
        )

    @property
    def doc_id(self) -> str:
        return f"CIK{self.cik}-{self.accession_number}"


def _user_agent() -> str:
    contact = os.environ.get("EDGAR_CONTACT", "").strip()
    if not contact:
        raise EdgarAccessError(
            "Falta EDGAR_CONTACT en el entorno (.env). La SEC exige un User-Agent "
            "con contacto identificable; no se inventa uno."
        )
    return f"QuantLab-MVP {contact}"


class _RateLimiter:
    def __init__(self, min_interval: float = MIN_SECONDS_BETWEEN_REQUESTS) -> None:
        self._min_interval = min_interval
        self._last_call: float | None = None

    def wait(self) -> None:
        if self._last_call is not None:
            elapsed = time.monotonic() - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_call = time.monotonic()


_rate_limiter = _RateLimiter()


def _get(url: str) -> bytes:
    """GET con User-Agent obligatorio, límite de tasa y reintento con backoff."""
    headers = {"User-Agent": _user_agent()}
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        _rate_limiter.wait()
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                content = response.read(MAX_DOCUMENT_BYTES + 1)
                if len(content) > MAX_DOCUMENT_BYTES:
                    raise EdgarAccessError(
                        f"Documento más grande que el tope permitido ({MAX_DOCUMENT_BYTES} bytes): {url}"
                    )
                return content
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise EdgarAccessError(f"EDGAR respondió {exc.code} para {url}", status_code=exc.code) from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise EdgarAccessError(f"No se pudo contactar a EDGAR ({url}): {exc}") from exc
    raise EdgarAccessError(f"Falló la descarga de {url}") from last_error


def get_cik(ticker: str) -> str:
    """Devuelve el CIK (10 dígitos, con ceros) de un ticker, o levanta EdgarAccessError."""
    data = json.loads(_get(TICKERS_URL).decode("utf-8"))
    ticker_upper = ticker.strip().upper()
    for entry in data.values():
        if entry.get("ticker") == ticker_upper:
            return f"{int(entry['cik_str']):010d}"
    raise EdgarAccessError(f"Ticker no encontrado en EDGAR: {ticker}")


def list_10k_filings(cik: str, limit: int = 5) -> list[FilingRef]:
    """Lista los 10-K más recientes de una empresa, más nuevo primero."""
    url = SUBMISSIONS_URL.format(cik10=cik)
    data = json.loads(_get(url).decode("utf-8"))
    recent = data["filings"]["recent"]
    forms = recent["form"]
    results: list[FilingRef] = []
    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        results.append(
            FilingRef(
                cik=cik,
                accession_number=recent["accessionNumber"][i],
                filing_date=recent["filingDate"][i],
                report_date=recent["reportDate"][i],
                primary_document=recent["primaryDocument"][i],
            )
        )
        if len(results) >= limit:
            break
    return results


@dataclass(frozen=True)
class ConceptPeriod:
    start: str | None
    end: str
    value: float


def company_concept_periods_for_filing(
    cik: str, concept: str, accession_number: str
) -> list[ConceptPeriod]:
    """Todas las columnas de año (start, end, val) de un concepto us-gaap que
    aparecen etiquetadas dentro de un filing exacto (un 10-K normalmente
    muestra 2-3 años comparativos de cada estado financiero).

    Es solo una AYUDA INTERNA (ver SPEC.md sección 3): sirve para saber qué
    cifra y qué periodo buscar dentro del HTML con iXBRL. Nunca es la fuente
    de una cita. Devuelve [] si el filing no reporta ese concepto (no se
    inventa un valor).
    """
    url = COMPANY_CONCEPT_URL.format(cik10=cik, concept=concept)
    try:
        data = json.loads(_get(url).decode("utf-8"))
    except EdgarAccessError as exc:
        if exc.status_code == 404:
            return []  # la empresa no reporta este concepto: no es una falla
        raise  # cualquier otra falla (red, 5xx) se propaga; no se disfraza de "no reportado"
    periods = [
        ConceptPeriod(start=entry.get("start"), end=entry["end"], value=float(entry["val"]))
        for unit_values in data.get("units", {}).values()
        for entry in unit_values
        if entry.get("accn") == accession_number
    ]
    # Sin duplicados (un mismo periodo puede repetirse entre unidades/formularios).
    seen: set[tuple[str | None, str, float]] = set()
    unique: list[ConceptPeriod] = []
    for p in periods:
        key = (p.start, p.end, p.value)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def company_concept_fy_value(cik: str, concept: str, filing: FilingRef) -> float | None:
    """Valor oficial (en USD) de un concepto us-gaap para el año que cubre el
    filing (su `report_date`), o None si no se reporta."""
    for period in company_concept_periods_for_filing(cik, concept, filing.accession_number):
        if period.end == filing.report_date:
            return period.value
    return None


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def download_filing(filing: FilingRef) -> bytes:
    """Descarga el HTML con iXBRL en línea del filing dado."""
    return _get(filing.document_url)


def save_filing(content: bytes, dest_path: str) -> str:
    """Guarda el documento tal cual se descargó y devuelve su hash SHA-256."""
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(content)
    return sha256_hex(content)
