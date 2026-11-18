"""CLI del MVP: corre el pipeline completo para un ticker en SEC EDGAR.

    python cli.py SPGI --out-dir salida

Descarga el 10-K más reciente, lo guarda con su hash, extrae y verifica las
cifras, calcula FCF y CAGR, y escribe el reporte en Markdown y en HTML
(reporte.md, reporte.html) en la carpeta de salida.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from calc.fcf import compute_fcf, compute_revenue_cagr
from extract.facts import extract_core_facts
from ingest.edgar import download_filing, get_cik, list_10k_filings, save_filing
from report.html_report import build_html_report
from report.report import build_report
from verify.verifier import verify_all

_EXAMPLES_COMPANIES_PATH = Path(__file__).resolve().parent / "examples" / "companies.json"


def _load_example_companies() -> dict | None:
    """Datos precalculados para "Pruébalo con una acción" (ver SPEC.md 9).
    Si el archivo no existe o no se puede leer, la página simplemente no
    muestra esa sección — nunca se inventan empresas de ejemplo."""
    try:
        return json.loads(_EXAMPLES_COMPANIES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run(ticker: str, out_dir: str) -> None:
    cik = get_cik(ticker)
    filings = list_10k_filings(cik, limit=1)
    if not filings:
        raise SystemExit(f"{ticker} no tiene 10-K en SEC EDGAR.")
    filing = filings[0]

    content = download_filing(filing)
    os.makedirs(out_dir, exist_ok=True)
    doc_path = os.path.join(out_dir, f"{ticker.lower()}_{filing.accession_no_dashes}.htm")
    doc_hash = save_filing(content, doc_path)
    html_text = content.decode("utf-8", errors="replace")

    facts = extract_core_facts(cik=cik, filing=filing, html_text=html_text, doc_hash=doc_hash)
    verified = verify_all(facts, content)
    fcf = compute_fcf(verified)
    cagr = compute_revenue_cagr(verified["revenue_series"])

    md = build_report(
        empresa_ejemplo=ticker, filing_doc_id=filing.doc_id, verified=verified, fcf=fcf, cagr=cagr
    )
    html = build_html_report(
        empresa_ejemplo=ticker, filing_doc_id=filing.doc_id, verified=verified, fcf=fcf, cagr=cagr,
        companies=_load_example_companies(),
    )

    Path(out_dir, "reporte.md").write_text(md, encoding="utf-8")
    Path(out_dir, "reporte.html").write_text(html, encoding="utf-8")

    print(f"Documento original guardado en: {doc_path}")
    print(f"Reporte Markdown: {os.path.join(out_dir, 'reporte.md')}")
    print(f"Reporte web:      {os.path.join(out_dir, 'reporte.html')}")


def main() -> None:
    load_dotenv()  # lee .env si existe; EDGAR_CONTACT nunca se inventa (ver ingest/edgar.py)
    parser = argparse.ArgumentParser(description="Quant Lab: reporte de un 10-K con citas verificables.")
    parser.add_argument("ticker", help="Ticker en SEC EDGAR, ej. SPGI (sin bancos: el MVP no les aplica)")
    parser.add_argument("--out-dir", default="salida", help="Carpeta de salida (por defecto: salida/)")
    args = parser.parse_args()
    run(args.ticker.upper(), args.out_dir)


if __name__ == "__main__":
    main()
