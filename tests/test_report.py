from calc.fcf import CagrResult, FcfResult
from extract.facts import Citation, CitedValue
from report.report import DISCLAIMER, build_report


def _cv(value, label, citation_text=None, derivado=False, nota=""):
    citation = (
        Citation(doc_id="CIK0-0001", seccion="Estado de resultados", frase_exacta=citation_text, hash="h")
        if citation_text is not None
        else None
    )
    return CitedValue(concept=label, label=label, value=value, citation=citation, derivado=derivado, nota=nota)


def _verified_fixture(wk_no_verificado=True):
    return {
        "revenue": _cv(1100.0, "Ingresos", "Revenue $ 1,100"),
        "operating_income": _cv(600.0, "Utilidad operativa", "Operating income $ 600"),
        "depreciation_amortization": _cv(100.0, "Depreciación y amortización", "D&A $ 100"),
        "ebitda": _cv(700.0, "EBITDA (derivado)", citation_text=None, derivado=True, nota="EBITDA = ..."),
        "income_tax_expense": _cv(80.0, "Gasto por impuestos (devengado)", "Tax expense $ 80"),
        "income_tax_paid": _cv(90.0, "Impuestos pagados en efectivo (referencia)", "Taxes paid $ 90"),
        "capex": _cv(50.0, "CAPEX", "Capex $ 50"),
        "working_capital_change": (
            CitedValue(concept="wk", label="Variación de capital de trabajo", value=None, citation=None,
                       nota="no reporta línea agregada (no verificado)")
            if wk_no_verificado
            else _cv(20.0, "Variación de capital de trabajo", "WK change $ 20")
        ),
    }


def test_report_puts_risk_section_before_figures_and_ends_with_disclaimer():
    verified = _verified_fixture()
    fcf = FcfResult(value=None, componentes_no_verificados=["Variación de capital de trabajo"], nota="falta ΔWK")
    cagr = CagrResult(value=0.05, years=1.0, inicio=None, fin=None, nota="CAGR de prueba")

    report = build_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )

    risk_idx = report.index("Riesgo y limitaciones")
    figures_idx = report.index("Cifras con fuente")
    assert risk_idx < figures_idx
    assert report.strip().endswith(DISCLAIMER)
    assert "Variación de capital de trabajo" in report.split("Cifras con fuente")[0]  # listada como riesgo


def test_report_lists_no_verificado_items_as_risk_and_shows_citations_for_the_rest():
    verified = _verified_fixture()
    fcf = FcfResult(value=None, componentes_no_verificados=["Variación de capital de trabajo"], nota="falta ΔWK")
    cagr = CagrResult(value=None, years=None, inicio=None, fin=None, nota="sin datos suficientes")

    report = build_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )

    assert "no se pudieron verificar" in report
    assert "Revenue $ 1,100" in report
    assert "Operating income $ 600" in report
    assert "no verificado" in report  # CAGR y ΔWK


def test_report_includes_change_summary_when_given():
    verified = _verified_fixture(wk_no_verificado=False)
    fcf = FcfResult(value=550.0, componentes_no_verificados=[], nota="FCF calculado")
    cagr = CagrResult(value=0.08, years=2.0, inicio=None, fin=None, nota="CAGR calculado")

    report = build_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
        resumen_cambios="- Los ingresos subieron.",
    )

    assert "Resumen de cambios" in report
    assert "Los ingresos subieron." in report
    assert "Todas las cifras de este reporte tienen una cita verificada" in report


def test_report_never_recommends_buying_or_selling():
    verified = _verified_fixture()
    fcf = FcfResult(value=None, componentes_no_verificados=["x"], nota="n")
    cagr = CagrResult(value=None, years=None, inicio=None, fin=None, nota="n")
    report = build_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    for forbidden in ("compra esta acción", "vende ahora", "recomendamos comprar"):
        assert forbidden not in report.lower()
