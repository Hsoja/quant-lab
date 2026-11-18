from extract import ixbrl


def test_parse_ixbrl_extracts_fact_with_correct_offset_and_text():
    html = (
        "<html><body><table><tr><td>Operating income</td>"
        '<td><ix:nonFraction name="us-gaap:OperatingIncomeLoss" '
        'contextRef="FY2025" unitRef="USD" scale="6" decimals="-6">1,000'
        "</ix:nonFraction></td></tr></table></body></html>"
    )
    text, facts = ixbrl.parse_ixbrl(html)
    assert len(facts) == 1
    fact = facts[0]
    assert fact.local_name == "OperatingIncomeLoss"
    assert fact.raw_text == "1,000"
    assert text[fact.text_start : fact.text_end] == "1,000"
    assert "Operating income" in text


def test_parse_ixbrl_ignores_script_and_style_content():
    html = (
        "<html><head><style>body{color:red}</style></head><body>"
        "<script>alert('x')</script>"
        "<p>Texto visible</p>"
        "</body></html>"
    )
    text, facts = ixbrl.parse_ixbrl(html)
    assert "color:red" not in text
    assert "alert" not in text
    assert "Texto visible" in text
    assert facts == []


def test_to_number_handles_commas_parentheses_scale_and_sign():
    assert ixbrl.to_number("1,000", None, 6) == 1_000_000_000.0
    assert ixbrl.to_number("(50)", None, 0) == -50.0
    assert ixbrl.to_number("50", "-", 0) == -50.0
    assert ixbrl.to_number("—", None, 0) == 0.0
    assert ixbrl.to_number("no es un número", None, 0) is None


def test_boundary_tags_prevent_word_concatenation():
    html = "<table><tr><td>Total</td><td>6,478</td></tr></table>"
    text, _facts = ixbrl.parse_ixbrl(html)
    assert "Total6,478" not in text
    assert "Total" in text and "6,478" in text
