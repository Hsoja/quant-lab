import json
import urllib.error
from pathlib import Path

import pytest

from ingest import edgar

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeResponse:
    def __init__(self, content: bytes):
        self._content = content

    def read(self, _n=-1):
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _edgar_contact(monkeypatch):
    monkeypatch.setenv("EDGAR_CONTACT", "QuantLab-tests contact@example.org")


@pytest.fixture(autouse=True)
def _no_rate_limit_sleep(monkeypatch):
    # Las pruebas unitarias no deben pagar el 1 req/seg real; eso se prueba
    # por separado (test_rate_limiter_waits_between_calls).
    monkeypatch.setattr(edgar._rate_limiter, "wait", lambda: None)


def test_user_agent_requires_contact(monkeypatch):
    monkeypatch.delenv("EDGAR_CONTACT", raising=False)
    with pytest.raises(edgar.EdgarAccessError):
        edgar._user_agent()


def test_get_cik_known_ticker(monkeypatch):
    fixture_bytes = (FIXTURES / "company_tickers_sample.json").read_bytes()
    monkeypatch.setattr(
        edgar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(fixture_bytes)
    )
    assert edgar.get_cik("spgi") == "0000064040"


def test_get_cik_unknown_ticker(monkeypatch):
    fixture_bytes = (FIXTURES / "company_tickers_sample.json").read_bytes()
    monkeypatch.setattr(
        edgar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(fixture_bytes)
    )
    with pytest.raises(edgar.EdgarAccessError):
        edgar.get_cik("NOPE")


def test_list_10k_filings_filters_and_limits(monkeypatch):
    fixture_bytes = (FIXTURES / "submissions_sample.json").read_bytes()
    monkeypatch.setattr(
        edgar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(fixture_bytes)
    )
    filings = edgar.list_10k_filings("0000064040", limit=5)
    assert [f.accession_number for f in filings] == [
        "0000064040-26-000013",
        "0000064040-25-000052",
    ]
    assert filings[0].primary_document == "spgi-20251231.htm"
    assert filings[0].doc_id == "CIK0000064040-0000064040-26-000013"


def test_list_10k_filings_respects_limit(monkeypatch):
    fixture_bytes = (FIXTURES / "submissions_sample.json").read_bytes()
    monkeypatch.setattr(
        edgar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(fixture_bytes)
    )
    filings = edgar.list_10k_filings("0000064040", limit=1)
    assert len(filings) == 1


def test_filing_document_url_has_no_dashes_in_accession():
    filing = edgar.FilingRef(
        cik="0000064040",
        accession_number="0000064040-26-000013",
        filing_date="2026-02-11",
        primary_document="spgi-20251231.htm",
    )
    assert filing.document_url == (
        "https://www.sec.gov/Archives/edgar/data/64040/000006404026000013/"
        "spgi-20251231.htm"
    )


def test_sha256_hex_is_deterministic():
    assert edgar.sha256_hex(b"hola") == (
        "b221d9dbb083a7f33428d7c2a3c3198ae925614d70210e28716ccaa7cd4ddb79"
    )


def test_save_filing_writes_file_and_returns_matching_hash(tmp_path):
    dest = tmp_path / "sub" / "filing.htm"
    digest = edgar.save_filing(b"contenido de prueba", str(dest))
    assert dest.read_bytes() == b"contenido de prueba"
    assert digest == edgar.sha256_hex(b"contenido de prueba")


def test_download_filing_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "rate limited", {}, None)
        return _FakeResponse(b"<html>ok</html>")

    monkeypatch.setattr(edgar.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(edgar.time, "sleep", lambda _s: None)

    filing = edgar.FilingRef(
        cik="0000064040",
        accession_number="0000064040-26-000013",
        filing_date="2026-02-11",
        primary_document="spgi-20251231.htm",
    )
    content = edgar.download_filing(filing)
    assert content == b"<html>ok</html>"
    assert calls["n"] == 2


def test_download_filing_gives_up_after_max_retries(monkeypatch):
    def always_fails(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "down", {}, None)

    monkeypatch.setattr(edgar.urllib.request, "urlopen", always_fails)
    monkeypatch.setattr(edgar.time, "sleep", lambda _s: None)

    filing = edgar.FilingRef(
        cik="0000064040",
        accession_number="0000064040-26-000013",
        filing_date="2026-02-11",
        primary_document="spgi-20251231.htm",
    )
    with pytest.raises(edgar.EdgarAccessError):
        edgar.download_filing(filing)


def test_get_rejects_document_over_size_cap(monkeypatch):
    too_big = b"x" * (edgar.MAX_DOCUMENT_BYTES + 10)
    monkeypatch.setattr(
        edgar.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(too_big)
    )
    with pytest.raises(edgar.EdgarAccessError):
        edgar._get("https://www.sec.gov/fake")


@pytest.mark.network
def test_real_edgar_access_for_example_company():
    """Prueba de integración real: confirma que EDGAR sigue respondiendo.

    Se salta por defecto (ver conftest.py). Activar con RUN_NETWORK_TESTS=1.
    """
    cik = edgar.get_cik("SPGI")
    assert cik == "0000064040"

    filings = edgar.list_10k_filings(cik, limit=1)
    assert len(filings) == 1

    content = edgar.download_filing(filings[0])
    assert len(content) > 0
    assert b"ix:nonFraction" in content or b"ix:nonfraction" in content.lower()
    assert len(edgar.sha256_hex(content)) == 64
