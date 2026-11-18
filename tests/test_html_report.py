import base64
import hashlib
import re
import shutil
import subprocess

import pytest

from calc.fcf import CagrResult, FcfResult
from extract.facts import Citation, CitedValue
from report.html_report import build_html_report


def _cv(value, label, citation_text=None, derivado=False, nota=""):
    citation = (
        Citation(doc_id="CIK0-0001", seccion="Estado de resultados", frase_exacta=citation_text, hash="h")
        if citation_text is not None
        else None
    )
    return CitedValue(concept=label, label=label, value=value, citation=citation, derivado=derivado, nota=nota)


def _verified_fixture(xss_payload=None):
    frase = xss_payload or "Revenue $ 1,100"
    return {
        "revenue": _cv(1100.0, "Ingresos", frase),
        "operating_income": _cv(600.0, "Utilidad operativa", "Operating income $ 600"),
        "depreciation_amortization": _cv(100.0, "Depreciación y amortización", "D&A $ 100"),
        "ebitda": _cv(700.0, "EBITDA (derivado)", derivado=True, nota="EBITDA = ..."),
        "income_tax_expense": _cv(80.0, "Gasto por impuestos (devengado)", "Tax expense $ 80"),
        "income_tax_paid": _cv(90.0, "Impuestos pagados en efectivo (referencia)", "Taxes paid $ 90"),
        "capex": _cv(50.0, "CAPEX", "Capex $ 50"),
        "working_capital_change": CitedValue(
            concept="wk", label="Variación de capital de trabajo", value=None, citation=None,
            nota="no reporta línea agregada (no verificado)",
        ),
    }


def _fcf_cagr():
    fcf = FcfResult(value=None, componentes_no_verificados=["Variación de capital de trabajo"], nota="falta ΔWK")
    cagr = CagrResult(value=0.05, years=1.0, inicio=None, fin=None, nota="CAGR de prueba")
    return fcf, cagr


def test_html_report_escapes_xss_payload_in_citation():
    payload = "<img src=x onerror=alert(1)>"
    verified = _verified_fixture(xss_payload=payload)
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_html_report_escapes_xss_in_change_summary():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
        resumen_cambios="<script>alert(1)</script>",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_html_report_escapes_xss_in_company_name_and_doc_id():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="<script>alert(1)</script>", filing_doc_id="\"><svg onload=alert(1)>",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    assert "<script>alert(1)</script>" not in html
    assert "<svg onload=alert(1)>" not in html


def test_html_report_has_strict_csp_and_no_external_resources():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    assert "Content-Security-Policy" in html
    assert "default-src 'none'" in html
    # No se carga ningún recurso de terceros (scripts, estilos, imágenes, fuentes):
    # ni <script src=, ni <link ... href=, ni fuentes de CDN o de Google Fonts.
    assert "<script src=" not in html.lower()
    assert "<link " not in html.lower()
    assert "cdn." not in html.lower()
    assert "fonts.googleapis" not in html.lower()
    # El único enlace a https:// permitido es la navegación, decidida por la persona,
    # al propio repositorio del proyecto — nunca una carga automática de un recurso.
    http_links = [line for line in html.splitlines() if "http://" in line or "https://" in line]
    assert all("github.com/Hsoja/quant-lab" in line and 'rel="noopener noreferrer"' in line for line in http_links)


def test_html_report_has_no_dangerous_js_patterns():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    for forbidden in ("innerHTML", "eval(", "new Function", "document.write", "onerror=", "onclick="):
        assert forbidden not in html


def test_html_report_risk_section_appears_before_figures_and_never_recommends():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    assert html.index("Riesgo y limitaciones") < html.index("Cifras con fuente")
    for forbidden in ("compra esta acción", "vende ahora", "recomendamos comprar"):
        assert forbidden not in html.lower()
    assert "no es asesoría financiera" in html.lower()


def test_html_report_respects_prefers_reduced_motion():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    assert "prefers-reduced-motion" in html


def test_inline_script_is_allowed_by_its_own_csp():
    """Caso real que pasó: la CSP decía `script-src 'self'` sin permitir el
    <script> inline de la propia página. El navegador lo bloqueaba en
    silencio (sin error visible) y TODO el contenido con clase `.reveal`
    (riesgo, pasos, tarjetas, confianza) se quedaba en opacity:0 para
    siempre, porque el script que agrega `.is-visible` nunca llegaba a
    correr. Esta prueba recalcula, igual que haría un navegador, el hash
    SHA-256 del <script> tal como quedó en el HTML y confirma que SÍ está
    en la lista de permitidos de la CSP."""
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    script_match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script_match, "no se encontró el <script> de la página"
    digest = base64.b64encode(hashlib.sha256(script_match.group(1).encode("utf-8")).digest()).decode("ascii")

    csp_match = re.search(r'Content-Security-Policy" content="([^"]+)"', html)
    assert csp_match, "no se encontró la Content-Security-Policy"
    csp = csp_match.group(1)

    assert f"sha256-{digest}" in csp, (
        "el script-src de la CSP no permite este <script> exacto: "
        "el navegador lo bloquearía y la página se quedaría en blanco"
    )
    assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0], (
        "no debe depender de 'unsafe-inline' para scripts: el hash es la protección real"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está disponible en este entorno")
def test_inline_script_has_no_syntax_errors():
    """Confirma, con un intérprete de JS de verdad, que el <script> no tiene
    errores de sintaxis — una prueba de texto no lo detectaría."""
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    script_match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script_match
    result = subprocess.run(
        ["node", "--check", "/dev/stdin"],
        input=script_match.group(1), capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
