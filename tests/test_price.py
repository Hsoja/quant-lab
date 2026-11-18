import urllib.error

import pytest

from ingest import price


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
def _no_rate_limit_sleep(monkeypatch):
    monkeypatch.setattr(price._rate_limiter, "wait", lambda: None)


SAMPLE_RESPONSE = (
    b'{"chart":{"result":[{"meta":{"currency":"USD","symbol":"SPGI",'
    b'"regularMarketTime":1794949202,"regularMarketPrice":452.35,'
    b'"fiftyTwoWeekHigh":522.47}}],"error":null}}'
)


def test_parse_latest_price_happy_path():
    point = price.parse_latest_price(SAMPLE_RESPONSE)
    assert point is not None
    assert point.price == 452.35
    assert point.currency == "USD"
    assert point.as_of == "2026-11-17"
    assert point.frase_exacta in SAMPLE_RESPONSE.decode("utf-8")
    assert point.frase_exacta == '"regularMarketPrice":452.35'


def test_parse_latest_price_returns_none_on_malformed_json():
    assert price.parse_latest_price(b"no es json") is None


def test_parse_latest_price_returns_none_when_fields_missing():
    assert price.parse_latest_price(b'{"chart":{"result":[{"meta":{}}]}}') is None


def test_fetch_price_chart_rejects_non_https_scheme():
    with pytest.raises(price.PriceAccessError):
        price.fetch_price_chart("file:///etc/passwd")


def test_fetch_price_chart_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "down", {}, None)
        return _FakeResponse(SAMPLE_RESPONSE)

    monkeypatch.setattr(price.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(price.time, "sleep", lambda _s: None)

    content = price.fetch_price_chart("SPGI")
    assert content == SAMPLE_RESPONSE
    assert calls["n"] == 2


def test_fetch_price_chart_gives_up_after_max_retries(monkeypatch):
    def always_fails(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "down", {}, None)

    monkeypatch.setattr(price.urllib.request, "urlopen", always_fails)
    monkeypatch.setattr(price.time, "sleep", lambda _s: None)

    with pytest.raises(price.PriceAccessError):
        price.fetch_price_chart("SPGI")


def test_fetch_price_chart_rejects_oversized_response(monkeypatch):
    too_big = b"x" * (price.MAX_RESPONSE_BYTES + 10)
    monkeypatch.setattr(price.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(too_big))
    with pytest.raises(price.PriceAccessError):
        price.fetch_price_chart("SPGI")
