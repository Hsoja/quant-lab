import pytest

from calc.fcf import compute_fcf, compute_revenue_cagr, _years_between
from extract.facts import Citation, CitedValue


def _cv(value, label="L", period_end=None):
    citation = (
        Citation(doc_id="D", seccion="S", frase_exacta="x", hash="h") if value is not None else None
    )
    return CitedValue(concept="c", label=label, value=value, citation=citation, period_end=period_end)


def test_compute_fcf_happy_path():
    facts = {
        "ebitda": _cv(1200.0),
        "income_tax_expense": _cv(150.0),
        "capex": _cv(50.0),
        "working_capital_change": _cv(20.0),
    }
    result = compute_fcf(facts)
    assert result.value == 1200.0 - 150.0 - 50.0 - 20.0
    assert result.componentes_no_verificados == []


def test_compute_fcf_missing_component_is_not_computed():
    facts = {
        "ebitda": _cv(1200.0),
        "income_tax_expense": _cv(150.0),
        "capex": _cv(50.0),
        "working_capital_change": _cv(None, label="Variación de capital de trabajo"),
    }
    result = compute_fcf(facts)
    assert result.value is None
    assert result.componentes_no_verificados == ["Variación de capital de trabajo"]


def test_compute_revenue_cagr_happy_path():
    series = [
        _cv(900.0, period_end="2024-12-31"),
        _cv(1100.0, period_end="2025-12-31"),
    ]
    result = compute_revenue_cagr(series)
    years = _years_between("2024-12-31", "2025-12-31")
    expected = (1100.0 / 900.0) ** (1 / years) - 1
    assert result.value == pytest.approx(expected)
    assert result.inicio.period_end == "2024-12-31"
    assert result.fin.period_end == "2025-12-31"


def test_compute_revenue_cagr_needs_at_least_two_years():
    result = compute_revenue_cagr([_cv(1100.0, period_end="2025-12-31")])
    assert result.value is None
    assert "no verificado" in result.nota.lower()
