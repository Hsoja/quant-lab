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
from calc.montecarlo import compute_return_stats  # noqa: E402
from calc.valuation import compute_valuation  # noqa: E402
from extract.facts import Citation, CitedValue, extract_core_facts  # noqa: E402
from ingest.edgar import download_filing, get_cik, list_10k_filings, save_filing, sha256_hex  # noqa: E402
from ingest.price import fetch_price_chart, parse_daily_closes, parse_latest_price  # noqa: E402
from verify.verifier import verify_all  # noqa: E402

TICKERS = ["SPGI", "COST", "AAPL", "UBER"]

# Bolsa de cada ticker, para el símbolo de TradingView (ver SPEC.md 9.7). Se
# documenta a mano porque son solo 4 tickers conocidos — no se auto-detecta.
_EXCHANGE_BY_TICKER = {"SPGI": "NYSE", "COST": "NASDAQ", "AAPL": "NASDAQ", "UBER": "NYSE"}

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


def _fmt_usd(value: float | None) -> str:
    return f"US$ {value:,.0f}" if value is not None else "no verificado"


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.2f}%" if value is not None else "no verificado"


def _riesgo_especifico(verified: dict, fcf) -> str:
    """Una observación de riesgo grounded en las cifras reales — nunca un
    texto genérico de relleno. Revisa primero las trampas más informativas
    (la misma lógica que el manual de inversión: un solo número nunca basta)."""
    net_income = verified["net_income"].value
    ebitda = verified["ebitda"].value
    wk = verified["working_capital_change"]
    capex = verified["capex"].value

    if net_income is not None and ebitda is not None and ebitda > 0 and net_income > ebitda * 1.3:
        return (
            f"Ojo con esta: la utilidad neta ({_fmt_usd(net_income)}) es más alta que el EBITDA "
            f"({_fmt_usd(ebitda)}). Eso suele significar que hay una ganancia que no es del negocio "
            "normal (un ajuste contable, una venta de activos, algo que no se repite), no solo más "
            "ventas — la misma trampa de mirar un solo número de un solo vistazo. Vale la pena revisar "
            'la nota de "otros ingresos" del reporte antes de confiar en el P/E tal cual sale aquí.'
        )
    if wk.no_verificado:
        return (
            "La variación de capital de trabajo sale \"no verificado\" en este reporte (no publica una "
            "línea agregada), así que el flujo de caja libre tampoco se pudo calcular — es una limitación "
            "real de los datos disponibles, no un juicio sobre la empresa. El siguiente paso para completar "
            "esta tesis sería revisar el estado de flujo de efectivo completo del 10-K."
        )
    if fcf.value is not None and capex is not None and capex > fcf.value * 0.8:
        return (
            f"El CAPEX ({_fmt_usd(capex)}) es grande frente al FCF ({_fmt_usd(fcf.value)}) — una empresa "
            "que está invirtiendo mucho en expandirse. Vale la pena vigilar que ese ritmo de inversión no "
            "empiece a crecer más rápido que las ventas (una de las señales de alerta del manual de "
            "inversión: inversión que crece más rápido que las ventas)."
        )
    return (
        "No se detectó, con las cifras ya citadas, ninguna señal mecánica obvia como las de arriba — pero "
        "eso no significa que no haya riesgo: esta prueba no revisa el sector, la competencia ni las 7 "
        "señales de alerta completas del manual de inversión."
    )


def build_qa(verified: dict, fcf, cagr, valuation) -> list[dict]:
    """Preguntas y respuestas ya preparadas para el apartado de chat
    (SPEC.md sección 9.6): nunca una llamada en vivo al LLM, pero cada
    número que aparece sale de las mismas cifras ya verificadas de arriba —
    nunca un texto de relleno con números inventados."""
    revenue = verified["revenue"]
    qa = []

    if cagr.value is not None:
        crecimiento = (
            f"Los ingresos del periodo más reciente fueron de {_fmt_usd(revenue.value)}. El CAGR de "
            f"ingresos entre {cagr.inicio.period_end} y {cagr.fin.period_end} ({cagr.years:.2f} años, los "
            f"que trae citados este mismo reporte) fue de {_fmt_pct(cagr.value)}."
        )
    else:
        crecimiento = f"Los ingresos del periodo más reciente fueron de {_fmt_usd(revenue.value)}. El crecimiento (CAGR) sale \"no verificado\": {cagr.nota}"
    qa.append({"pregunta": "¿Cómo le fue en ingresos y crecimiento?", "respuesta": crecimiento})

    if valuation.price is not None:
        pe_text = f"{valuation.pe:.1f}" if valuation.pe is not None else "no verificado"
        fcfy_text = _fmt_pct(valuation.fcf_yield)
        valoracion = (
            f"Con el precio de cierre del {valuation.price_as_of} (US$ {valuation.price:.2f}), el P/E sale "
            f"en {pe_text} y el FCF yield en {fcfy_text}. Con los dos umbrales fijos de esta prueba (P/E ≤ 20 "
            'o FCF yield ≥ 5% para "barata"; P/E ≥ 30 o FCF yield < 2% para "cara"), queda marcada '
            f'"{valuation.veredicto}". Es una lectura mecánica y simple, no la metodología completa del '
            "manual de inversión."
        )
    else:
        valoracion = "No se pudo obtener el precio de la fuente no oficial en este momento (no verificado)."
    qa.append({"pregunta": "¿Qué tan cara o barata se ve con los números simples?", "respuesta": valoracion})

    qa.append({
        "pregunta": "¿Cuál es el principal riesgo o qué la invalidaría?",
        "respuesta": _riesgo_especifico(verified, fcf),
    })
    return qa


def build_monte_carlo(ticker: str, price: float | None, price_as_of: str | None) -> dict | None:
    """μ y σ históricos para la simulación (Capa B, SIMULADO). None si la
    fuente falla o hay pocos datos: la página entonces pide supuestos
    manuales marcados "no verificado" — nunca se inventan."""
    if price is None:
        return None
    try:
        raw = fetch_price_chart(ticker, history=True)
        closes = parse_daily_closes(raw)
    except Exception as exc:
        print(f"  historial no disponible para {ticker}: {exc}", file=sys.stderr)
        return None
    stats = compute_return_stats(closes) if closes else None
    if stats is None:
        return None
    return {
        "s0": price,
        "as_of": price_as_of,
        "mu": stats.mu,
        "sigma": stats.sigma,
        "n_obs": stats.n_obs,
        "source": "Yahoo Finance, cierres diarios ~3 años (fuente no oficial)",
        "source_hash": sha256_hex(raw),
    }


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

    monte_carlo = build_monte_carlo(ticker, price_value, price_as_of)

    valuation = compute_valuation(
        eps=verified["eps"], diluted_shares=verified["diluted_shares"], fcf_value=fcf.value,
        price=price_value, price_citation=price_citation, price_as_of=price_as_of,
    )
    qa = build_qa(verified, fcf, cagr, valuation)
    revenue_series = [
        {"period_end": cv.period_end, "value": cv.value}
        for cv in verified["revenue_series"]
        if cv.value is not None
    ]

    return {
        "ticker": ticker,
        "tradingview_symbol": f"{_EXCHANGE_BY_TICKER[ticker]}:{ticker}",
        "filing_doc_id": filing.doc_id,
        "report_date": filing.report_date,
        "figures": {key: _cv_summary(verified[key]) for key, _label in _FIGURE_KEYS},
        "revenue_series": revenue_series,
        "qa": qa,
        "monte_carlo": monte_carlo,
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
