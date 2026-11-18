"""Página web del reporte (adicional, fuera del alcance original del MVP,
ver SPEC.md sección 3). Es un único archivo
HTML autocontenido y estático: no hay backend, no hay formularios, no se
guarda nada en el navegador. Blanco y azul claro, con animaciones ligeras
que respetan `prefers-reduced-motion`.

Reglas de seguridad (skill frontend-seguro) aplicadas:
- Todo texto dinámico pasa por `html.escape` antes de insertarse — defensa
  en profundidad, porque las citas vienen del documento oficial, que todo
  el proyecto trata como dato no confiable (nunca como instrucción).
- CSP estricta vía `<meta>`: sin scripts externos, sin fuentes externas,
  sin `eval`/`Function`/`innerHTML`. El único `<script>` usa
  `textContent`/`addEventListener`, nunca HTML armado a mano.
- Nunca sugiere comprar ni vender; mismo pie de no asesoría que el Markdown
  de `report/report.py`, cuyo catálogo de conceptos reutiliza (una sola
  fuente de verdad sobre qué cifras existen y en qué orden).
"""

from __future__ import annotations

import html as _html
from datetime import datetime, timezone

from calc.fcf import CagrResult, FcfResult
from extract.facts import CitedValue
from report.report import DISCLAIMER, _DISPLAY_ORDER

_CSP = (
    "default-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "img-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
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


def _figure_card(key: str, label: str, cv: CitedValue) -> str:
    if cv.no_verificado:
        detail = _esc(cv.nota) or "Sin fuente suficiente; no se usó en ningún cálculo."
    elif cv.derivado:
        detail = _esc(cv.nota) or "Calculado a partir de otras cifras de esta misma tabla."
    else:
        detail = (
            f"{_esc(cv.citation.doc_id)} · {_esc(cv.citation.seccion)}"
            f"<blockquote>{_esc(cv.citation.frase_exacta)}</blockquote>"
        )
    return f"""
      <article class="card reveal" data-key="{_esc(key)}">
        <header class="card-head">
          <h3>{_esc(label)}</h3>
          {_badge(cv)}
        </header>
        <p class="card-value">{_esc(_fmt_money(cv.value))}</p>
        <details class="card-detail">
          <summary>Ver fuente</summary>
          <div>{detail}</div>
        </details>
      </article>"""


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
    return f"""
    <section class="calc-grid" aria-label="Cálculos">
      <article class="card reveal">
        <h3>FCF</h3>
        <p class="card-value">{_esc(_fmt_money(fcf.value))}</p>
        <p class="card-note">{_esc(fcf.nota)}</p>
      </article>
      <article class="card reveal">
        <h3>CAGR de ingresos</h3>
        <p class="card-value">{_esc(cagr_text)}</p>
        <p class="card-note">{_esc(cagr.nota)}</p>
      </article>
    </section>"""


def build_html_report(
    *,
    empresa_ejemplo: str,
    filing_doc_id: str,
    verified: dict,
    fcf: FcfResult,
    cagr: CagrResult,
    resumen_cambios: str | None = None,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    cards = "".join(_figure_card(key, label, verified[key]) for key, label in _DISPLAY_ORDER)
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
<style>
  :root {{
    --bg: #ffffff;
    --surface: #eef5ff;
    --surface-2: #dbeafe;
    --accent: #2563eb;
    --accent-dark: #1e40af;
    --text: #0f172a;
    --muted: #51607a;
    --warn-bg: #fff7ed;
    --warn-border: #f59e0b;
    --radius: 14px;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
  }}
  a {{ color: var(--accent-dark); }}
  header.top {{
    background: linear-gradient(135deg, var(--accent) 0%, #60a5fa 100%);
    color: #ffffff;
    padding: 2rem 1.5rem;
  }}
  header.top h1 {{ margin: 0 0 .25rem; font-size: 1.6rem; }}
  header.top p {{ margin: 0; opacity: .9; font-size: .9rem; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 1.5rem; }}
  section {{ margin-bottom: 1.75rem; }}
  h2 {{ color: var(--accent-dark); font-size: 1.15rem; }}
  .risk {{
    background: var(--warn-bg);
    border-left: 4px solid var(--warn-border);
    border-radius: var(--radius);
    padding: 1.25rem 1.5rem;
  }}
  .risk ul {{ margin: .5rem 0; padding-left: 1.25rem; }}
  .risk-note {{ color: var(--muted); font-size: .9rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
  .calc-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--surface-2);
    border-radius: var(--radius);
    padding: 1rem 1.1rem;
  }}
  .card-head {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; }}
  .card h3 {{ margin: 0; font-size: .95rem; color: var(--text); }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; margin: .4rem 0; color: var(--accent-dark); }}
  .card-note {{ color: var(--muted); font-size: .85rem; margin: 0; }}
  .card-detail summary {{ cursor: pointer; color: var(--accent-dark); font-size: .85rem; }}
  .card-detail summary:focus-visible, a:focus-visible, button:focus-visible {{
    outline: 3px solid var(--accent); outline-offset: 2px;
  }}
  .card-detail div {{ font-size: .85rem; color: var(--muted); margin-top: .4rem; }}
  .card-detail blockquote {{
    margin: .4rem 0 0; padding: .5rem .75rem; background: #ffffff;
    border-left: 3px solid var(--accent); border-radius: 6px; font-style: italic;
  }}
  .badge {{ font-size: .7rem; padding: .15rem .5rem; border-radius: 999px; white-space: nowrap; }}
  .badge-ok {{ background: #dcfce7; color: #166534; }}
  .badge-info {{ background: #dbeafe; color: #1e40af; }}
  .badge-warn {{ background: #fef3c7; color: #92400e; }}
  .cambios-body {{ white-space: pre-line; }}
  footer {{
    text-align: center; color: var(--muted); font-size: .85rem;
    padding: 1.5rem; border-top: 1px solid var(--surface-2);
  }}
  footer strong {{ color: var(--text); }}
  .reveal {{ opacity: 0; transform: translateY(10px); transition: opacity .5s ease, transform .5s ease; }}
  .reveal.is-visible {{ opacity: 1; transform: none; }}
  @media (prefers-reduced-motion: reduce) {{
    .reveal {{ opacity: 1; transform: none; transition: none; }}
  }}
</style>
</head>
<body>
  <header class="top">
    <h1>{_esc(empresa_ejemplo)}</h1>
    <p>Reporte de {_esc(filing_doc_id)} · generado {_esc(generated_at.strftime('%Y-%m-%d %H:%M UTC'))}</p>
  </header>
  <main>
    {_risk_banner(verified, fcf)}
    <section aria-label="Cifras con fuente">
      <h2>📊 Cifras con fuente</h2>
      <div class="grid">{cards}
      </div>
    </section>
    <section aria-label="Cálculos">
      <h2>🧮 Cálculos</h2>
      {_calc_cards(fcf, cagr)}
    </section>
    {cambios_section}
  </main>
  <footer>
    <p><strong>{_esc(DISCLAIMER.replace('**', ''))}</strong></p>
    <p>Herramienta de investigación, no es asesoría financiera. No sugiere comprar ni vender.</p>
  </footer>
  <script>
  (function () {{
    "use strict";
    var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var items = document.querySelectorAll(".reveal");
    if (prefersReduced || !("IntersectionObserver" in window)) {{
      items.forEach(function (el) {{ el.classList.add("is-visible"); }});
      return;
    }}
    var observer = new IntersectionObserver(function (entries) {{
      entries.forEach(function (entry) {{
        if (entry.isIntersecting) {{
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }}
      }});
    }}, {{ threshold: 0.15 }});
    items.forEach(function (el) {{ observer.observe(el); }});
  }})();
  </script>
</body>
</html>
"""
