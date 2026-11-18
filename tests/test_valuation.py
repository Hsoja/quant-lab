from calc.valuation import compute_valuation
from extract.facts import Citation, CitedValue


def _cv(value, derivado=True):
    return CitedValue(concept="x", label="X", value=value, citation=None, derivado=derivado)


def _price_citation():
    return Citation(doc_id="YAHOO-CHART:FAKE", seccion="Cotización", frase_exacta='"regularMarketPrice":10', hash="h")


def test_compute_valuation_marks_barata_when_both_signals_agree():
    result = compute_valuation(
        eps=_cv(1.0), diluted_shares=_cv(100.0), fcf_value=600.0,
        price=10.0, price_citation=_price_citation(), price_as_of="2026-01-01",
    )
    # P/E = 10/1 = 10 (<=20 -> barata); market_cap = 10*100 = 1000; fcf_yield = 600/1000 = 0.6 (>=0.05 -> barata)
    assert result.pe == 10.0
    assert result.fcf_yield == 0.6
    assert result.veredicto == "barata"


def test_compute_valuation_marks_cara_when_both_signals_agree():
    result = compute_valuation(
        eps=_cv(0.1), diluted_shares=_cv(100.0), fcf_value=1.0,
        price=10.0, price_citation=_price_citation(), price_as_of="2026-01-01",
    )
    # P/E = 10/0.1 = 100 (>=30 -> cara); market_cap = 1000; fcf_yield = 1/1000 = 0.001 (<0.02 -> cara)
    assert result.veredicto == "cara"


def test_compute_valuation_marks_neutral_on_mixed_signals():
    result = compute_valuation(
        eps=_cv(0.5), diluted_shares=_cv(100.0), fcf_value=600.0,
        price=10.0, price_citation=_price_citation(), price_as_of="2026-01-01",
    )
    # P/E = 10/0.5 = 20 (<=20 -> barata); fcf_yield = 600/1000 = 0.6 (barata) -- make it mixed instead
    # Ajustamos: EPS alto para que P/E sea "cara" y fcf_yield siga "barata".
    result = compute_valuation(
        eps=_cv(0.1), diluted_shares=_cv(100.0), fcf_value=600.0,
        price=10.0, price_citation=_price_citation(), price_as_of="2026-01-01",
    )
    assert result.veredicto == "neutral"


def test_compute_valuation_is_no_verificado_without_price():
    result = compute_valuation(
        eps=_cv(1.0), diluted_shares=_cv(100.0), fcf_value=600.0,
        price=None, price_citation=None, price_as_of=None,
    )
    assert result.veredicto == "no verificado"
    assert result.pe is None
    assert result.fcf_yield is None


def test_compute_valuation_handles_missing_eps_or_shares_without_crashing():
    result = compute_valuation(
        eps=_cv(None), diluted_shares=_cv(None), fcf_value=None,
        price=10.0, price_citation=_price_citation(), price_as_of="2026-01-01",
    )
    assert result.pe is None
    assert result.fcf_yield is None
    assert result.veredicto == "no verificado"


def test_compute_valuation_never_divides_by_zero():
    result = compute_valuation(
        eps=_cv(0.0), diluted_shares=_cv(0.0), fcf_value=600.0,
        price=10.0, price_citation=_price_citation(), price_as_of="2026-01-01",
    )
    assert result.pe is None  # eps <= 0 no se usa para P/E
    assert result.fcf_yield is None  # market_cap es 0, no se divide
