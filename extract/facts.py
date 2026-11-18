"""Fase 2: EBITDA (derivado), impuestos, CAPEX, ingresos y variación de
capital de trabajo — cada cifra con su cita `{doc_id, sección, frase_exacta,
hash}`. Las decisiones de cálculo están fijas en SPEC.md sección 4; este
módulo solo las ejecuta, nunca las decide de nuevo caso por caso.

La API `companyconcept` de EDGAR (vía `ingest.edgar`) se usa solo para saber
qué valor y qué periodo buscar; la cita siempre sale de parsear el mismo HTML
guardado (`extract.ixbrl`), nunca de esa API.
"""

from __future__ import annotations

from dataclasses import dataclass

from ingest.edgar import FilingRef, company_concept_fy_value, company_concept_periods_for_filing

from . import ixbrl

CONTEXT_WINDOW_CHARS = 160
VALUE_MATCH_TOLERANCE = 1.0  # dólares; el escalado de iXBRL debería dar un match casi exacto


@dataclass(frozen=True)
class Citation:
    doc_id: str
    seccion: str
    frase_exacta: str
    hash: str


@dataclass(frozen=True)
class CitedValue:
    concept: str
    label: str
    value: float | None
    citation: Citation | None
    derivado: bool = False
    nota: str = ""
    period_end: str | None = None  # para series de varios años (ver revenue_series)

    @property
    def no_verificado(self) -> bool:
        """True si no hay con qué confiar en este número.

        Un valor "derivado" (ej. EBITDA) nunca tiene cita propia a propósito
        — se apoya en sus componentes, que ya están citados por separado —
        así que solo cuenta como "no verificado" si ni siquiera se pudo
        calcular (value is None). Para el resto, falta la cita SÍ importa.
        """
        if self.derivado:
            return self.value is None
        return self.value is None or self.citation is None


# (nombre interno, tag us-gaap, etiqueta humana, sección para la cita)
_SIMPLE_CONCEPTS = {
    "operating_income": ("OperatingIncomeLoss", "Utilidad operativa", "Estado de resultados"),
    "depreciation_amortization": (
        "DepreciationDepletionAndAmortization",
        "Depreciación y amortización",
        "Estado de flujo de efectivo",
    ),
    "income_tax_expense": (
        "IncomeTaxExpenseBenefit",
        "Gasto por impuestos (devengado)",
        "Estado de resultados",
    ),
    "income_tax_paid": (
        "IncomeTaxesPaidNet",
        "Impuestos pagados en efectivo (solo referencia)",
        "Notas al estado de flujo de efectivo",
    ),
    "net_income": ("NetIncomeLoss", "Utilidad neta", "Estado de resultados"),
}

# No toda empresa etiqueta las acciones diluidas igual; se prueban en orden.
_SHARES_CANDIDATES = (
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
)
_SHARES_LABEL = "Acciones en circulación (promedio ponderado)"
_SHARES_SECCION = "Estado de resultados (ganancia por acción)"

# No toda empresa etiqueta CAPEX igual; se prueban en este orden (SPEC.md 4.3).
_CAPEX_CANDIDATES = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PropertyPlantAndEquipmentAdditions",
)
_CAPEX_LABEL = "CAPEX (compra de propiedad, planta y equipo)"
_CAPEX_SECCION = "Estado de flujo de efectivo / nota de propiedad, planta y equipo"

# Candidatos de "línea agregada" de capital de trabajo (SPEC.md 4.4, paso 1).
# Si ninguno existe en el filing, el MVP marca ΔWK como "no verificado"
# (SPEC.md 4.4, paso 3) en vez de sumar líneas individuales a ciegas.
_WORKING_CAPITAL_AGGREGATE_CANDIDATES = (
    "IncreaseDecreaseInOperatingCapital",
    "IncreaseDecreaseInOperatingAssets",
    "IncreaseDecreaseInOperatingLiabilities",
    "IncreaseDecreaseInOtherOperatingCapitalNet",
)

# Cada empresa usa uno u otro tag de ingresos; se prueban en orden.
_REVENUE_CANDIDATES = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
)


def _find_fact_for_value(
    facts: list[ixbrl.IxFact], local_name: str, target_value: float
) -> ixbrl.IxFact | None:
    for fact in facts:
        if fact.local_name != local_name:
            continue
        value = ixbrl.to_number(fact.raw_text, fact.sign, fact.scale)
        if value is not None and abs(value - target_value) <= VALUE_MATCH_TOLERANCE:
            return fact
    return None


def _build_citation(
    full_text: str, fact: ixbrl.IxFact, doc_id: str, doc_hash: str, seccion: str
) -> Citation:
    start = max(0, fact.text_start - CONTEXT_WINDOW_CHARS)
    frase = full_text[start : fact.text_end].strip()
    return Citation(doc_id=doc_id, seccion=seccion, frase_exacta=frase, hash=doc_hash)


def _cite_value(
    *,
    concept_key: str,
    local_name: str,
    label: str,
    seccion: str,
    filing: FilingRef,
    full_text: str,
    facts: list[ixbrl.IxFact],
    doc_hash: str,
    target_value: float | None,
    period_end: str | None = None,
) -> CitedValue:
    if target_value is None:
        return CitedValue(
            concept=concept_key,
            label=label,
            value=None,
            citation=None,
            period_end=period_end,
            nota=f"us-gaap:{local_name} no está reportado para este periodo (no verificado).",
        )
    fact = _find_fact_for_value(facts, local_name, target_value)
    if fact is None:
        return CitedValue(
            concept=concept_key,
            label=label,
            value=target_value,
            citation=None,
            period_end=period_end,
            nota=(
                f"us-gaap:{local_name} = {target_value:,.0f} según la API de EDGAR, pero no "
                "se encontró el hecho correspondiente en el HTML descargado (no verificado: "
                "no se cita una frase que no se localizó)."
            ),
        )
    citation = _build_citation(full_text, fact, filing.doc_id, doc_hash, seccion)
    return CitedValue(
        concept=concept_key, label=label, value=target_value, citation=citation, period_end=period_end
    )


def _cite_current_year(
    *,
    concept_key: str,
    local_name: str,
    label: str,
    seccion: str,
    cik: str,
    filing: FilingRef,
    full_text: str,
    facts: list[ixbrl.IxFact],
    doc_hash: str,
) -> CitedValue:
    target_value = company_concept_fy_value(cik, local_name, filing)
    return _cite_value(
        concept_key=concept_key, local_name=local_name, label=label, seccion=seccion,
        filing=filing, full_text=full_text, facts=facts, doc_hash=doc_hash,
        target_value=target_value, period_end=filing.report_date,
    )


def _find_first_available(
    candidates: tuple[str, ...], cik: str, filing: FilingRef
) -> tuple[str, list] | None:
    """Primer tag candidato que el filing reporte, con sus columnas de año."""
    for local_name in candidates:
        periods = company_concept_periods_for_filing(cik, local_name, filing.accession_number)
        if periods:
            return local_name, periods
    return None


def extract_core_facts(
    *, cik: str, filing: FilingRef, html_text: str, doc_hash: str
) -> dict[str, object]:
    """Extrae los hechos citados del MVP a partir del documento ya descargado.

    `html_text` es el mismo documento cuyo hash es `doc_hash`; esta función
    nunca descarga nada, solo lo interpreta.
    """
    full_text, facts = ixbrl.parse_ixbrl(html_text)
    results: dict[str, object] = {}

    for concept_key, (local_name, label, seccion) in _SIMPLE_CONCEPTS.items():
        results[concept_key] = _cite_current_year(
            concept_key=concept_key, local_name=local_name, label=label, seccion=seccion,
            cik=cik, filing=filing, full_text=full_text, facts=facts, doc_hash=doc_hash,
        )

    # CAPEX: se prueban los candidatos en orden (SPEC.md 4.3); el primero
    # que el filing reporte para el año actual gana.
    capex_value = None
    capex_local_name = None
    for local_name in _CAPEX_CANDIDATES:
        value = company_concept_fy_value(cik, local_name, filing)
        if value is not None:
            capex_value, capex_local_name = value, local_name
            break
    if capex_local_name is not None:
        results["capex"] = _cite_value(
            concept_key="capex", local_name=capex_local_name, label=_CAPEX_LABEL,
            seccion=_CAPEX_SECCION, filing=filing, full_text=full_text, facts=facts,
            doc_hash=doc_hash, target_value=capex_value, period_end=filing.report_date,
        )
    else:
        results["capex"] = CitedValue(
            concept="capex", label=_CAPEX_LABEL, value=None, citation=None,
            nota=(
                "Ninguno de los tags de CAPEX candidatos (" + ", ".join(_CAPEX_CANDIDATES)
                + ") aparece en este filing (no verificado)."
            ),
        )

    # Ingresos: se usa el primer tag candidato que el filing reporte, y se
    # cita CADA columna de año disponible (sirve para el CAGR en calc/).
    revenue_match = _find_first_available(_REVENUE_CANDIDATES, cik, filing)
    revenue_series: list[CitedValue] = []
    if revenue_match is not None:
        local_name, periods = revenue_match
        for period in sorted(periods, key=lambda p: p.end):
            revenue_series.append(
                _cite_value(
                    concept_key="revenue", local_name=local_name, label=f"Ingresos ({period.end})",
                    seccion="Estado de resultados", filing=filing, full_text=full_text,
                    facts=facts, doc_hash=doc_hash, target_value=period.value,
                    period_end=period.end,
                )
            )
    results["revenue_series"] = revenue_series
    results["revenue"] = next(
        (cv for cv in revenue_series if cv.value is not None and cv.period_end == filing.report_date),
        None,
    ) or CitedValue(
        concept="revenue", label="Ingresos", value=None, citation=None,
        nota="Ninguno de los tags de ingresos candidatos aparece en este filing (no verificado).",
    )

    # Variación de capital de trabajo: solo línea agregada (SPEC.md 4.4).
    wk_value = None
    wk_local_name = None
    for local_name in _WORKING_CAPITAL_AGGREGATE_CANDIDATES:
        value = company_concept_fy_value(cik, local_name, filing)
        if value is not None:
            wk_value, wk_local_name = value, local_name
            break
    if wk_local_name is not None:
        results["working_capital_change"] = _cite_value(
            concept_key="working_capital_change", local_name=wk_local_name,
            label="Variación de capital de trabajo", seccion="Estado de flujo de efectivo",
            filing=filing, full_text=full_text, facts=facts, doc_hash=doc_hash,
            target_value=wk_value,
        )
    else:
        results["working_capital_change"] = CitedValue(
            concept="working_capital_change", label="Variación de capital de trabajo",
            value=None, citation=None,
            nota=(
                "Este filing no reporta una línea agregada de capital de trabajo "
                "(se probó: " + ", ".join(_WORKING_CAPITAL_AGGREGATE_CANDIDATES) + "). "
                "El MVP no suma líneas individuales a ciegas (SPEC.md 4.4, paso 3): "
                "queda como no verificado."
            ),
        )

    # EBITDA (derivado): nunca es una frase del documento, es la suma de dos
    # cifras ya citadas por separado (SPEC.md 4.1).
    op_income = results["operating_income"]
    dep_amort = results["depreciation_amortization"]
    if op_income.value is not None and dep_amort.value is not None:
        results["ebitda"] = CitedValue(
            concept="ebitda", label="EBITDA (derivado)",
            value=op_income.value + dep_amort.value, citation=None, derivado=True,
            nota="EBITDA = utilidad operativa + depreciación y amortización (SPEC.md 4.1).",
        )
    else:
        results["ebitda"] = CitedValue(
            concept="ebitda", label="EBITDA (derivado)", value=None, citation=None, derivado=True,
            nota="No se puede derivar EBITDA: falta utilidad operativa o D&A citadas.",
        )

    # Acciones diluidas: se prueban candidatos en orden, igual que CAPEX/ΔWK.
    shares_value = None
    shares_local_name = None
    for local_name in _SHARES_CANDIDATES:
        value = company_concept_fy_value(cik, local_name, filing)
        if value is not None:
            shares_value, shares_local_name = value, local_name
            break
    if shares_local_name is not None:
        results["diluted_shares"] = _cite_value(
            concept_key="diluted_shares", local_name=shares_local_name, label=_SHARES_LABEL,
            seccion=_SHARES_SECCION, filing=filing, full_text=full_text, facts=facts,
            doc_hash=doc_hash, target_value=shares_value, period_end=filing.report_date,
        )
    else:
        results["diluted_shares"] = CitedValue(
            concept="diluted_shares", label=_SHARES_LABEL, value=None, citation=None,
            nota=(
                "Ninguno de los tags de acciones candidatos (" + ", ".join(_SHARES_CANDIDATES)
                + ") aparece en este filing (no verificado)."
            ),
        )

    # EPS (derivado): utilidad neta / acciones diluidas. Se usa para el P/E
    # del apartado de valoración experimental (ver calc/valuation.py).
    net_income = results["net_income"]
    diluted_shares = results["diluted_shares"]
    if net_income.value is not None and diluted_shares.value not in (None, 0):
        results["eps"] = CitedValue(
            concept="eps", label="Utilidad por acción (derivado)",
            value=net_income.value / diluted_shares.value, citation=None, derivado=True,
            nota="EPS = utilidad neta / acciones diluidas.",
        )
    else:
        results["eps"] = CitedValue(
            concept="eps", label="Utilidad por acción (derivado)", value=None, citation=None,
            derivado=True, nota="No se puede derivar EPS: falta utilidad neta o acciones diluidas citadas.",
        )

    return results
