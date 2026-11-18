import cli
from ingest.edgar import ConceptPeriod, FilingRef

FAKE_VALUES = {
    "OperatingIncomeLoss": 1_000_000_000.0,
    "DepreciationDepletionAndAmortization": 200_000_000.0,
    "IncomeTaxExpenseBenefit": 150_000_000.0,
    "PaymentsToAcquirePropertyPlantAndEquipment": 50_000_000.0,
}
FAKE_REVENUE_PERIODS = [
    ConceptPeriod(start="2024-01-01", end="2024-12-31", value=900_000_000.0),
    ConceptPeriod(start="2025-01-01", end="2025-12-31", value=1_100_000_000.0),
]

HTML_DOC = """
<html><body><table>
<tr><td>Operating income</td><td>
<ix:nonFraction name="us-gaap:OperatingIncomeLoss" contextRef="FY2025" unitRef="USD" scale="6" decimals="-6">1,000</ix:nonFraction>
</td></tr>
<tr><td>Depreciation and amortization</td><td>
<ix:nonFraction name="us-gaap:DepreciationDepletionAndAmortization" contextRef="FY2025" unitRef="USD" scale="6" decimals="-6">200</ix:nonFraction>
</td></tr>
<tr><td>Income tax expense</td><td>
<ix:nonFraction name="us-gaap:IncomeTaxExpenseBenefit" contextRef="FY2025" unitRef="USD" scale="6" decimals="-6">150</ix:nonFraction>
</td></tr>
<tr><td>Purchases of property and equipment</td><td>
<ix:nonFraction name="us-gaap:PaymentsToAcquirePropertyPlantAndEquipment" contextRef="FY2025" unitRef="USD" scale="6" decimals="-6">50</ix:nonFraction>
</td></tr>
<tr><td>Revenue 2024</td><td>
<ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="FY2024" unitRef="USD" scale="6" decimals="-6">900</ix:nonFraction>
</td></tr>
<tr><td>Revenue 2025</td><td>
<ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="FY2025" unitRef="USD" scale="6" decimals="-6">1,100</ix:nonFraction>
</td></tr>
</table></body></html>
""".encode("utf-8")


def _fake_filing():
    return FilingRef(
        cik="0000000001", accession_number="0000000001-26-000001",
        filing_date="2026-02-11", report_date="2025-12-31", primary_document="fake-10k.htm",
    )


def test_run_writes_markdown_and_html_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_cik", lambda ticker: "0000000001")
    monkeypatch.setattr(cli, "list_10k_filings", lambda cik, limit=1: [_fake_filing()])
    monkeypatch.setattr(cli, "download_filing", lambda filing: HTML_DOC)

    import extract.facts as facts_module
    monkeypatch.setattr(facts_module, "company_concept_fy_value", lambda cik, concept, filing: FAKE_VALUES.get(concept))
    monkeypatch.setattr(
        facts_module, "company_concept_periods_for_filing",
        lambda cik, concept, accession_number: (
            FAKE_REVENUE_PERIODS if concept == "RevenueFromContractWithCustomerExcludingAssessedTax" else []
        ),
    )

    out_dir = str(tmp_path / "salida")
    cli.run("FAKE", out_dir)

    md = (tmp_path / "salida" / "reporte.md").read_text(encoding="utf-8")
    html = (tmp_path / "salida" / "reporte.html").read_text(encoding="utf-8")
    assert "Análisis informativo, no asesoría financiera" in md
    assert "Content-Security-Policy" in html
    assert "FAKE" in md and "FAKE" in html
    saved_doc = tmp_path / "salida" / "fake_000000000126000001.htm"
    assert saved_doc.exists()
