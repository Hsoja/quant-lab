"""Genera examples/companies.json: el conjunto de empresas precalculadas
para el apartado "Pruébalo con una acción" (SPEC.md sección 9).

Se corre a mano (no es parte del CLI normal de cada usuario): descarga de
verdad de EDGAR y de la fuente de precio, con los mismos límites de tasa de
siempre. El resultado es un JSON con datos públicos de unas pocas empresas
de ejemplo, ya extraídos, verificados y con su valoración experimental —
eso es lo que la página estática embebe; nunca hay una llamada en vivo
desde el navegador.

    python scripts/precompute_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from calc.fcf import compute_fcf, compute_revenue_cagr  # noqa: E402
from calc.valuation import compute_valuation  # noqa: E402
from extract.facts import Citation, CitedValue, extract_core_facts  # noqa: E402
from ingest.edgar import download_filing, get_cik, list_10k_filings, save_filing, sha256_hex  # noqa: E402
from ingest.price import fetch_price_chart, parse_latest_price  # noqa: E402
from verify.verifier import verify_all  # noqa: E402

TICKERS = ["SPGI", "COST", "AAPL", "UBER"]

_FIGURE_KEYS = (
    ("revenue", "Ingresos"),
    ("operating_income", "Utilidad operativa"),
    ("ebitda", "EBITDA (derivado)"),
    ("net_income", "Utilidad neta"),
    ("capex", "CAPEX"),
    ("working_capital_change", "Variación de capital de trabajo"),
)


def _cv_summary(cv: CitedValue) -> dict:
    return {
        "label": cv.label,
        "value": cv.value,
        "derivado": cv.derivado,
        "no_verificado": cv.no_verificado,
        "nota": cv.nota or None,
        "citation": (
            {"doc_id": cv.citation.doc_id, "seccion": cv.citation.seccion, "frase_exacta": cv.citation.frase_exacta}
            if cv.citation
            else None
        ),
    }


def _citation_summary(citation: Citation | None) -> dict | None:
    if citation is None:
        return None
    return {"doc_id": citation.doc_id, "seccion": citation.seccion, "frase_exacta": citation.frase_exacta}


def build_company(ticker: str) -> dict:
    cik = get_cik(ticker)
    filing = list_10k_filings(cik, limit=1)[0]
    content = download_filing(filing)
    doc_hash = save_filing(content, f"data/raw/{ticker.lower()}_{filing.accession_no_dashes}.htm")
    html_text = content.decode("utf-8", errors="replace")

    facts = extract_core_facts(cik=cik, filing=filing, html_text=html_text, doc_hash=doc_hash)
    verified = verify_all(facts, content)
    fcf = compute_fcf(verified)
    cagr = compute_revenue_cagr(verified["revenue_series"])

    price_value = price_as_of = None
    price_citation = None
    try:
        raw_price = fetch_price_chart(ticker)
        point = parse_latest_price(raw_price)
        if point is not None:
            price_value, price_as_of = point.price, point.as_of
            price_citation = Citation(
                doc_id=f"YAHOO-CHART:{ticker}",
                seccion=f"Cotización de cierre, {point.as_of} (Yahoo Finance, fuente no oficial)",
                frase_exacta=point.frase_exacta,
                hash=sha256_hex(raw_price),
            )
    except Exception as exc:  # no se simula un precio si la fuente falla
        print(f"  precio no disponible para {ticker}: {exc}", file=sys.stderr)

    valuation = compute_valuation(
        eps=verified["eps"], diluted_shares=verified["diluted_shares"], fcf_value=fcf.value,
        price=price_value, price_citation=price_citation, price_as_of=price_as_of,
    )

    return {
        "ticker": ticker,
        "filing_doc_id": filing.doc_id,
        "report_date": filing.report_date,
        "figures": {key: _cv_summary(verified[key]) for key, _label in _FIGURE_KEYS},
        "fcf": {"value": fcf.value, "nota": fcf.nota},
        "cagr": {"value": cagr.value, "nota": cagr.nota},
        "valuation": {
            "price": valuation.price,
            "price_as_of": valuation.price_as_of,
            "price_citation": _citation_summary(valuation.price_citation),
            "pe": valuation.pe,
            "fcf_yield": valuation.fcf_yield,
            "market_cap": valuation.market_cap,
            "veredicto": valuation.veredicto,
            "nota": valuation.nota,
        },
    }


def main() -> None:
    load_dotenv()
    out: dict[str, dict] = {}
    for ticker in TICKERS:
        print(f"Procesando {ticker}...", file=sys.stderr)
        out[ticker] = build_company(ticker)
    dest = Path(__file__).resolve().parent.parent / "examples" / "companies.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {dest}")


if __name__ == "__main__":
    main()
