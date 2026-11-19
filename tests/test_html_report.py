import base64
import hashlib
import re
import shutil
import subprocess

import pytest

from calc.fcf import CagrResult, FcfResult
from extract.facts import Citation, CitedValue
from report.html_report import build_html_report


def _node_check(js: str, tmp_dir=None):
    """`node --check` sobre un archivo temporal (/dev/stdin no existe en todos los entornos)."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(js)
        path = fh.name
    try:
        return subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=10)
    finally:
        import os
        os.unlink(path)


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
    # El único https:// permitido fuera de la CSP es: el enlace al repositorio
    # (navegación decidida por la persona) y las referencias a TradingView dentro
    # del <script> (solo se usan para armar el src de un <iframe> con sandbox,
    # nunca un script ni un estilo cargado por nuestra cuenta).
    http_links = [line for line in html.splitlines() if "http://" in line or "https://" in line]
    assert all(
        "Content-Security-Policy" in line
        or "tradingview.com" in line
        or "tradingview-widget.com" in line
        or "www.w3.org/2000/svg" in line  # identificador de espacio de nombres SVG, no un recurso
        or ("github.com/Hsoja/quant-lab" in line and 'rel="noopener noreferrer"' in line)
        for line in http_links
    )


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
    result = _node_check(script_match.group(1))
    assert result.returncode == 0, result.stderr


def test_reveal_content_is_visible_by_default_without_javascript():
    """Defensa en profundidad: si el script no corre por CUALQUIER motivo
    (no solo el de la prueba anterior), el contenido .reveal nunca debe
    depender de JS para mostrarse. Solo se "pre-esconde" bajo `.js-ready`,
    una clase que el propio script agrega como primera línea; sin JS, esa
    clase nunca existe y el valor por defecto del CSS es visible."""
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    style_match = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    assert style_match
    css = style_match.group(1)
    # Ninguna línea cuyo selector EMPIECE en ".reveal" (bare, sin ".js-ready"
    # antes) puede esconderlo (opacity: 0) — eso sería volver al bug original.
    bare_hidden_rules = [
        line for line in css.splitlines()
        if re.match(r"\s*\.reveal\s*\{", line) and "opacity: 0" in line
    ]
    assert not bare_hidden_rules, f"`.reveal` se esconde sin `.js-ready` por delante: {bare_hidden_rules}"
    assert ".js-ready .reveal" in css
    assert 'classList.add("js-ready")' in html


def _sample_companies():
    return {
        "FAKE": {
            "ticker": "FAKE",
            "filing_doc_id": "CIK0-0001",
            "report_date": "2025-12-31",
            "figures": {
                "revenue": {
                    "label": "Ingresos", "value": 1100.0, "derivado": False, "no_verificado": False,
                    "nota": None, "citation": {"doc_id": "CIK0-0001", "seccion": "S", "frase_exacta": "Revenue $ 1,100"},
                },
            },
            "fcf": {"value": None, "nota": "falta ΔWK"},
            "cagr": {"value": 0.05, "nota": "CAGR de prueba"},
            "valuation": {
                "price": 10.0, "price_as_of": "2025-12-31",
                "price_citation": {"doc_id": "YAHOO-CHART:FAKE", "seccion": "Cotización", "frase_exacta": '"regularMarketPrice":10'},
                "pe": 12.5, "fcf_yield": None, "market_cap": 1000.0, "veredicto": "barata",
                "nota": "Lectura automática simple; es una prueba.",
            },
        }
    }


def test_try_it_section_absent_without_companies_data():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr, companies=None,
    )
    # El script siempre menciona estos IDs (debe degradarse sin datos), pero
    # el HTML de la sección en sí solo existe si se le dieron empresas.
    assert 'data-json=' not in html
    assert '<select id="company-select"' not in html
    assert '<h2 id="try-it-title">' not in html


def test_try_it_section_has_warning_and_bot_avatar():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr, companies=_sample_companies(),
    )
    assert "Esto es una prueba" in html
    assert "no es asesoría financiera" in html.lower() or "asesoría financiera" in html
    assert "bot-avatar" in html
    assert 'id="company-select"' in html
    assert 'id="try-it-result"' in html


def test_try_it_section_escapes_embedded_company_data():
    companies = _sample_companies()
    companies["FAKE"]["figures"]["revenue"]["citation"]["frase_exacta"] = "<script>alert(1)</script>"
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr, companies=companies,
    )
    assert "<script>alert(1)</script>" not in html
    # El JSON va dentro de un atributo HTML (data-json), nunca en un <script> propio.
    assert 'id="companies-data"' in html
    assert re.search(r'<script[^>]*>\s*\{', html) is None


def test_try_it_section_js_has_no_syntax_errors():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr, companies=_sample_companies(),
    )
    script_match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script_match
    if shutil.which("node") is None:
        pytest.skip("node no está disponible en este entorno")
    result = _node_check(script_match.group(1))
    assert result.returncode == 0, result.stderr


def _sample_companies_with_qa():
    companies = _sample_companies()
    companies["FAKE"]["tradingview_symbol"] = "NYSE:FAKE"
    companies["FAKE"]["qa"] = [
        {"pregunta": "¿Cómo le fue en ingresos?", "respuesta": "Los ingresos fueron de US$ 1,100,000,000."},
        {"pregunta": "¿Cuál es el riesgo?", "respuesta": "El FCF no se pudo calcular (no verificado)."},
    ]
    return companies


def test_live_widgets_use_sandboxed_iframe_with_no_dangerous_permissions():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr, companies=_sample_companies_with_qa(),
    )
    assert "sandbox" in html
    for dangerous in ("allow-forms", "allow-top-navigation", "allow-modals", "allow-pointer-lock"):
        assert dangerous not in html
    assert "embed-widget/" in html
    assert '"symbol-overview"' in html
    assert '"timeline"' in html
    assert "SYMBOL_PATTERN" in html  # el símbolo se valida antes de armar la URL


def test_chat_section_warns_it_is_not_a_live_chat_and_never_recommends():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr, companies=_sample_companies_with_qa(),
    )
    assert "no es un chat en vivo" in html
    for forbidden in ("compra esta acción", "vende ahora", "recomendamos comprar"):
        assert forbidden not in html.lower()


# --- Diseño v2: capas, simulación y diario ---------------------------------

def _plain_html(companies=None):
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    return build_html_report(
        empresa_ejemplo="Empresa de Ejemplo", filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr, companies=companies,
    )


def test_layers_are_ordered_and_separated_by_a_frontier():
    html = _plain_html()
    assert html.index("CAPA A · HECHOS VERIFICADOS") < html.index('role="separator"') < html.index("CAPA B · SIMULADO")
    assert html.index("CAPA B · SIMULADO") < html.index('id="diario"')


def test_simulation_layer_has_no_citations_and_says_it_is_not_a_prediction():
    html = _plain_html()
    layer_b = html[html.index('id="simulacion"'):html.index('id="diario"')]
    assert "no un hecho ni una predicción" in layer_b
    assert "<blockquote" not in layer_b  # nada citado dentro de lo simulado
    assert "no están validadas" in layer_b or "no están validadas con un" in layer_b


def test_layer_a_has_no_simulated_numbers():
    html = _plain_html()
    layer_a = html[html.index('id="reporte"'):html.index('role="separator"')]
    for word in ("Monte Carlo", "VaR 95", "P50", "SIMULADO"):
        assert word not in layer_a


def test_diary_keeps_fact_and_scenario_in_separate_fields_and_never_stores():
    html = _plain_html()
    assert 'id="diary-fact"' in html and 'id="diary-scenario"' in html
    assert 'maxlength="1000"' in html
    for forbidden in ("localStorage", "sessionStorage", "document.cookie", "XMLHttpRequest", "fetch("):
        assert forbidden not in html
    assert "<form" not in html.lower()


def test_figure_cards_expose_labels_for_the_diary():
    html = _plain_html()
    assert 'data-figure-label="Ingresos"' in html


def test_monte_carlo_math_is_correct_in_node():
    """Corre el motor de simulación del navegador en Node y revisa propiedades matemáticas."""
    import json
    import re as _re
    from report.html_report import _SCRIPT

    start = _SCRIPT.index("function mulberry32")
    end = _SCRIPT.index("// --- Panel de simulación")
    math_js = _SCRIPT[start:end]
    assert "document." not in math_js and "window." not in math_js
    program = (
        math_js
        + """
var base = { s0: 100, mu: 0.1, sigma: 0.0, days: 252, paths: 200, capital: 1000, seed: 7 };
var flat = summarize(simulateGBM(base));
var noisy = summarize(simulateGBM({ s0: 100, mu: 0.1, sigma: 0.3, days: 90, paths: 4000, capital: 1000, seed: 7 }));
var again = summarize(simulateGBM({ s0: 100, mu: 0.1, sigma: 0.3, days: 90, paths: 4000, capital: 1000, seed: 7 }));
var other = summarize(simulateGBM({ s0: 100, mu: 0.1, sigma: 0.3, days: 90, paths: 4000, capital: 1000, seed: 8 }));
console.log(JSON.stringify({ flat: flat.p50, flatSpread: flat.p95 - flat.p5, noisy: noisy, same: noisy.p50 === again.p50, diff: noisy.p50 !== other.p50 }));
"""
    )
    import subprocess, tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(program)
        path = fh.name
    try:
        out = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert abs(data["flat"] - 1000 * 2.718281828459045 ** 0.1) < 1e-6  # sigma=0: determinista
    assert data["flatSpread"] < 1e-6
    n = data["noisy"]
    assert n["p5"] < n["p50"] < n["p95"]
    assert 0 <= n["pLoss10"] <= 1 and 0 <= n["pUp"] <= 1 and n["pGain20"] <= n["pUp"]
    assert n["var95"] >= 0
    assert abs(n["var95"] - max(0, 1000 - n["p5"])) < 1e-9
    assert sum(n["hist"]["bins"]) == 4000
    assert data["same"] and data["diff"]


# --- Diseño v3: fuentes embebidas, TradingView, asistente flotante ---------------


def test_fonts_are_embedded_as_data_uris_and_csp_allows_only_data_fonts():
    html = _plain_html()
    assert html.count("src: url(data:font/woff2;base64,") == 4
    for family in ("Manrope", "Instrument Serif", "IBM Plex Mono"):
        assert f'font-family: "{family}"' in html
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "font-src data:" in csp
    assert "fonts.gstatic" not in html and "fonts.googleapis" not in html


def test_csp_frame_src_only_allows_the_tradingview_widget_host():
    html = _plain_html()
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "frame-src https://www.tradingview-widget.com;" in csp
    assert "s.tradingview.com" not in html
    assert "script-src 'self' 'sha256-" in csp


def test_tradingview_widgets_pass_their_config_in_the_url_hash_never_a_script():
    from report.html_report import _SCRIPT

    assert 'TV_BASE = "https://www.tradingview-widget.com/embed-widget/"' in _SCRIPT
    assert 'encodeURIComponent(JSON.stringify(config))' in _SCRIPT
    for widget in ("ticker-tape", "advanced-chart", "symbol-overview", "timeline"):
        assert f'"{widget}"' in _SCRIPT
    assert "createElement(\"script\")" not in _SCRIPT and "createElement('script')" not in _SCRIPT


def test_floating_bot_is_present_and_declares_it_is_not_live():
    html = _plain_html()
    for element_id in ("bot-open", "bot-drawer", "bot-input", "bot-log", "bot-chips", "bot-data"):
        assert f'id="{element_id}"' in html
    assert "no es un chat en vivo" in html
    assert 'data-kb="' in html
    # Sin red en el asistente: nada de fetch/XHR/WebSocket en el script.
    from report.html_report import _SCRIPT

    for forbidden in ("WebSocket", "EventSource", "sendBeacon"):
        assert forbidden not in _SCRIPT


def test_bot_knowledge_base_uses_only_report_figures_and_never_recommends():
    import json
    from report.html_report import _bot_kb

    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    kb = _bot_kb("EJEMPLO", "CIK0-0001", verified, fcf, cagr)
    texts = " ".join(item["respuesta"] for item in kb).lower()
    assert "us$ 1,100" in texts  # ingreso de la fixture, tomado de verified
    assert "falta Δwk".lower() in texts  # el motivo real del FCF faltante
    for forbidden in ("compra esta acción", "vende ahora", "recomendamos comprar"):
        assert forbidden not in texts
    assert all({"pregunta", "respuesta", "keywords"} <= set(item) for item in kb)
    json.dumps(kb)  # serializable


def test_bot_data_is_escaped_inside_its_attribute():
    verified = _verified_fixture()
    fcf, cagr = _fcf_cagr()
    html = build_html_report(
        empresa_ejemplo='"><script>alert(1)</script>', filing_doc_id="CIK0-0001",
        verified=verified, fcf=fcf, cagr=cagr,
    )
    assert "<script>alert(1)</script>" not in html


def test_hero_counts_match_the_verified_figures():
    html = _plain_html()
    # fixture: 6 citadas, 1 derivada (EBITDA), 1 sin verificar (capital de trabajo)
    assert re.search(r"<small>Citadas</small><b>6</b>", html)
    assert re.search(r"<small>Derivadas</small><b>1</b>", html)
    assert re.search(r"<small>Sin verificar</small><b>1</b>", html)
