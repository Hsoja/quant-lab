"""Fase 3: FCF (versión simplificada del MVP) y CAGR de ingresos.

Solo hace aritmética sobre los `CitedValue` que entrega `extract/` — nunca
vuelve a tocar el documento ni EDGAR. Fórmulas: SPEC.md secciones 4.5 y 4.6.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from extract.facts import CitedValue


@dataclass(frozen=True)
class FcfResult:
    value: float | None
    componentes_no_verificados: list[str]
    nota: str


def compute_fcf(facts: dict[str, object]) -> FcfResult:
    """FCF = EBITDA (derivado) − Impuestos (gasto, devengado) − CAPEX − ΔWK."""
    ebitda: CitedValue = facts["ebitda"]
    taxes: CitedValue = facts["income_tax_expense"]
    capex: CitedValue = facts["capex"]
    wk: CitedValue = facts["working_capital_change"]

    missing = [f.label for f in (ebitda, taxes, capex, wk) if f.value is None]
    if missing:
        return FcfResult(
            value=None,
            componentes_no_verificados=missing,
            nota=(
                "FCF no se calcula: falta(n) " + ", ".join(missing) + " (no verificado). "
                "No se rellena con 0 ni con un supuesto."
            ),
        )
    value = ebitda.value - taxes.value - capex.value - wk.value
    return FcfResult(
        value=value,
        componentes_no_verificados=[],
        nota="FCF = EBITDA (derivado) − impuestos (devengado) − CAPEX − ΔWK.",
    )


@dataclass(frozen=True)
class CagrResult:
    value: float | None
    years: float | None
    inicio: CitedValue | None
    fin: CitedValue | None
    nota: str


def _years_between(start_iso: str, end_iso: str) -> float:
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    return (end - start).days / 365.25


def compute_revenue_cagr(revenue_series: list[CitedValue]) -> CagrResult:
    """CAGR = (ingreso_final / ingreso_inicial) ** (1/años) − 1.

    Usa las columnas de año comparativas que ya vienen citadas dentro del
    mismo filing (ver extract/facts.py); no descarga ni asume nada nuevo.
    """
    disponibles = [cv for cv in revenue_series if cv.value is not None and cv.period_end]
    if len(disponibles) < 2:
        return CagrResult(
            value=None, years=None, inicio=None, fin=None,
            nota="No hay al menos 2 años de ingresos citados en este filing (no verificado).",
        )
    inicio = min(disponibles, key=lambda cv: cv.period_end)
    fin = max(disponibles, key=lambda cv: cv.period_end)
    years = _years_between(inicio.period_end, fin.period_end)
    if inicio.value <= 0 or years <= 0:
        return CagrResult(
            value=None, years=years, inicio=inicio, fin=fin,
            nota="Ingreso inicial o número de años inválido para calcular CAGR.",
        )
    value = (fin.value / inicio.value) ** (1 / years) - 1
    return CagrResult(
        value=value, years=years, inicio=inicio, fin=fin,
        nota=f"CAGR de ingresos entre {inicio.period_end} y {fin.period_end} ({years:.2f} años).",
    )
