"""Precio de cierre de una acción — fuente NO oficial (ver SPEC.md sección 9).

SEC EDGAR no trae precios de mercado, solo lo que la empresa reporta. Para el
apartado experimental "Pruébalo con una acción" se usa el endpoint de
gráficas de Yahoo Finance, ampliamente usado por la comunidad pero sin
documentación pública ni soporte oficial: puede cambiar o dejar de
funcionar sin aviso. Si falla, el precio sale "no verificado" — nunca se
inventa ni se usa un valor de respaldo.

Mismas reglas que ingest/edgar.py: solo https, límite de tasa, reintento con
backoff, y el documento crudo se guarda con su hash para que una cita sobre
el precio se pueda verificar después exactamente igual que una cita del
10-K (reusa Citation y verify_citation sin cambios).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
HISTORY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=3y"
_TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 2
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_USER_AGENT = "QuantLab-MVP (research tool; no oficial, ver SPEC.md 9)"


class PriceAccessError(Exception):
    """El acceso a la fuente de precio falló de forma que no se debe simular."""


class _RateLimiter:
    def __init__(self, min_interval: float = MIN_SECONDS_BETWEEN_REQUESTS) -> None:
        self._min_interval = min_interval
        self._last_call: float | None = None

    def wait(self) -> None:
        if self._last_call is not None:
            remaining = self._min_interval - (time.monotonic() - self._last_call)
            if remaining > 0:
                time.sleep(remaining)
        self._last_call = time.monotonic()


_rate_limiter = _RateLimiter()


def fetch_price_chart(ticker: str, *, history: bool = False) -> bytes:
    """Descarga la respuesta cruda (JSON) del endpoint de gráficas.
    history=True pide ~3 años de cierres diarios (para μ/σ de la simulación)."""
    symbol = ticker.strip().upper()
    if not _TICKER_PATTERN.match(symbol):
        raise PriceAccessError(f"Ticker no válido: {ticker!r}")
    url = (HISTORY_URL if history else CHART_URL).format(ticker=symbol)
    if not url.startswith("https://"):
        raise PriceAccessError(f"Esquema de URL no permitido: {url}")
    headers = {"User-Agent": _USER_AGENT}
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        _rate_limiter.wait()
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise PriceAccessError(f"Respuesta más grande que el tope permitido: {url}")
                return content
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise PriceAccessError(f"La fuente de precio respondió {exc.code} para {ticker}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise PriceAccessError(f"No se pudo contactar la fuente de precio para {ticker}: {exc}") from exc
    raise PriceAccessError(f"Falló la descarga del precio de {ticker}") from last_error


@dataclass(frozen=True)
class PricePoint:
    price: float
    currency: str
    as_of: str  # fecha ISO (UTC) del último cierre disponible
    frase_exacta: str  # porción literal de la respuesta cruda, para citar


def parse_latest_price(raw: bytes) -> PricePoint | None:
    """Extrae el último precio de la respuesta cruda. None si no se pudo
    interpretar — quien llama debe tratarlo como "no verificado", nunca
    inventar un número."""
    text = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
        meta = data["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        currency = str(meta.get("currency", "USD"))
        timestamp = int(meta["regularMarketTime"])
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None

    key_index = text.find('"regularMarketPrice":')
    if key_index == -1:
        return None
    end_index = text.find(",", key_index)
    if end_index == -1:
        end_index = text.find("}", key_index)
    if end_index == -1:
        return None
    frase_exacta = text[key_index:end_index]

    as_of = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    return PricePoint(price=price, currency=currency, as_of=as_of, frase_exacta=frase_exacta)


def parse_daily_closes(raw: bytes) -> list[float] | None:
    """Cierres diarios (en orden) de la respuesta cruda. None si no se pudo
    interpretar. Los días sin cierre (null) se descartan; nunca se rellenan
    ni se interpolan."""
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(closes, list) or not closes:
        return None
    try:
        values = [float(c) for c in closes if c is not None]
    except (TypeError, ValueError):
        return None
    # Yahoo a veces trae días sin cierre (null): se descartan, no se inventan.
    return values or None
