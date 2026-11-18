# Quant Lab

A monitor for official financial reports with **verifiable citations**. It reads a report
(currently a 10-K from SEC EDGAR), extracts structured figures, computes them in code, and cites
every claim against the originally downloaded document. An automated verifier confirms each
citation exists literally in the document; if it doesn't, the claim is discarded and marked
**"not verified"**.

**Not financial advice.** It's a research tool: it shows a thesis, the risk, and what would
invalidate it — never a buy/sell signal. Built so anyone can use it with any non-financial company
that files with the SEC (banks are out of scope: EBITDA and EV/EBITDA don't apply to them in any
meaningful way).

Full rules and decisions live in [`SPEC.md`](SPEC.md). The threat model for each piece lives in
[`docs/SECURITY.md`](docs/SECURITY.md). Security audit results: [`SECURITY_REPORT.md`](SECURITY_REPORT.md).

**Live demo page:** https://hsoja.github.io/quant-lab/ — a static report generated from public
data for an example company, showcasing the citation format and the "not verified" flags.

## Status

MVP complete (phases 0-6), validated live against a real 10-K: `ingest/`, `extract/`, `calc/`,
`verify/`, `llm/`, and `report/` all work end to end. Example generated from public data:
[`examples/reporte_ejemplo.md`](examples/reporte_ejemplo.md) and
[`examples/reporte_ejemplo.html`](examples/reporte_ejemplo.html).

## Install

Requires **Python 3.9 or newer** (patched versions of some dependencies don't exist for 3.8; see
[`SECURITY_REPORT.md`](SECURITY_REPORT.md), finding QL-5).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set your own contact in EDGAR_CONTACT
```

To run the security scanners (bandit, pip-audit, semgrep): `pip install -r requirements-dev.txt`.

## Usage

```bash
python cli.py SPGI --out-dir output
```

Downloads the most recent 10-K for the ticker, saves it with its hash, extracts and verifies the
figures, and writes `output/report.md` and `output/report.html` (a static page, no backend or
forms — see "The web page" below). `ANTHROPIC_API_KEY` in `.env` is optional; it's only needed for
the change summary in `llm/summarizer.py` (phase 5), which **never** receives the document's raw
text, only the JSON of already-verified figures (see `docs/SECURITY.md`).

## The web page

`report/html_report.py` generates a single self-contained HTML file (white and light blue) from
the same data as the Markdown report. It's static on purpose: no backend, no forms, no
`localStorage`, no external scripts or fonts. All dynamic text goes through `html.escape` before
being inserted, and it ships a strict Content-Security-Policy (`default-src 'none'`; the inline
`<script>` is allowed by a SHA-256 hash of its exact content, not `'unsafe-inline'`). Reveal
content is visible by default and only pre-hides once the script confirms it started, so a future
script failure for any reason can't blank the page again. Animations respect
`prefers-reduced-motion`.

### "Try it with a stock" (experimental)

A small interactive section lets you pick among a handful of pre-computed example companies and
see a simple, mechanical "cheap / expensive / neutral" read (P/E and FCF yield against two fixed
thresholds) — clearly marked as a test, never investment advice. It stays static: no ticker is
fetched live from the browser. `scripts/precompute_examples.py` runs the full pipeline plus a
price lookup (`ingest/price.py`, an unofficial Yahoo Finance endpoint — SEC EDGAR has no market
prices) for a short list of tickers and writes `examples/companies.json`, which the page embeds
as a `data-json` HTML attribute (never inside a `<script>` tag) and reads client-side. See
SPEC.md section 9 for the full decisions and limitations.

## Running tests

```bash
pytest
```

By default no calls are made to real EDGAR (network tests are marked and skipped). To confirm real
access:

```bash
RUN_NETWORK_TESTS=1 pytest -m network
```

## Tech stack

Python · SEC EDGAR (inline XBRL) · Anthropic API (optional, phase 5 only) · pytest · bandit ·
pip-audit · semgrep · gitleaks

## License

[MIT](LICENSE)
