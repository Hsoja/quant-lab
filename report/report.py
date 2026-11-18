"""Fase 6: reporte final en Markdown.

Orden fijo (SPEC.md reglas 1, 6 y 8): riesgo y limitaciones primero, luego
las cifras con su fuente ("no verificado" donde falte), luego los cálculos
y el resumen de cambios si existe, y siempre el pie de no asesoría. Nunca
dice "compra" ni "vende" (regla 4): solo describe lo que dice el documento.
"""

from __future__ import annotations

from calc.fcf import CagrResult, FcfResult
from extract.facts import CitedValue

DISCLAIMER = "**Análisis informativo, no asesoría financiera.**"

_DISPLAY_ORDER = (
    ("revenue", "Ingresos"),
    ("operating_income", "Utilidad operativa"),
    ("depreciation_amortization", "Depreciación y amortización"),
    ("ebitda", "EBITDA (derivado)"),
    ("income_tax_expense", "Gasto por impuestos (devengado)"),
    ("income_tax_paid", "Impuestos pagados en efectivo (referencia)"),
    ("capex", "CAPEX"),
    ("working_capital_change", "Variación de capital de trabajo"),
)


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "no verificado"
    return f"US$ {value:,.0f}"


def _risk_section(verified: dict, fcf: FcfResult) -> str:
    sin_cita = [label for key, label in _DISPLAY_ORDER if verified[key].no_verificado]
    lines = ["## ⚠️ Riesgo y limitaciones (léase primero)", ""]
    if sin_cita:
        lines.append(
            "Estas cifras **no se pudieron verificar** con una cita en el documento y no se "
            "usaron en ningún cálculo:"
        )
        for label in sin_cita:
            lines.append(f"- {label}")
    else:
        lines.append("Todas las cifras de este reporte tienen una cita verificada contra el documento original.")
    if fcf.value is None:
        lines.append("")
        lines.append(f"**El FCF no se pudo calcular:** {fcf.nota}")
    lines.append("")
    lines.append(
        "Este reporte describe lo que dice el documento oficial citado abajo; no es una tesis "
        "de inversión completa (no trae argumento en contra ni señales de alerta de un "
        "portafolio) y no sustituye leer el reporte completo."
    )
    return "\n".join(lines)


def _figures_section(verified: dict) -> str:
    lines = ["## 📊 Cifras con fuente", "", "| Concepto | Valor | Cita |", "| --- | --- | --- |"]
    for key, label in _DISPLAY_ORDER:
        cv: CitedValue = verified[key]
        if cv.no_verificado:
            cita = "no verificado" + (f" — {cv.nota}" if cv.nota else "")
        elif cv.derivado:
            cita = "derivado (ver componentes de esta misma tabla)"
        else:
            cita = f"{cv.citation.doc_id}, {cv.citation.seccion}: “{cv.citation.frase_exacta}”"
        lines.append(f"| {label} | {_fmt_money(cv.value)} | {cita} |")
    return "\n".join(lines)


def _calc_section(fcf: FcfResult, cagr: CagrResult) -> str:
    lines = ["## 🧮 Cálculos", ""]
    lines.append(f"- **FCF:** {_fmt_money(fcf.value)} — {fcf.nota}")
    if cagr.value is not None:
        lines.append(f"- **CAGR de ingresos:** {cagr.value:+.2%} — {cagr.nota}")
    else:
        lines.append(f"- **CAGR de ingresos:** no verificado — {cagr.nota}")
    return "\n".join(lines)


def build_report(
    *,
    empresa_ejemplo: str,
    filing_doc_id: str,
    verified: dict,
    fcf: FcfResult,
    cagr: CagrResult,
    resumen_cambios: str | None = None,
) -> str:
    parts = [
        f"# Reporte — {empresa_ejemplo} ({filing_doc_id})",
        "",
        _risk_section(verified, fcf),
        "",
        _figures_section(verified),
        "",
        _calc_section(fcf, cagr),
        "",
    ]
    if resumen_cambios:
        parts += ["## 📝 Resumen de cambios", "", resumen_cambios, ""]
    parts.append(DISCLAIMER)
    return "\n".join(parts)
