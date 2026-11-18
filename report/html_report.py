"""Página web del reporte (adicional, fuera del alcance original del MVP,
ver SPEC.md sección 3). Es un único archivo HTML autocontenido y estático:
no hay backend, no hay formularios, no se guarda nada en el navegador.
Blanco y azul claro, animada, y pensada para explicar el sistema de
verificación (no solo mostrar números) — así alguien que nunca vio el
proyecto entiende, en un scroll, por qué puede confiar en lo que lee.

Reglas de seguridad (skill frontend-seguro) aplicadas:
- Todo texto dinámico pasa por `html.escape` antes de insertarse — defensa
  en profundidad, porque las citas vienen del documento oficial, que todo
  el proyecto trata como dato no confiable (nunca como instrucción).
- CSP estricta vía `<meta>`: sin scripts externos, sin fuentes externas,
  sin `eval`/`Function`/`innerHTML`. El único `<script>` usa
  `textContent`/`addEventListener`, nunca HTML armado a mano, y su
  `script-src` se permite por **hash SHA-256 del contenido exacto**
  (`'sha256-...'`), no por `'unsafe-inline'`: solo ese script, byte a byte,
  puede ejecutarse. El único enlace a `https://` que existe en la página es,
  a propósito, al propio código fuente en GitHub (navegación que decide la
  persona, no una carga automática de un recurso de terceros) y lleva
  `rel="noopener noreferrer"`.
- Nunca sugiere comprar ni vender; mismo pie de no asesoría que el Markdown
  de `report/report.py`, cuyo catálogo de conceptos reutiliza (una sola
  fuente de verdad sobre qué cifras existen y en qué orden).
- Ningún dato personal: solo cifras de la empresa de ejemplo y metadatos
  del propio documento oficial (ya público).
"""

from __future__ import annotations

import base64
import hashlib
import html as _html
import json as _json
from datetime import datetime, timezone

from calc.fcf import CagrResult, FcfResult
from extract.facts import CitedValue
from report.report import DISCLAIMER, _DISPLAY_ORDER

_REPO_URL = "https://github.com/Hsoja/quant-lab"

# El único <script> de la página, como texto plano (sin f-string: así sus
# propias llaves de JS no necesitan escaparse por duplicado). Como la página
# es estática, un nonce no serviría de nada (sería el mismo siempre, visible
# en el propio HTML); en cambio, un hash SHA-256 del contenido exacto SÍ es
# una restricción real: solo este script, byte a byte, puede ejecutarse — no
# "cualquier script inline" ('unsafe-inline' sí lo permitiría).
_SCRIPT = """(function () {
  "use strict";
  // Primera línea a propósito: recién ahora es seguro "pre-esconder" el
  // contenido para animarlo. Si el script nunca llega a correr (CSP, un
  // error, lo que sea), esta clase nunca se agrega y todo se queda visible
  // por el valor por defecto del CSS.
  document.documentElement.classList.add("js-ready");
  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var progress = document.getElementById("scroll-progress");
  function updateProgress() {
    var doc = document.documentElement;
    var max = doc.scrollHeight - doc.clientHeight;
    var pct = max > 0 ? (doc.scrollTop / max) * 100 : 0;
    progress.style.width = pct + "%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  updateProgress();

  function animateCount(el) {
    var raw = el.getAttribute("data-count");
    if (raw === null) return;
    var target = parseFloat(raw);
    if (isNaN(target)) return;
    var suffix = el.getAttribute("data-suffix") || "";
    var isMoney = suffix === "";
    if (prefersReduced) return; // el texto final ya está en el DOM, no hace falta animar
    var start = null;
    var duration = 900;
    function step(ts) {
      if (start === null) start = ts;
      var progressRatio = Math.min((ts - start) / duration, 1);
      var current = target * progressRatio;
      if (isMoney) {
        el.textContent = "US$ " + Math.round(current).toLocaleString("en-US");
      } else {
        el.textContent = (current >= 0 ? "+" : "") + current.toFixed(2) + suffix;
      }
      if (progressRatio < 1) {
        window.requestAnimationFrame(step);
      } else if (isMoney) {
        el.textContent = "US$ " + Math.round(target).toLocaleString("en-US");
      }
    }
    window.requestAnimationFrame(step);
  }

  // --- "Pruébalo con una acción" (experimental): todo con datos ya
  // embebidos en la página (data-json), nunca una llamada de red desde el
  // navegador. Construido solo con createElement y textContent.
  (function () {
    var dataEl = document.getElementById("companies-data");
    var select = document.getElementById("company-select");
    var resultEl = document.getElementById("try-it-result");
    if (!dataEl || !select || !resultEl) return;

    var companies = {};
    try {
      companies = JSON.parse(dataEl.getAttribute("data-json") || "{}");
    } catch (e) {
      companies = {};
    }

    Object.keys(companies).sort().forEach(function (ticker) {
      var opt = document.createElement("option");
      opt.value = ticker;
      opt.textContent = ticker;
      select.appendChild(opt);
    });

    function clear(el) {
      while (el.firstChild) el.removeChild(el.firstChild);
    }

    function money(value) {
      if (value === null || value === undefined) return "no verificado";
      return "US$ " + Math.round(value).toLocaleString("en-US");
    }

    function pct(value) {
      if (value === null || value === undefined) return "no verificado";
      return (value * 100).toFixed(2) + "%";
    }

    function badge(text, kind) {
      var span = document.createElement("span");
      span.className = "badge badge-" + kind;
      span.textContent = text;
      return span;
    }

    function figureRow(figure) {
      var row = document.createElement("div");
      row.className = "try-it-figure";
      var label = document.createElement("span");
      label.className = "try-it-figure-label";
      label.textContent = figure.label;
      var value = document.createElement("span");
      value.className = "try-it-figure-value";
      value.textContent = money(figure.value);
      row.appendChild(label);
      row.appendChild(value);
      if (figure.no_verificado) row.appendChild(badge("no verificado", "warn"));
      else if (figure.derivado) row.appendChild(badge("derivado", "info"));
      else row.appendChild(badge("citado", "ok"));
      return row;
    }

    function badgeKindForVerdict(verdict) {
      if (verdict === "barata") return "ok";
      if (verdict === "cara") return "warn";
      if (verdict === "neutral") return "info";
      return "warn"; // "no verificado"
    }

    function renderResult(ticker) {
      var company = companies[ticker];
      clear(resultEl);
      if (!company) return;

      var thinking = document.createElement("p");
      thinking.className = "thinking";
      thinking.textContent = "🤖 Analizando " + ticker + "…";
      resultEl.appendChild(thinking);

      window.setTimeout(
        function () {
          clear(resultEl);
          var valuation = company.valuation;

          var head = document.createElement("div");
          head.className = "try-it-result-head";
          var title = document.createElement("h3");
          title.textContent = ticker + " — " + company.filing_doc_id;
          head.appendChild(title);
          head.appendChild(badge(valuation.veredicto, badgeKindForVerdict(valuation.veredicto)));
          resultEl.appendChild(head);

          var priceP = document.createElement("p");
          priceP.className = "try-it-price";
          if (valuation.price !== null) {
            priceP.textContent =
              "Precio (" + valuation.price_as_of + "): US$ " + valuation.price.toFixed(2) +
              " · P/E: " + (valuation.pe !== null ? valuation.pe.toFixed(1) : "no verificado") +
              " · FCF yield: " + pct(valuation.fcf_yield);
          } else {
            priceP.textContent = "Precio no disponible (no verificado).";
          }
          resultEl.appendChild(priceP);

          var notaP = document.createElement("p");
          notaP.className = "card-note";
          notaP.textContent = valuation.nota;
          resultEl.appendChild(notaP);

          var figuresWrap = document.createElement("div");
          figuresWrap.className = "try-it-figures";
          Object.keys(company.figures).forEach(function (key) {
            figuresWrap.appendChild(figureRow(company.figures[key]));
          });
          resultEl.appendChild(figuresWrap);
        },
        prefersReduced ? 0 : 650
      );
    }

    select.addEventListener("change", function () {
      if (select.value) renderResult(select.value);
      else clear(resultEl);
    });
  })();

  var items = document.querySelectorAll(".reveal");
  if (prefersReduced || !("IntersectionObserver" in window)) {
    items.forEach(function (el) { el.classList.add("is-visible"); });
    return;
  }
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        var counter = entry.target.querySelector("[data-count]");
        if (counter) animateCount(counter);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });
  items.forEach(function (el) { observer.observe(el); });
})();"""


def _sha256_b64(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


_SCRIPT_HASH = _sha256_b64(_SCRIPT)

_CSP = (
    "default-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    f"script-src 'self' 'sha256-{_SCRIPT_HASH}'; "
    "img-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

_STYLE = """
  :root {
    --bg: #ffffff;
    --surface: #eef5ff;
    --surface-2: #dbeafe;
    --accent: #2563eb;
    --accent-2: #38bdf8;
    --accent-dark: #1e40af;
    --text: #0f172a;
    --muted: #51607a;
    --warn-bg: #fff7ed;
    --warn-border: #f59e0b;
    --radius: 16px;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
  }
  a { color: var(--accent-dark); }
  #scroll-progress {
    position: fixed; top: 0; left: 0; height: 3px; width: 0%;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
    z-index: 50; transition: width .1s linear;
  }
  .hero {
    position: relative; overflow: hidden;
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
    color: #ffffff; padding: 3rem 1.5rem 3.5rem;
  }
  .hero-blob {
    position: absolute; inset: -40% -10% auto auto; width: 60vw; height: 60vw; max-width: 640px; max-height: 640px;
    background: radial-gradient(circle at 30% 30%, rgba(255,255,255,.35), transparent 60%);
    border-radius: 50%; pointer-events: none;
  }
  .hero-inner { position: relative; max-width: 960px; margin: 0 auto; }
  .pill-row { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1.25rem; }
  .pill {
    background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.35);
    padding: .3rem .75rem; border-radius: 999px; font-size: .78rem; backdrop-filter: blur(4px);
  }
  .hero h1 { margin: 0 0 .35rem; font-size: 2rem; }
  .hero-sub { margin: 0 0 1.25rem; opacity: .92; font-size: .95rem; }
  .hero-cta {
    display: inline-block; color: #ffffff; text-decoration: none; font-weight: 600;
    border-bottom: 2px solid rgba(255,255,255,.6); padding-bottom: 2px;
  }
  main { max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem 1rem; }
  section { margin-bottom: 2.5rem; }
  h2 { color: var(--accent-dark); font-size: 1.25rem; }
  .section-intro { color: var(--muted); margin-top: -.5rem; }
  .risk {
    background: var(--warn-bg); border-left: 4px solid var(--warn-border);
    border-radius: var(--radius); padding: 1.25rem 1.5rem;
  }
  .risk ul { margin: .5rem 0; padding-left: 1.25rem; }
  .risk-note { color: var(--muted); font-size: .9rem; }

  .pipeline-track { display: flex; flex-wrap: wrap; align-items: stretch; gap: .5rem; }
  .step {
    flex: 1 1 160px; background: var(--surface); border: 1px solid var(--surface-2);
    border-radius: var(--radius); padding: 1.1rem; text-align: center;
  }
  .step-icon { font-size: 1.6rem; margin-bottom: .4rem; }
  .step h3 { margin: 0 0 .35rem; font-size: .95rem; color: var(--accent-dark); }
  .step p { margin: 0; font-size: .82rem; color: var(--muted); }
  .step-arrow { align-self: center; color: var(--accent); font-size: 1.3rem; flex: 0 0 auto; }
  @media (max-width: 720px) { .step-arrow { transform: rotate(90deg); } }

  .trust-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
  .trust-card { background: var(--surface); border: 1px solid var(--surface-2); border-radius: var(--radius); padding: 1.1rem; }
  .trust-icon { font-size: 1.5rem; margin-bottom: .3rem; }
  .trust-card h3 { margin: 0 0 .3rem; font-size: .95rem; }
  .trust-card p { margin: 0; font-size: .85rem; color: var(--muted); }
  .trust-link { text-align: center; font-size: .9rem; }

  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
  .calc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
  .card {
    background: var(--surface); border: 1px solid var(--surface-2); border-radius: var(--radius);
    padding: 1rem 1.1rem; transition: transform .2s ease, box-shadow .2s ease;
  }
  .card:hover { transform: translateY(-3px); box-shadow: 0 10px 24px -12px rgba(37,99,235,.35); }
  .card-head { display: flex; align-items: center; gap: .5rem; }
  .card-head h3 { margin: 0; font-size: .92rem; color: var(--text); flex: 1; }
  .card-icon { font-size: 1.1rem; }
  .card-value { font-size: 1.5rem; font-weight: 700; margin: .5rem 0; color: var(--accent-dark); }
  .card-note { color: var(--muted); font-size: .85rem; margin: 0; }
  .card-detail summary { cursor: pointer; color: var(--accent-dark); font-size: .85rem; }
  .card-detail summary:focus-visible, a:focus-visible, button:focus-visible {
    outline: 3px solid var(--accent); outline-offset: 2px;
  }
  .card-detail div { font-size: .85rem; color: var(--muted); margin-top: .4rem; }
  .card-detail blockquote {
    margin: .4rem 0 0; padding: .5rem .75rem; background: #ffffff;
    border-left: 3px solid var(--accent); border-radius: 6px; font-style: italic;
  }
  .badge { font-size: .7rem; padding: .15rem .5rem; border-radius: 999px; white-space: nowrap; }
  .badge-ok { background: #dcfce7; color: #166534; }
  .badge-info { background: #dbeafe; color: #1e40af; }
  .badge-warn { background: #fef3c7; color: #92400e; }
  .cambios-body { white-space: pre-line; }

  .try-it { background: var(--surface); border: 1px solid var(--surface-2); border-radius: var(--radius); padding: 1.5rem; }
  .try-it-warning {
    background: var(--warn-bg); border-left: 4px solid var(--warn-border); border-radius: 10px;
    padding: .9rem 1.1rem; font-size: .85rem; margin-bottom: 1.25rem;
  }
  .try-it-head { display: flex; align-items: center; gap: .9rem; margin-bottom: 1rem; }
  .try-it-head h2 { margin: 0; }
  .bot-avatar {
    flex: 0 0 auto; width: 44px; height: 44px; border-radius: 50%;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    display: flex; align-items: center; justify-content: center; font-size: 1.4rem;
    animation: bot-pulse 2.4s ease-in-out infinite;
  }
  @keyframes bot-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.08); } }
  .try-it-label { display: block; font-size: .85rem; font-weight: 600; margin-bottom: .35rem; }
  .try-it-select {
    width: 100%; max-width: 320px; padding: .55rem .7rem; border-radius: 10px;
    border: 1px solid var(--surface-2); background: #ffffff; color: var(--text); font-size: .95rem;
  }
  .try-it-select:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
  .try-it-result { margin-top: 1.25rem; min-height: 1px; }
  .try-it-result-head { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
  .try-it-result-head h3 { margin: 0; font-size: 1rem; }
  .try-it-price { font-size: .95rem; margin: .5rem 0; }
  .try-it-figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: .5rem; margin-top: .75rem; }
  .try-it-figure {
    display: flex; align-items: center; justify-content: space-between; gap: .5rem;
    background: #ffffff; border: 1px solid var(--surface-2); border-radius: 10px; padding: .5rem .7rem; font-size: .82rem;
  }
  .try-it-figure-label { color: var(--muted); }
  .try-it-figure-value { font-weight: 700; }
  .thinking { color: var(--muted); }
  .thinking::after { content: ""; animation: thinking-dots 1.2s steps(4, end) infinite; }
  @keyframes thinking-dots { 0% { content: ""; } 25% { content: "."; } 50% { content: ".."; } 75% { content: "..."; } }
  @media (prefers-reduced-motion: reduce) {
    .bot-avatar { animation: none; }
    .thinking::after { animation: none; content: "..."; }
  }

  footer {
    text-align: center; color: var(--muted); font-size: .85rem;
    padding: 1.5rem; border-top: 1px solid var(--surface-2);
  }
  footer strong { color: var(--text); }
  /* El contenido es visible por defecto: si el script no corre, por lo que
     sea (bloqueado, un error, JS desactivado), nunca desaparece. Solo se
     "pre-esconde" para animar cuando el propio script confirma que arrancó
     (clase .js-ready en <html>, puesta como primera línea del script). */
  .js-ready .reveal { opacity: 0; transform: translateY(14px); transition: opacity .5s ease, transform .5s ease; }
  .reveal.is-visible { opacity: 1; transform: none; }
  @media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    .js-ready .reveal { opacity: 1; transform: none; transition: none; }
    .card { transition: none; }
    #scroll-progress { transition: none; }
  }
"""

_CONCEPT_ICONS = {
    "revenue": "💰",
    "operating_income": "⚙️",
    "depreciation_amortization": "📉",
    "ebitda": "⚡",
    "income_tax_expense": "🏛️",
    "income_tax_paid": "🧾",
    "capex": "🏗️",
    "working_capital_change": "🔄",
}

_PIPELINE_STEPS = (
    (
        "📥",
        "Ingesta",
        "Se descarga el documento oficial y se guarda con su huella digital (hash). Esa huella "
        "es la identidad del documento para todo lo que sigue: si cambia un solo carácter, la "
        "huella cambia y se nota.",
    ),
    (
        "🔍",
        "Extracción",
        "Cada cifra se busca en los datos estructurados del propio documento (XBRL en línea) y "
        "se localiza su frase exacta ahí mismo — nunca se copia de un resumen ni se inventa.",
    ),
    (
        "🛡️",
        "Verificación",
        "Un verificador independiente vuelve a abrir el documento guardado y confirma que cada "
        "frase exista ahí, literal. Si no existe, se descarta — esto pasa antes de que cualquier "
        "modelo de lenguaje intervenga.",
    ),
    (
        "🤖",
        "Resumen (IA)",
        "El modelo redacta a partir de las cifras YA verificadas — nunca lee el documento "
        "original. Así, nada escondido en el documento puede influir en lo que escribe.",
    ),
    (
        "📄",
        "Reporte",
        "El riesgo y las limitaciones se muestran primero, luego cada cifra con su fuente. "
        "Nunca una recomendación de compra o venta.",
    ),
)

_TRUST_POINTS = (
    (
        "🔒",
        "Sin tus datos, nunca",
        "Esta página es un archivo estático: no hay servidor, no hay formularios, no se guarda "
        "nada en tu navegador. Solo muestra cifras públicas de una empresa de ejemplo.",
    ),
    (
        "🚫",
        "Nunca una orden de compra o venta",
        "El objetivo es mostrar de dónde sale cada número, no decirte qué hacer con tu dinero. "
        "Eso siempre lo decides tú, con tu propio criterio.",
    ),
    (
        "🧩",
        "Código abierto y verificable",
        "Las reglas de este sistema (qué se cita, cómo se calcula cada cifra, cómo se verifica) "
        "están escritas y versionadas — no son una caja negra.",
    ),
)


def _esc(value: object) -> str:
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "no verificado"
    return f"US$ {value:,.0f}"


def _badge(cv: CitedValue) -> str:
    if cv.no_verificado:
        return '<span class="badge badge-warn">no verificado</span>'
    if cv.derivado:
        return '<span class="badge badge-info">derivado</span>'
    return '<span class="badge badge-ok">citado</span>'


def _count_attr(value: float | None, suffix: str = "") -> str:
    """data-count para la animación numérica; vacío si no hay valor que animar."""
    if value is None:
        return ""
    suffix_attr = f' data-suffix="{_esc(suffix)}"' if suffix else ""
    return f' data-count="{value!r}"{suffix_attr}'


def _figure_card(index: int, key: str, label: str, cv: CitedValue) -> str:
    icon = _CONCEPT_ICONS.get(key, "🔎")
    if cv.no_verificado:
        detail = _esc(cv.nota) or "Sin fuente suficiente; no se usó en ningún cálculo."
    elif cv.derivado:
        detail = _esc(cv.nota) or "Calculado a partir de otras cifras de esta misma tabla."
    else:
        detail = (
            f"{_esc(cv.citation.doc_id)} · {_esc(cv.citation.seccion)}"
            f"<blockquote>{_esc(cv.citation.frase_exacta)}</blockquote>"
        )
    delay = min(index, 6) * 60
    return f"""
      <article class="card reveal" style="transition-delay:{delay}ms" data-key="{_esc(key)}">
        <header class="card-head">
          <span class="card-icon" aria-hidden="true">{icon}</span>
          <h3>{_esc(label)}</h3>
          {_badge(cv)}
        </header>
        <p class="card-value"{_count_attr(cv.value)}>{_esc(_fmt_money(cv.value))}</p>
        <details class="card-detail">
          <summary>Ver fuente</summary>
          <div>{detail}</div>
        </details>
      </article>"""


def _hero(empresa_ejemplo: str, filing_doc_id: str, generated_at: datetime) -> str:
    return f"""
  <header class="hero">
    <div class="hero-blob" aria-hidden="true"></div>
    <div class="hero-inner">
      <div class="pill-row">
        <span class="pill">✅ Cada cifra citada o marcada "no verificado"</span>
        <span class="pill">🔒 Sin backend · sin tus datos</span>
        <span class="pill">🚫 Nunca "compra" ni "vende"</span>
      </div>
      <h1>{_esc(empresa_ejemplo)}</h1>
      <p class="hero-sub">Reporte de {_esc(filing_doc_id)} · generado {_esc(generated_at.strftime('%Y-%m-%d %H:%M UTC'))}</p>
      <a class="hero-cta" href="#como-funciona">¿Cómo sé que esto es confiable? ↓</a>
    </div>
  </header>"""


def _pipeline_section() -> str:
    steps = []
    for i, (icon, title, body) in enumerate(_PIPELINE_STEPS):
        delay = i * 90
        arrow = '<span class="step-arrow" aria-hidden="true">→</span>' if i < len(_PIPELINE_STEPS) - 1 else ""
        steps.append(
            f"""
        <div class="step reveal" style="transition-delay:{delay}ms">
          <div class="step-icon" aria-hidden="true">{icon}</div>
          <h3>{_esc(title)}</h3>
          <p>{_esc(body)}</p>
        </div>
        {arrow}"""
        )
    return f"""
    <section class="pipeline" id="como-funciona" aria-labelledby="pipeline-title">
      <h2 id="pipeline-title">🔬 Cómo se verifica cada cifra</h2>
      <p class="section-intro">Cinco pasos, en este orden a propósito, antes de que algo llegue a esta
      página:</p>
      <div class="pipeline-track">{''.join(steps)}
      </div>
    </section>"""


def _trust_section() -> str:
    cards = "".join(
        f"""
      <div class="trust-card reveal">
        <div class="trust-icon" aria-hidden="true">{icon}</div>
        <h3>{_esc(title)}</h3>
        <p>{_esc(body)}</p>
      </div>"""
        for icon, title, body in _TRUST_POINTS
    )
    return f"""
    <section class="trust" aria-labelledby="trust-title">
      <h2 id="trust-title">🤝 Por qué puedes confiar en esta página</h2>
      <div class="trust-grid">{cards}
      </div>
      <p class="trust-link">
        <a href="{_REPO_URL}" target="_blank" rel="noopener noreferrer">Ver las reglas y el código fuente completos ↗</a>
      </p>
    </section>"""


def _risk_banner(verified: dict, fcf: FcfResult) -> str:
    sin_cita = [label for key, label in _DISPLAY_ORDER if verified[key].no_verificado]
    items = "".join(f"<li>{_esc(label)}</li>" for label in sin_cita)
    fcf_line = (
        f'<p class="risk-fcf"><strong>El FCF no se pudo calcular:</strong> {_esc(fcf.nota)}</p>'
        if fcf.value is None
        else ""
    )
    cuerpo = (
        f"<p>Estas cifras <strong>no se pudieron verificar</strong> con una cita en el documento "
        f"y no se usaron en ningún cálculo:</p><ul>{items}</ul>"
        if sin_cita
        else "<p>Todas las cifras de este reporte tienen una cita verificada contra el documento original.</p>"
    )
    return f"""
    <section class="risk reveal" aria-labelledby="risk-title">
      <h2 id="risk-title">⚠️ Riesgo y limitaciones (léase primero)</h2>
      {cuerpo}
      {fcf_line}
      <p class="risk-note">Este reporte describe lo que dice el documento oficial citado abajo;
      no es una tesis de inversión completa y no sustituye leer el reporte completo.</p>
    </section>"""


def _calc_cards(fcf: FcfResult, cagr: CagrResult) -> str:
    cagr_text = f"{cagr.value:+.2%}" if cagr.value is not None else "no verificado"
    cagr_pct = cagr.value * 100 if cagr.value is not None else None
    return f"""
    <section class="calc-grid" aria-label="Cálculos">
      <article class="card reveal">
        <header class="card-head"><span class="card-icon" aria-hidden="true">🧮</span><h3>FCF</h3></header>
        <p class="card-value"{_count_attr(fcf.value)}>{_esc(_fmt_money(fcf.value))}</p>
        <p class="card-note">{_esc(fcf.nota)}</p>
      </article>
      <article class="card reveal">
        <header class="card-head"><span class="card-icon" aria-hidden="true">📈</span><h3>CAGR de ingresos</h3></header>
        <p class="card-value"{_count_attr(cagr_pct, suffix="%")}>{_esc(cagr_text)}</p>
        <p class="card-note">{_esc(cagr.nota)}</p>
      </article>
    </section>"""


def _try_it_section(companies: dict | None) -> str:
    if not companies:
        return ""
    companies_json = _json.dumps(companies, ensure_ascii=False, separators=(",", ":"))
    return f"""
    <section class="try-it reveal" aria-labelledby="try-it-title">
      <p class="try-it-warning">
        <strong>⚠️ Esto es una prueba (experimental).</strong> La lectura de "barata" o "cara" es
        automática y simple (P/E y FCF yield con dos umbrales fijos) — no es la metodología
        completa de un manual de inversión, no compara contra el sector ni revisa señales de
        alerta, y de ninguna manera es asesoría financiera. No tomes ninguna decisión basada en
        esto.
      </p>
      <div class="try-it-head">
        <span class="bot-avatar" aria-hidden="true">🤖</span>
        <div>
          <h2 id="try-it-title">Pruébalo con una acción</h2>
          <p class="section-intro">Elige una empresa ya verificada y mira el mismo pipeline correr sobre sus cifras.</p>
        </div>
      </div>
      <label class="try-it-label" for="company-select">Empresa</label>
      <select id="company-select" class="try-it-select">
        <option value="">— elige una empresa —</option>
      </select>
      <div id="try-it-result" class="try-it-result" aria-live="polite"></div>
    </section>
    <div id="companies-data" hidden data-json="{_esc(companies_json)}"></div>"""


def build_html_report(
    *,
    empresa_ejemplo: str,
    filing_doc_id: str,
    verified: dict,
    fcf: FcfResult,
    cagr: CagrResult,
    resumen_cambios: str | None = None,
    generated_at: datetime | None = None,
    companies: dict | None = None,
) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    cards = "".join(
        _figure_card(i, key, label, verified[key]) for i, (key, label) in enumerate(_DISPLAY_ORDER)
    )
    cambios_section = (
        f"""
    <section class="card reveal" aria-labelledby="cambios-title">
      <h2 id="cambios-title">📝 Resumen de cambios</h2>
      <div class="cambios-body">{_esc(resumen_cambios)}</div>
    </section>"""
        if resumen_cambios
        else ""
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{_CSP}">
<meta name="referrer" content="no-referrer">
<title>{_esc(empresa_ejemplo)} — Reporte Quant Lab</title>
<style>{_STYLE}</style>
</head>
<body>
  <div id="scroll-progress"></div>
  {_hero(empresa_ejemplo, filing_doc_id, generated_at)}
  <main>
    {_risk_banner(verified, fcf)}
    {_pipeline_section()}
    <section aria-label="Cifras con fuente">
      <h2>📊 Cifras con fuente</h2>
      <p class="section-intro">Cada tarjeta dice si la cifra está citada, es derivada de otras, o no se pudo verificar.</p>
      <div class="grid">{cards}
      </div>
    </section>
    <section aria-label="Cálculos">
      <h2>🧮 Cálculos</h2>
      {_calc_cards(fcf, cagr)}
    </section>
    {cambios_section}
    {_try_it_section(companies)}
    {_trust_section()}
  </main>
  <footer>
    <p><strong>{_esc(DISCLAIMER.replace('**', ''))}</strong></p>
    <p>Herramienta de investigación, no es asesoría financiera. No sugiere comprar ni vender.</p>
  </footer>
  <script>{_SCRIPT}</script>
</body>
</html>
"""
