"""Valoración simple — EXPERIMENTAL (ver SPEC.md sección 9).

Calcula P/E y FCF yield usando el precio de Yahoo Finance (fuente no
oficial, ingest/price.py) y las cifras ya verificadas de extract/. Da una
lectura mecánica de "barata / cara / neutral" con dos umbrales fijos — NO es
la metodología completa del manual de inversión (sin comparación sectorial,
sin las 7 señales de alerta, sin PEG, sin considerar el crecimiento). Por
eso se marca como prueba en todo el reporte y nunca se usa para decir
"compra" o "vende" (regla no negociable del proyecto, igual que todo lo
demás).

Solo hace aritmética sobre los valores ya extraídos/citados — nunca vuelve
a tocar el documento ni la red.
"""

from __future__ import annotations

from dataclasses import dataclass

from extract.facts import Citation, CitedValue

# Umbrales fijos y simples, a propósito (nada de comparación sectorial):
PE_BARATA_MAX = 20.0
PE_CARA_MIN = 30.0
FCF_YIELD_BARATA_MIN = 0.05
FCF_YIELD_CARA_MAX = 0.02

NOTA_LIMITACION = (
    "Lectura automática simple (P/E y FCF yield con dos umbrales fijos): no es la "
    "metodología completa del manual de inversión (sin comparación sectorial, sin "
    "señales de alerta, sin considerar el crecimiento). Es una prueba — no te bases "
    "en esto para decidir."
)


@dataclass(frozen=True)
class ValuationResult:
    price: float | None
    price_citation: Citation | None
    price_as_of: str | None
    pe: float | None
    fcf_yield: float | None
    market_cap: float | None
    veredicto: str  # "barata" | "cara" | "neutral" | "no verificado"
    nota: str


def _señal_pe(pe: float) -> str:
    if pe <= PE_BARATA_MAX:
        return "barata"
    if pe >= PE_CARA_MIN:
        return "cara"
    return "neutral"


def _señal_fcf_yield(fcf_yield: float) -> str:
    if fcf_yield >= FCF_YIELD_BARATA_MIN:
        return "barata"
    if fcf_yield < FCF_YIELD_CARA_MAX:
        return "cara"
    return "neutral"


def compute_valuation(
    *,
    eps: CitedValue,
    diluted_shares: CitedValue,
    fcf_value: float | None,
    price: float | None,
    price_citation: Citation | None,
    price_as_of: str | None,
) -> ValuationResult:
    if price is None or price_citation is None:
        return ValuationResult(
            price=None, price_citation=None, price_as_of=None, pe=None, fcf_yield=None,
            market_cap=None, veredicto="no verificado",
            nota="No se pudo obtener el precio de la fuente no oficial (no verificado). " + NOTA_LIMITACION,
        )

    pe = price / eps.value if (eps.value is not None and eps.value > 0) else None
    market_cap = (
        price * diluted_shares.value if diluted_shares.value not in (None, 0) else None
    )
    fcf_yield = (
        fcf_value / market_cap if (fcf_value is not None and market_cap not in (None, 0)) else None
    )

    señales = []
    if pe is not None:
        señales.append(_señal_pe(pe))
    if fcf_yield is not None:
        señales.append(_señal_fcf_yield(fcf_yield))

    if not señales:
        veredicto = "no verificado"
    elif all(s == "barata" for s in señales):
        veredicto = "barata"
    elif all(s == "cara" for s in señales):
        veredicto = "cara"
    else:
        veredicto = "neutral"

    return ValuationResult(
        price=price, price_citation=price_citation, price_as_of=price_as_of,
        pe=pe, fcf_yield=fcf_yield, market_cap=market_cap, veredicto=veredicto,
        nota=NOTA_LIMITACION,
    )
