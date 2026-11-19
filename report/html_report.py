"""Página web del reporte (adicional, fuera del alcance original del MVP,
ver SPEC.md sección 3). Es un único archivo HTML autocontenido y estático:
no hay backend, no hay formularios, no se guarda nada en el navegador.
Diseño v3 (Capa A hechos verificados · Capa B simulación · Diario), oscuro con fondo animado
(brillos violeta/menta, a pedido explícito de un look de tablero más vistoso), con tipografías
embebidas (Manrope, Instrument Serif, IBM Plex Mono), widgets de TradingView en iframes
aislados, un asistente flotante de respuestas preparadas, animada, y pensada para explicar el sistema de
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
from pathlib import Path

from calc.fcf import CagrResult, FcfResult
from extract.facts import CitedValue
from report.report import DISCLAIMER, _DISPLAY_ORDER

_REPO_URL = "https://github.com/Hsoja/quant-lab"

_ASSETS = Path(__file__).resolve().parent / "assets"

# Tipografías embebidas como data: URI (licencia OFL, ver assets/fonts/LICENSES.md):
# la página sigue siendo un solo archivo y no carga nada de ningún host de fuentes.
_FONT_FACES = (
    ("Manrope", "normal", "200 800", "manrope-var.woff2"),
    ("Instrument Serif", "normal", "400", "instrument-serif.woff2"),
    ("Instrument Serif", "italic", "400", "instrument-serif-italic.woff2"),
    ("IBM Plex Mono", "normal", "500", "ibm-plex-mono-500.woff2"),
)


def _font_css() -> str:
    rules = []
    for family, style, weight, filename in _FONT_FACES:
        data = base64.b64encode((_ASSETS / "fonts" / filename).read_bytes()).decode("ascii")
        rules.append(
            f'@font-face {{ font-family: "{family}"; font-style: {style}; font-weight: {weight}; '
            f"font-display: swap; src: url(data:font/woff2;base64,{data}) format(\"woff2\"); }}"
        )
    return "\n".join(rules)

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

  // --- TradingView: iframes aislados con sandbox. La configuración viaja en
  // el hash (#...), que el navegador NUNCA envía al servidor; el patrón es el
  // mismo que usa TradePro. Nunca se carga un <script> de TradingView.
  var TV_BASE = "https://www.tradingview-widget.com/embed-widget/";
  function tvFrame(widget, config, title, extraClass, locale) {
    var frame = document.createElement("iframe");
    frame.className = "live-frame" + (extraClass ? " " + extraClass : "");
    frame.src = TV_BASE + widget + "/?locale=" + (locale || "es") + "#" + encodeURIComponent(JSON.stringify(config));
    frame.loading = "lazy";
    frame.title = title;
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox");
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    return frame;
  }


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

    // Gráfica y noticias en vivo: iframes aislados de TradingView (ver tvFrame).
    // El símbolo se valida antes de armar la configuración, aunque hoy
    // siempre venga de nuestros propios datos.
    var SYMBOL_PATTERN = /^[A-Z]+:[A-Z.]{1,10}$/;

    function liveCard(titleText, frame, extraClass) {
      var card = document.createElement("div");
      card.className = "card live-card" + (extraClass ? " " + extraClass : "");
      var h = document.createElement("h4");
      h.textContent = titleText;
      card.appendChild(h);
      card.appendChild(frame);
      return card;
    }

    function liveSection(ticker, symbol) {
      var block = document.createElement("div");
      block.className = "live-block";

      var head = document.createElement("div");
      head.className = "live-block-head";
      var title = document.createElement("h3");
      title.textContent = "Mercado en vivo · " + symbol;
      head.appendChild(title);
      var ext = document.createElement("span");
      ext.className = "live-ext";
      ext.textContent = "externo · no verificado";
      head.appendChild(ext);
      block.appendChild(head);

      var wrap = document.createElement("div");
      wrap.className = "try-it-live";

      wrap.appendChild(liveCard(
        "Gráfica interactiva",
        tvFrame("advanced-chart", {
          autosize: true, symbol: symbol, interval: "D", timezone: "America/Toronto",
          theme: "dark", style: "1", locale: "es", allow_symbol_change: false,
          hide_side_toolbar: true, withdateranges: true, save_image: false,
          backgroundColor: "rgba(13, 15, 30, 0)", gridColor: "rgba(148, 160, 255, 0.06)",
          support_host: "https://www.tradingview-widget.com"
        }, "Gráfica interactiva de " + ticker, "live-frame-main"),
        "live-wide"
      ));
      wrap.appendChild(liveCard(
        "Rangos de precio",
        tvFrame("symbol-overview", {
          symbols: [[ticker, symbol + "|1D"]], chartOnly: false, width: "100%", height: "100%",
          locale: "es", colorTheme: "dark", autosize: true, showVolume: false, showMA: false,
          hideDateRanges: false, hideMarketStatus: false, hideSymbolLogo: false,
          scalePosition: "right", scaleMode: "Normal", fontSize: "10", noTimeScale: false,
          valuesTracking: "1", changeMode: "price-and-percent", chartType: "area",
          lineWidth: 2, lineType: 0, isTransparent: true,
          backgroundColor: "rgba(13, 15, 30, 0)",
          topColor: "rgba(123, 108, 255, 0.35)", bottomColor: "rgba(123, 108, 255, 0)", lineColor: "#9a8fff"
        }, "Rangos de precio de " + ticker, "live-frame-chart")
      ));
      wrap.appendChild(liveCard(
        "Noticias de mercado (en inglés)",
        // El feed de noticias de TradingView solo responde con locale=en (con es muestra un error).
        tvFrame("timeline", {
          width: "100%", height: "100%", colorTheme: "dark", isTransparent: true,
          feedMode: "symbol", symbol: symbol, displayMode: "regular"
        }, "Noticias en vivo de " + ticker, "live-frame-news", "en")
      ));

      var note = document.createElement("p");
      note.className = "live-note";
      note.textContent = "Widgets externos de TradingView, no verificados por este proyecto — úsalos solo como referencia visual; los precios pueden ir con retraso.";
      wrap.appendChild(note);
      block.appendChild(wrap);
      return block;
    }

    // Chat de preguntas ya preparadas (nunca un chat en vivo: SPEC.md 9.6).
    function askQuestion(chatLog, qa) {
      var userBubble = document.createElement("div");
      userBubble.className = "chat-bubble chat-bubble-user";
      userBubble.textContent = qa.pregunta;
      chatLog.appendChild(userBubble);

      var botBubble = document.createElement("div");
      botBubble.className = "chat-bubble chat-bubble-bot thinking";
      botBubble.textContent = "🤖 Pensando…";
      chatLog.appendChild(botBubble);
      if (botBubble.scrollIntoView) {
        botBubble.scrollIntoView({ behavior: prefersReduced ? "auto" : "smooth", block: "nearest" });
      }

      window.setTimeout(
        function () {
          botBubble.classList.remove("thinking");
          botBubble.textContent = qa.respuesta;
        },
        prefersReduced ? 0 : 750
      );
    }

    function chatSection(ticker, qaList) {
      var card = document.createElement("div");
      card.className = "chat-card";

      var head = document.createElement("div");
      head.className = "chat-head";
      var avatar = document.createElement("span");
      avatar.className = "bot-avatar bot-avatar-sm";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = "🤖";
      head.appendChild(avatar);
      var headTitle = document.createElement("strong");
      headTitle.textContent = "Pregúntale al pipeline sobre " + ticker;
      head.appendChild(headTitle);
      card.appendChild(head);

      var warn = document.createElement("p");
      warn.className = "chat-warn";
      warn.textContent =
        "Respuestas ya preparadas con las cifras de arriba — no es un chat en vivo, nunca dice " +
        '"compra" ni "vende".';
      card.appendChild(warn);

      var log = document.createElement("div");
      log.className = "chat-log";
      card.appendChild(log);

      var buttons = document.createElement("div");
      buttons.className = "chat-buttons";
      qaList.forEach(function (qa) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chat-question-btn";
        btn.textContent = qa.pregunta;
        btn.addEventListener("click", function () {
          askQuestion(log, qa);
          btn.disabled = true;
        });
        buttons.appendChild(btn);
      });
      card.appendChild(buttons);

      return card;
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

          if (company.tradingview_symbol && SYMBOL_PATTERN.test(company.tradingview_symbol)) {
            resultEl.appendChild(liveSection(ticker, company.tradingview_symbol));
          }
          if (company.qa && company.qa.length) {
            resultEl.appendChild(chatSection(ticker, company.qa));
          }
          document.dispatchEvent(new CustomEvent("company-chosen", { detail: { ticker: ticker, qa: company.qa || [] } }));
        },
        prefersReduced ? 0 : 650
      );
    }

    select.addEventListener("change", function () {
      if (select.value) renderResult(select.value);
      else clear(resultEl);
    });
  })();

  // --- Motor Monte Carlo (GBM) — Capa B, SIMULADO -------------------------
  // S[t+1] = S[t] * exp((mu - sigma^2/2) dt + sigma sqrt(dt) Z), dt = 1/252.
  // Misma fórmula que calc/montecarlo.py. PRNG con semilla (mulberry32): el
  // mismo conjunto de supuestos y semilla da siempre el mismo resultado.
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gaussian(rng) {
    var u = 0;
    while (u === 0) u = rng();
    var v = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  function percentile(sorted, p) {
    var idx = (sorted.length - 1) * p;
    var lo = Math.floor(idx);
    var hi = Math.ceil(idx);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }
  function simulateGBM(p) {
    var dt = 1 / 252;
    var drift = (p.mu - (p.sigma * p.sigma) / 2) * dt;
    var vol = p.sigma * Math.sqrt(dt);
    var rng = mulberry32(p.seed);
    var nPoints = Math.min(p.days, 60);
    var stepIdx = [];
    for (var i = 0; i <= nPoints; i++) stepIdx.push(Math.round((i * p.days) / nPoints));
    var series = stepIdx.map(function () { return new Float64Array(p.paths); });
    var finals = new Float64Array(p.paths);
    for (var path = 0; path < p.paths; path++) {
      var logS = Math.log(p.s0);
      series[0][path] = p.s0;
      var k = 1;
      for (var d = 1; d <= p.days; d++) {
        logS += drift + vol * gaussian(rng);
        if (d === stepIdx[k]) {
          series[k][path] = Math.exp(logS);
          k++;
        }
      }
      finals[path] = Math.exp(logS);
    }
    return { params: p, stepIdx: stepIdx, series: series, finals: finals };
  }
  function summarize(sim) {
    var p = sim.params;
    var scale = p.capital / p.s0;
    var values = Array.prototype.slice.call(sim.finals).map(function (x) { return x * scale; });
    values.sort(function (a, b) { return a - b; });
    var n = values.length;
    function share(pred) {
      var c = 0;
      for (var i = 0; i < n; i++) if (pred(values[i])) c++;
      return c / n;
    }
    var p5 = percentile(values, 0.05);
    var bands = sim.series.map(function (col) {
      var s = Array.prototype.slice.call(col).map(function (x) { return x * scale; });
      s.sort(function (a, b) { return a - b; });
      return [0.05, 0.25, 0.5, 0.75, 0.95].map(function (q) { return percentile(s, q); });
    });
    var lo = percentile(values, 0.01);
    var hi = percentile(values, 0.99);
    var nBins = 30;
    var width = (hi - lo) / nBins || 1;
    var bins = [];
    for (var b = 0; b < nBins; b++) bins.push(0);
    values.forEach(function (v) {
      var idx = Math.floor((v - lo) / width);
      if (idx < 0) idx = 0;
      if (idx >= nBins) idx = nBins - 1;
      bins[idx]++;
    });
    var samplePaths = [];
    for (var s = 0; s < Math.min(25, p.paths); s++) {
      samplePaths.push(sim.series.map(function (col) { return col[s] * scale; }));
    }
    return {
      capital: p.capital,
      pUp: share(function (v) { return v > p.capital; }),
      pLoss10: share(function (v) { return v < p.capital * 0.9; }),
      pGain20: share(function (v) { return v > p.capital * 1.2; }),
      p5: p5,
      p50: percentile(values, 0.5),
      p95: percentile(values, 0.95),
      var95: Math.max(0, p.capital - p5),
      bands: bands,
      stepIdx: sim.stepIdx,
      samplePaths: samplePaths,
      hist: { lo: lo, width: width, bins: bins }
    };
  }

  // --- Panel de simulación (Capa B) y diario de decisiones ----------------
  // Todo con createElement/createElementNS y textContent; los supuestos se
  // validan y acotan antes de simular. Nada sale del navegador.
  (function () {
    var runBtn = document.getElementById("mc-run");
    if (!runBtn) return;
    var NS = "http://www.w3.org/2000/svg";
    var sourceSel = document.getElementById("mc-source");
    var fields = {
      s0: document.getElementById("mc-s0"),
      mu: document.getElementById("mc-mu"),
      sigma: document.getElementById("mc-sigma"),
      days: document.getElementById("mc-days"),
      paths: document.getElementById("mc-paths"),
      capital: document.getElementById("mc-capital"),
      seed: document.getElementById("mc-seed")
    };
    var errorEl = document.getElementById("mc-error");
    var metaEl = document.getElementById("mc-meta");
    var resultsEl = document.getElementById("mc-results");
    var lastSummary = null;

    var dataEl = document.getElementById("companies-data");
    var companies = {};
    try { companies = JSON.parse((dataEl && dataEl.getAttribute("data-json")) || "{}"); } catch (e) { companies = {}; }
    Object.keys(companies).sort().forEach(function (ticker) {
      var mc = companies[ticker].monte_carlo;
      if (!mc) return;
      var opt = document.createElement("option");
      opt.value = ticker;
      opt.textContent = ticker + " — μ y σ históricos";
      sourceSel.appendChild(opt);
    });

    function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
    function el(tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    }
    function svgEl(tag, attrs, cls) {
      var n = document.createElementNS(NS, tag);
      Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, String(attrs[k])); });
      if (cls) n.setAttribute("class", cls);
      return n;
    }
    function usd(v) { return "US$ " + Math.round(v).toLocaleString("en-US"); }
    function pctText(v) { return (v * 100).toFixed(0) + "%"; }

    function applySource() {
      var t = sourceSel.value;
      metaEl.textContent = "";
      if (t && companies[t] && companies[t].monte_carlo) {
        var mc = companies[t].monte_carlo;
        fields.s0.value = mc.s0.toFixed(2);
        fields.mu.value = (mc.mu * 100).toFixed(1);
        fields.sigma.value = (mc.sigma * 100).toFixed(1);
        metaEl.textContent =
          "μ y σ calculados de " + mc.n_obs + " retornos diarios hasta " + mc.as_of + " — " + mc.source +
          ". Huella de la respuesta: " + String(mc.source_hash).slice(0, 12) + "… (histórico: no garantiza nada hacia adelante).";
      } else {
        fields.s0.value = "100";
        fields.mu.value = "8";
        fields.sigma.value = "25";
        metaEl.textContent =
          "Supuestos manuales de ejemplo: NO verificados y NO son de ninguna empresa. Cámbialos por los tuyos.";
      }
    }
    sourceSel.addEventListener("change", applySource);
    applySource();

    function readParams() {
      function num(name) { return Number(fields[name].value); }
      var p = {
        s0: num("s0"), mu: num("mu") / 100, sigma: num("sigma") / 100,
        days: Math.round(num("days")), paths: Math.round(num("paths")),
        capital: num("capital"), seed: Math.round(num("seed"))
      };
      var problems = [];
      if (!(p.s0 > 0 && p.s0 <= 1e7)) problems.push("Precio inicial: entre 0 y 10,000,000.");
      if (!(p.mu >= -1 && p.mu <= 2)) problems.push("μ: entre -100% y 200%.");
      if (!(p.sigma > 0 && p.sigma <= 3)) problems.push("σ: mayor que 0 y hasta 300%.");
      if (!(p.days >= 1 && p.days <= 756)) problems.push("Días: entre 1 y 756.");
      if (!(p.paths >= 100 && p.paths <= 5000)) problems.push("Simulaciones: entre 100 y 5,000.");
      if (!(p.capital > 0 && p.capital <= 1e9)) problems.push("Capital: entre 0 y 1,000,000,000.");
      if (!isFinite(p.seed)) problems.push("Semilla: un número entero.");
      return { p: p, problems: problems };
    }

    function statCard(label, value, note, cls) {
      var c = el("div", "mc-stat " + (cls || ""));
      c.appendChild(el("p", "mc-stat-label", label));
      c.appendChild(el("p", "mc-stat-value", value));
      if (note) c.appendChild(el("p", "mc-stat-note", note));
      return c;
    }

    function fanChart(s, days) {
      var W = 640, H = 280, L = 56, R = 12, T = 12, B = 28;
      var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img" }, "mc-chart");
      svg.setAttribute("aria-label", "Trayectorias simuladas del capital con bandas P5-P95");
      var all = [];
      s.bands.forEach(function (b) { all.push(b[0], b[4]); });
      s.samplePaths.forEach(function (sp) { sp.forEach(function (v) { all.push(v); }); });
      var yMin = Math.min.apply(null, all.concat([s.capital]));
      var yMax = Math.max.apply(null, all.concat([s.capital]));
      var span = yMax - yMin || 1;
      function X(d) { return L + ((W - L - R) * d) / days; }
      function Y(v) { return T + (H - T - B) * (1 - (v - yMin) / span); }
      function path(vals) {
        return vals.map(function (v, i) { return (i ? "L" : "M") + X(s.stepIdx[i]).toFixed(1) + "," + Y(v).toFixed(1); }).join(" ");
      }
      var upper = s.bands.map(function (b) { return b[4]; });
      var lower = s.bands.map(function (b) { return b[0]; });
      var upper2 = s.bands.map(function (b) { return b[3]; });
      var lower2 = s.bands.map(function (b) { return b[1]; });
      function area(top, bottom) {
        var fwd = top.map(function (v, i) { return (i ? "L" : "M") + X(s.stepIdx[i]).toFixed(1) + "," + Y(v).toFixed(1); }).join(" ");
        var back = bottom.map(function (v, i) { return "L" + X(s.stepIdx[bottom.length - 1 - i]).toFixed(1) + "," + Y(bottom[bottom.length - 1 - i]).toFixed(1); }).join(" ");
        return fwd + " " + back + " Z";
      }
      svg.appendChild(svgEl("path", { d: area(upper, lower) }, "mc-band-outer"));
      svg.appendChild(svgEl("path", { d: area(upper2, lower2) }, "mc-band-inner"));
      s.samplePaths.forEach(function (sp) { svg.appendChild(svgEl("path", { d: path(sp) }, "mc-path")); });
      svg.appendChild(svgEl("path", { d: path(s.bands.map(function (b) { return b[2]; })) }, "mc-median"));
      svg.appendChild(svgEl("line", { x1: L, x2: W - R, y1: Y(s.capital), y2: Y(s.capital) }, "mc-capital-line"));
      [[yMax, T + 4], [s.capital, Y(s.capital) - 4], [yMin, H - B - 2]].forEach(function (pair) {
        var t = svgEl("text", { x: L - 6, y: pair[1], "text-anchor": "end" }, "mc-axis");
        t.textContent = usd(pair[0]);
        svg.appendChild(t);
      });
      [[0, "start", "día 0"], [days, "end", "día " + days]].forEach(function (a) {
        var t = svgEl("text", { x: a[0] === 0 ? L : W - R, y: H - 8, "text-anchor": a[1] }, "mc-axis");
        t.textContent = a[2];
        svg.appendChild(t);
      });
      return svg;
    }

    function histChart(s) {
      var W = 640, H = 200, L = 12, R = 12, T = 10, B = 28;
      var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img" }, "mc-chart");
      svg.setAttribute("aria-label", "Distribución simulada del valor final");
      var bins = s.hist.bins;
      var max = Math.max.apply(null, bins) || 1;
      var bw = (W - L - R) / bins.length;
      bins.forEach(function (count, i) {
        var h = ((H - T - B) * count) / max;
        var mid = s.hist.lo + s.hist.width * (i + 0.5);
        svg.appendChild(svgEl("rect", {
          x: (L + i * bw + 1).toFixed(1), y: (H - B - h).toFixed(1),
          width: Math.max(bw - 2, 1).toFixed(1), height: h.toFixed(1)
        }, mid < s.capital ? "mc-bar-loss" : "mc-bar-gain"));
      });
      var cx = L + ((s.capital - s.hist.lo) / (s.hist.width * bins.length)) * (W - L - R);
      if (cx >= L && cx <= W - R) svg.appendChild(svgEl("line", { x1: cx, x2: cx, y1: T, y2: H - B }, "mc-capital-line"));
      [[L, "start", usd(s.hist.lo)], [W - R, "end", usd(s.hist.lo + s.hist.width * bins.length)]].forEach(function (a) {
        var t = svgEl("text", { x: a[0], y: H - 8, "text-anchor": a[1] }, "mc-axis");
        t.textContent = a[2];
        svg.appendChild(t);
      });
      return svg;
    }

    function render(s, p) {
      clear(resultsEl);
      lastSummary = { s: s, p: p };
      var riskRow = el("div", "mc-stats");
      riskRow.appendChild(statCard("Prob. de perder más de 10%", pctText(s.pLoss10), "Riesgo primero", "mc-risk"));
      riskRow.appendChild(statCard("Pérdida en el peor 5% (VaR 95%)", usd(s.var95), "Simulada, no garantizada", "mc-risk"));
      riskRow.appendChild(statCard("Prob. de terminar arriba", pctText(s.pUp), "Valor final > capital inicial"));
      riskRow.appendChild(statCard("Prob. de ganar más de 20%", pctText(s.pGain20), "Escenario optimista"));
      resultsEl.appendChild(riskRow);
      var pr = el("div", "mc-stats mc-stats-3");
      pr.appendChild(statCard("P5 (escenario malo)", usd(s.p5), "5% termina por debajo"));
      pr.appendChild(statCard("P50 (mediana)", usd(s.p50), "La mitad termina por debajo"));
      pr.appendChild(statCard("P95 (escenario bueno)", usd(s.p95), "5% termina por encima"));
      resultsEl.appendChild(pr);
      var f1 = el("figure", "mc-figure");
      f1.appendChild(el("figcaption", "", "Trayectorias simuladas (" + p.paths + " en total; se dibujan 25) y bandas P5–P95 / P25–P75"));
      f1.appendChild(fanChart(s, p.days));
      resultsEl.appendChild(f1);
      var f2 = el("figure", "mc-figure");
      f2.appendChild(el("figcaption", "", "Distribución del valor final (rojo: por debajo del capital inicial)"));
      f2.appendChild(histChart(s));
      resultsEl.appendChild(f2);
      document.dispatchEvent(new CustomEvent("mc-updated"));
    }

    runBtn.addEventListener("click", function () {
      var r = readParams();
      if (r.problems.length) {
        errorEl.textContent = r.problems.join(" ");
        return;
      }
      errorEl.textContent = "";
      runBtn.disabled = true;
      window.setTimeout(function () {
        render(summarize(simulateGBM(r.p)), r.p);
        runBtn.disabled = false;
      }, 0);
    });

    window.__qlLastSim = function () { return lastSummary; };
  })();

  (function () {
    var factSel = document.getElementById("diary-fact");
    var scenSel = document.getElementById("diary-scenario");
    var noteEl = document.getElementById("diary-note");
    var previewEl = document.getElementById("diary-preview");
    var copyBtn = document.getElementById("diary-copy");
    var dlBtn = document.getElementById("diary-download");
    var statusEl = document.getElementById("diary-status");
    if (!factSel || !scenSel || !noteEl || !previewEl) return;

    function usd(v) { return "US$ " + Math.round(v).toLocaleString("en-US"); }

    document.querySelectorAll("[data-figure-label]").forEach(function (card) {
      var opt = document.createElement("option");
      opt.value = card.getAttribute("data-figure-label");
      opt.textContent = card.getAttribute("data-figure-label");
      factSel.appendChild(opt);
    });

    function refreshScenarios() {
      var keep = scenSel.value;
      while (scenSel.options.length > 1) scenSel.remove(1);
      var last = window.__qlLastSim && window.__qlLastSim();
      if (last) {
        [["P5 (escenario malo)", last.s.p5], ["P50 (mediana)", last.s.p50], ["P95 (escenario bueno)", last.s.p95]].forEach(function (pair) {
          var opt = document.createElement("option");
          opt.value = pair[0] + " = " + usd(pair[1]) + " en " + last.p.days + " días (SIMULADO)";
          opt.textContent = pair[0] + " — " + usd(pair[1]);
          scenSel.appendChild(opt);
        });
      }
      scenSel.value = keep && Array.prototype.some.call(scenSel.options, function (o) { return o.value === keep; }) ? keep : "";
    }
    document.addEventListener("mc-updated", function () { refreshScenarios(); build(); });

    function posture() {
      var r = document.querySelector('input[name="diary-posture"]:checked');
      return r ? r.value : "Sin definir";
    }

    function build() {
      var today = new Date().toISOString().slice(0, 10);
      var last = window.__qlLastSim && window.__qlLastSim();
      var lines = [
        "# Diario de decisiones — " + today,
        "",
        "## Hecho verificado (Capa A)",
        factSel.value || "(ninguno elegido)",
        "",
        "## Escenario simulado (Capa B)",
        scenSel.value || "(ninguno elegido)"
      ];
      if (last) {
        lines.push("Supuestos: precio inicial " + last.p.s0 + ", μ " + (last.p.mu * 100).toFixed(1) + "%, σ " +
          (last.p.sigma * 100).toFixed(1) + "%, " + last.p.days + " días, " + last.p.paths + " simulaciones, semilla " + last.p.seed + ".");
      }
      lines.push("", "## Mi postura", posture(), "", "## Mi razonamiento", noteEl.value || "(vacío)", "",
        "---", "Análisis informativo, no asesoría financiera. La decisión es tuya.", "");
      previewEl.value = lines.join("\\n");
    }
    [factSel, scenSel, noteEl].forEach(function (n) { n.addEventListener("input", build); n.addEventListener("change", build); });
    document.querySelectorAll('input[name="diary-posture"]').forEach(function (r) { r.addEventListener("change", build); });
    build();

    function say(msg) { statusEl.textContent = msg; }

    copyBtn.addEventListener("click", function () {
      build();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(previewEl.value).then(
          function () { say("Copiado. Pégalo donde guardes tu diario (por ejemplo, Notion)."); },
          function () { previewEl.select(); say("No se pudo copiar solo: el texto quedó seleccionado, copia con Ctrl/Cmd+C."); }
        );
      } else {
        previewEl.select();
        say("Este navegador no permite copiar solo: copia el texto seleccionado con Ctrl/Cmd+C.");
      }
    });

    dlBtn.addEventListener("click", function () {
      build();
      var blob = new Blob([previewEl.value], { type: "text/markdown;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "diario-" + new Date().toISOString().slice(0, 10) + ".md";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      say("Descargado. Esta página no guarda nada: tu texto solo vive en el archivo que descargas.");
    });
  })();

  // --- Reloj UTC, spotlight, navegación activa y cinta de TradingView --------
  (function () {
    var clockEl = document.getElementById("clock");
    if (clockEl) {
      var tick = function () { clockEl.textContent = new Date().toISOString().slice(11, 19) + " UTC"; };
      tick();
      window.setInterval(tick, 1000);
    }
    document.querySelectorAll(".spot").forEach(function (node) {
      node.addEventListener("pointermove", function (ev) {
        var r = node.getBoundingClientRect();
        node.style.setProperty("--mx", (ev.clientX - r.left) + "px");
        node.style.setProperty("--my", (ev.clientY - r.top) + "px");
      });
    });
    var links = document.querySelectorAll('.nav a[href^="#"]');
    if ("IntersectionObserver" in window && links.length) {
      var byId = {};
      links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
      var spy = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting && byId[en.target.id]) {
            links.forEach(function (a) { a.classList.remove("is-active"); });
            byId[en.target.id].classList.add("is-active");
          }
        });
      }, { rootMargin: "-35% 0px -55% 0px" });
      Object.keys(byId).forEach(function (id) {
        var s = document.getElementById(id);
        if (s) spy.observe(s);
      });
    }
    var tape = document.getElementById("ticker");
    if (tape) {
      var symbols = [
        ["FOREXCOM:SPXUSD", "S&P 500"], ["FOREXCOM:NSXUSD", "Nasdaq 100"], ["FOREXCOM:DJI", "Dow"],
        ["NYSE:SPGI", "SPGI"], ["NASDAQ:COST", "COST"], ["NASDAQ:AAPL", "AAPL"], ["NYSE:UBER", "UBER"],
        ["BITSTAMP:BTCUSD", "Bitcoin"], ["OANDA:XAUUSD", "Oro"], ["FX:USDCAD", "USD/CAD"]
      ].map(function (p) { return { proName: p[0], title: p[1] }; });
      tape.appendChild(tvFrame("ticker-tape", {
        width: "100%", height: "100%", colorTheme: "dark", isTransparent: true,
        symbols: symbols, showSymbolLogo: true, displayMode: "adaptive"
      }, "Cinta de precios de TradingView", ""));
    }
  })();

  // Constelación de fondo (solo decorativa): partículas lentas unidas por
  // líneas finas. Se detiene con la pestaña oculta y no corre con
  // prefers-reduced-motion.
  (function () {
    var cv = document.getElementById("bg-canvas");
    if (!cv || prefersReduced || !cv.getContext) return;
    var ctx = cv.getContext("2d");
    var W = 0, H = 0, dots = [];
    function resize() {
      W = cv.width = window.innerWidth;
      H = cv.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);
    for (var i = 0; i < 46; i++) {
      dots.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - 0.5) * 0.28, vy: (Math.random() - 0.5) * 0.28 });
    }
    function frame() {
      if (!document.hidden) {
        ctx.clearRect(0, 0, W, H);
        for (var a = 0; a < dots.length; a++) {
          var p = dots[a];
          p.x += p.vx; p.y += p.vy;
          if (p.x < 0 || p.x > W) p.vx *= -1;
          if (p.y < 0 || p.y > H) p.vy *= -1;
          ctx.fillStyle = "rgba(154, 143, 255, 0.7)";
          ctx.beginPath(); ctx.arc(p.x, p.y, 1.6, 0, 6.2832); ctx.fill();
          for (var b = a + 1; b < dots.length; b++) {
            var q = dots[b];
            var dx = p.x - q.x, dy = p.y - q.y, d2 = dx * dx + dy * dy;
            if (d2 < 19600) {
              ctx.strokeStyle = "rgba(123, 108, 255, " + (0.22 * (1 - d2 / 19600)).toFixed(3) + ")";
              ctx.lineWidth = 1;
              ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
            }
          }
        }
      }
      window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
  })();

  // --- Asistente flotante "Quant" (estilo Operativa) ------------------------
  // NO es un chat en vivo: no hay red, ni modelo, ni llave. Empareja tu
  // pregunta con respuestas redactadas al generar la página, a partir de las
  // mismas cifras verificadas. Si no hay respuesta preparada, dice que no la
  // tiene — nunca inventa. Todo con createElement/textContent.
  (function () {
    var fab = document.getElementById("bot-open");
    var drawer = document.getElementById("bot-drawer");
    var scrim = document.getElementById("bot-scrim");
    var closeBtn = document.getElementById("bot-close");
    var resetBtn = document.getElementById("bot-reset");
    var log = document.getElementById("bot-log");
    var chipsEl = document.getElementById("bot-chips");
    var input = document.getElementById("bot-input");
    var sendBtn = document.getElementById("bot-send");
    var dataEl = document.getElementById("bot-data");
    var orb = document.getElementById("bot-orb");
    var scroller = document.getElementById("bot-scroll");
    if (!fab || !drawer || !log || !input || !dataEl || !chipsEl) return;

    var kb = [];
    try { kb = JSON.parse(dataEl.getAttribute("data-kb") || "[]"); } catch (e) { kb = []; }
    var companyQa = [];
    var companyTicker = "";

    function norm(s) {
      return String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]/g, " ");
    }
    var STOP = " que una uno unos unas los las con por para del tan como cual cuales esta este esto estos son fue fueron hay ese esa mas muy pero les sus mis tus nos ser sobre donde cuando quien ";
    function tokens(s) {
      return norm(s).split(" ").filter(function (w) { return w.length > 2 && STOP.indexOf(" " + w + " ") === -1; });
    }

    var COMPANY_EXTRA = [
      ["ingresos", "crecimiento", "cagr", "ventas"],
      ["cara", "barata", "caro", "barato", "valoracion", "precio", "fcf", "yield", "multiplo"],
      ["riesgo", "riesgos", "invalidaria", "invalidar"]
    ];

    function best(question) {
      var q = tokens(question);
      var pool = [];
      companyQa.forEach(function (it) { pool.push({ item: it, bonus: 1 }); });
      kb.forEach(function (it) { pool.push({ item: it, bonus: 0 }); });
      var top = null, topScore = 0;
      pool.forEach(function (entry) {
        var kw = (entry.item.keywords || []).map(norm);
        var score = 0;
        q.forEach(function (w) {
          if (kw.indexOf(w) !== -1) { score += 2; return; }
          if (w.length > 4) {
            for (var i = 0; i < kw.length; i++) {
              if (kw[i].length > 4 && (kw[i].indexOf(w.slice(0, 5)) === 0)) { score += 1; break; }
            }
          }
        });
        if (score > 0) score += entry.bonus;
        if (score > topScore) { topScore = score; top = entry.item; }
      });
      return topScore >= 2 ? top : null;
    }

    function bubble(text, who) {
      var b = document.createElement("div");
      b.className = "chat-bubble chat-bubble-" + who;
      b.textContent = text;
      log.appendChild(b);
      toBottom();
      return b;
    }
    function toBottom() {
      if (scroller) scroller.scrollTop = scroller.scrollHeight;
    }
    function typing() {
      var b = document.createElement("div");
      b.className = "chat-bubble chat-bubble-bot";
      var d = document.createElement("span");
      d.className = "dots";
      for (var i = 0; i < 3; i++) d.appendChild(document.createElement("span"));
      b.appendChild(d);
      log.appendChild(b);
      toBottom();
      return b;
    }
    function typeInto(el, text) {
      if (prefersReduced) { el.textContent = text; toBottom(); return; }
      var i = 0;
      el.textContent = "";
      var iv = window.setInterval(function () {
        i += 3;
        el.textContent = text.slice(0, i);
        toBottom();
        if (i >= text.length) window.clearInterval(iv);
      }, 16);
    }

    function renderChips() {
      while (chipsEl.firstChild) chipsEl.removeChild(chipsEl.firstChild);
      var list = [];
      companyQa.forEach(function (it) { list.push(it); });
      kb.forEach(function (it) { if (list.length < 7) list.push(it); });
      list.slice(0, 7).forEach(function (it) {
        var c = document.createElement("button");
        c.type = "button";
        c.className = "chip";
        c.textContent = it.pregunta;
        c.addEventListener("click", function () { ask(it.pregunta, it); });
        chipsEl.appendChild(c);
      });
    }

    var FALLBACK = "No tengo una respuesta preparada para eso, y prefiero decir \\"no verificado\\" antes que inventar. Prueba con una de las preguntas de abajo.";

    function ask(text, direct) {
      var q = String(text).trim().slice(0, 200);
      if (!q) return;
      bubble(q, "user");
      var wait = typing();
      var item = direct || best(q);
      var answer = item ? item.respuesta : FALLBACK;
      window.setTimeout(function () {
        wait.textContent = "";
        typeInto(wait, answer);
      }, prefersReduced ? 0 : 700);
    }

    function greet() {
      while (log.firstChild) log.removeChild(log.firstChild);
      bubble("Hola, soy Quant. Respondo con textos ya preparados a partir de las cifras verificadas de esta página: no es un chat en vivo, no inventa números y nunca dice \\"compra\\" ni \\"vende\\".", "bot");
      renderChips();
    }
    greet();

    document.addEventListener("company-chosen", function (ev) {
      var d = ev.detail || {};
      companyTicker = String(d.ticker || "");
      companyQa = (d.qa || []).map(function (qa, i) {
        return {
          pregunta: qa.pregunta + " (" + companyTicker + ")",
          respuesta: qa.respuesta,
          keywords: tokens(qa.pregunta).concat(COMPANY_EXTRA[i] || [], [companyTicker.toLowerCase()])
        };
      });
      renderChips();
    });

    // Orbe de puntos (decorativo)
    var ctx = orb && orb.getContext ? orb.getContext("2d") : null;
    var pts = [];
    for (var i = 0; i < 380; i++) {
      var y = 1 - (i / 379) * 2;
      var r = Math.sqrt(1 - y * y);
      var th = Math.PI * (3 - Math.sqrt(5)) * i;
      pts.push([Math.cos(th) * r, y, Math.sin(th) * r]);
    }
    var angle = 0, raf = 0, open = false;
    function drawOrb() {
      if (!ctx) return;
      var w = orb.width, h = orb.height;
      ctx.clearRect(0, 0, w, h);
      var ca = Math.cos(angle), sa = Math.sin(angle);
      var R = w * 0.34;
      pts.forEach(function (p) {
        var x = p[0] * ca - p[2] * sa;
        var z = p[0] * sa + p[2] * ca;
        var f = 1.7 / (2.3 - z);
        var depth = (z + 1) / 2;
        ctx.fillStyle = "hsla(" + Math.round(255 - (p[1] + 1) * 52) + ", 90%, 72%, " + (0.2 + 0.8 * depth).toFixed(2) + ")";
        ctx.beginPath();
        ctx.arc(w / 2 + x * R * f, h / 2 + p[1] * R * f, 1 + 1.9 * depth, 0, 6.2832);
        ctx.fill();
      });
      angle += 0.007;
      if (open && !prefersReduced) raf = window.requestAnimationFrame(drawOrb);
    }

    function setOpen(state) {
      open = state;
      drawer.classList.toggle("is-open", state);
      scrim.classList.toggle("is-open", state);
      drawer.setAttribute("aria-hidden", state ? "false" : "true");
      fab.setAttribute("aria-expanded", state ? "true" : "false");
      if (state) {
        drawOrb();
        window.setTimeout(function () { input.focus(); }, 300);
      } else {
        window.cancelAnimationFrame(raf);
        fab.focus();
      }
    }
    fab.addEventListener("click", function () { setOpen(!open); });
    closeBtn.addEventListener("click", function () { setOpen(false); });
    scrim.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && open) setOpen(false); });
    resetBtn.addEventListener("click", greet);
    function submit() {
      var v = input.value;
      input.value = "";
      ask(v, null);
    }
    sendBtn.addEventListener("click", submit);
    input.addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); submit(); } });
    document.querySelectorAll("[data-open-bot]").forEach(function (b) {
      b.addEventListener("click", function () { setOpen(true); });
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

_TRADINGVIEW_ORIGIN = "https://www.tradingview-widget.com"

_CSP = (
    "default-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    f"script-src 'self' 'sha256-{_SCRIPT_HASH}'; "
    "img-src 'self'; "
    "font-src data:; "
    f"frame-src {_TRADINGVIEW_ORIGIN}; "
    "base-uri 'none'; "
    "form-action 'none'"
)

_STYLE = (_ASSETS / "style.css").read_text(encoding="utf-8").replace("/*FONTS*/", _font_css())

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

def _esc(value: object) -> str:
    if value is None:
        return ""
    return _html.escape(str(value), quote=True)


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "no verificado"
    return f"US$ {value:,.0f}"


def _fmt_money_short(value: float) -> str:
    abs_v = abs(value)
    if abs_v >= 1e9:
        return f"US$ {value / 1e9:.1f}B"
    if abs_v >= 1e6:
        return f"US$ {value / 1e6:.1f}M"
    return f"US$ {value:,.0f}"


_chart_id_counter = 0


def _revenue_line_chart_svg(
    series: list[dict], *, width: int = 560, height: int = 180
) -> str:
    """Gráfica de línea en SVG puro (sin librerías de terceros) para el
    histórico de ingresos ya citado arriba — nunca un número nuevo, solo
    otra forma de ver los mismos puntos. Si hay menos de 2 años con dato,
    no se dibuja nada (no se inventa una tendencia con un solo punto)."""
    global _chart_id_counter
    points = [p for p in series if p.get("value") is not None]
    if len(points) < 2:
        return ""
    _chart_id_counter += 1
    gradient_id = f"chartFade{_chart_id_counter}"

    values = [p["value"] for p in points]
    min_v, max_v = min(values), max(values)
    span = (max_v - min_v) or 1.0
    pad_x, pad_top, pad_bottom = 28, 28, 24
    n = len(points)

    def px(i: int) -> float:
        return pad_x + (width - 2 * pad_x) * (i / (n - 1))

    def py(v: float) -> float:
        return pad_top + (height - pad_top - pad_bottom) * (1 - (v - min_v) / span)

    coords = [(px(i), py(p["value"])) for i, p in enumerate(points)]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = (
        f"M{coords[0][0]:.1f},{height - pad_bottom:.1f} "
        + " ".join(f"L{x:.1f},{y:.1f}" for x, y in coords)
        + f" L{coords[-1][0]:.1f},{height - pad_bottom:.1f} Z"
    )
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="chart-dot" />' for x, y in coords)
    value_labels = "".join(
        f'<text x="{coords[i][0]:.1f}" y="{coords[i][1] - 10:.1f}" class="chart-value-label" '
        f'text-anchor="middle">{_esc(_fmt_money_short(p["value"]))}</text>'
        for i, p in enumerate(points)
    )
    year_labels = "".join(
        f'<text x="{coords[i][0]:.1f}" y="{height - 6:.1f}" class="chart-year-label" '
        f'text-anchor="middle">{_esc(str(p["period_end"])[:4])}</text>'
        for i, p in enumerate(points)
    )
    return f"""
      <svg viewBox="0 0 {width} {height}" class="line-chart" role="img" aria-label="Ingresos por año">
        <defs>
          <linearGradient id="{gradient_id}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" class="chart-fade-start" />
            <stop offset="100%" class="chart-fade-end" />
          </linearGradient>
        </defs>
        <path d="{area}" fill="url(#{gradient_id})" stroke="none" />
        <polyline points="{polyline}" class="chart-line" fill="none" />
        {dots}
        {value_labels}
        {year_labels}
      </svg>"""


def _kpi(icon: str, label: str, value_text: str, count_attr: str, tint: str, tag_kind: str, tag_text: str, foot: str) -> str:
    return f"""
      <article class="kpi {tint} reveal spot">
        <div class="kpi-body">
          <p class="kpi-label"><span aria-hidden="true">{icon}</span>{_esc(label)}</p>
          <p class="kpi-value"{count_attr}>{_esc(value_text)}</p>
        </div>
        <div class="kpi-foot"><span>{_esc(foot)}</span><span class="tag tag-{tag_kind}">{_esc(tag_text)}</span></div>
      </article>"""


def _kpi_for(verified: dict, key: str, label: str, tint: str) -> str:
    cv = verified.get(key)
    if cv is None:
        return ""
    if cv.no_verificado:
        kind, tag = "warn", "no verificado"
    elif cv.derivado:
        kind, tag = "info", "derivado"
    else:
        kind, tag = "ok", "citado"
    foot = cv.citation.seccion if (cv.citation is not None and not cv.derivado) else "del mismo reporte"
    return _kpi(_CONCEPT_ICONS.get(key, "🔎"), label, _fmt_money(cv.value), _count_attr(cv.value), tint, kind, tag, foot)


def _stat_cards(verified: dict, fcf: FcfResult | None = None, cagr: CagrResult | None = None) -> str:
    """Tablero de tarjetas grandes (estilo dashboard) con los números que más
    importan de un vistazo: los mismos que ya están citados en el grid de
    abajo, solo con más jerarquía visual. Nada nuevo se calcula aquí."""
    cards = [
        _kpi_for(verified, "revenue", "Ingresos", "t-vio"),
        _kpi_for(verified, "ebitda", "EBITDA (derivado)", "t-mint"),
        _kpi_for(verified, "net_income", "Utilidad neta", "t-amb"),
    ]
    if cagr is not None:
        if cagr.value is not None:
            cards.append(_kpi("📈", "CAGR de ingresos", f"{cagr.value:+.2%}", _count_attr(cagr.value * 100, suffix="%"),
                              "t-cor", "info", "calculado", "en código, no por IA"))
        else:
            cards.append(_kpi("📈", "CAGR de ingresos", "no verificado", "", "t-cor", "warn", "no verificado", "faltan años citados"))
    cards = [c for c in cards if c]
    if not cards:
        return ""
    return f'<div class="kpi-row">{"".join(cards)}</div>'


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
      <article class="card reveal spot" style="transition-delay:{delay}ms" data-key="{_esc(key)}" data-figure-label="{_esc(label)}">
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


def _site_header() -> str:
    return """
  <header class="site-header">
    <div class="wrap">
      <span class="brand">
        <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="#06070d" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-6 4 3 8-9"/><path d="M15 5h5v5"/></svg></span>
        Quant <span class="lab">Lab</span>
      </span>
      <nav class="nav" aria-label="Secciones">
        <a href="#reporte">1 · Reporte</a>
        <a href="#prueba">Pruébalo</a>
        <a href="#simulacion">2 · Simulación</a>
        <a href="#diario">3 · Diario</a>
        <a href="#como-funciona">Cómo se verifica</a>
      </nav>
      <span class="clock"><span class="dot-live" aria-hidden="true"></span><span id="clock">--:--:-- UTC</span></span>
      <span class="pill">Solo investigación</span>
    </div>
  </header>
  <div class="ticker" id="ticker" aria-label="Cinta de precios (TradingView, externa y sin verificar)"></div>
  <div class="strip"><div class="wrap">Análisis informativo, no es asesoría financiera. Nunca dice "compra" ni "vende": la decisión es tuya.</div></div>"""


def _bg_fx() -> str:
    return """
  <div class="bg-fx" aria-hidden="true">
    <div class="bg-grid"></div>
    <i class="orb orb-1"></i><i class="orb orb-2"></i><i class="orb orb-3"></i>
    <canvas id="bg-canvas"></canvas>
  </div>"""


def _bot_markup() -> str:
    face = (
        '<svg viewBox="0 0 40 40" aria-hidden="true" fill="none">'
        '<line x1="20" y1="3" x2="20" y2="9" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>'
        '<circle cx="20" cy="3.2" r="2.2" fill="#2bd9a0"/>'
        '<rect x="6" y="9" width="28" height="23" rx="9" fill="#0b0820" stroke="#fff" stroke-opacity=".85" stroke-width="2"/>'
        '<ellipse class="bot-eye" cx="14.5" cy="20" rx="3" ry="3.6" fill="#2bd9a0"/>'
        '<ellipse class="bot-eye" cx="25.5" cy="20" rx="3" ry="3.6" fill="#2bd9a0"/>'
        '<path d="M15 27.2q5 3 10 0" stroke="#9a8fff" stroke-width="2" stroke-linecap="round"/></svg>'
    )
    return f"""
  <div class="bot-fab">
    <div class="bot-greet">¿Te ayudo a leer el reporte? Pregúntame lo que quieras.</div>
    <button type="button" class="bot-btn" id="bot-open" aria-label="Abrir el asistente Quant" aria-expanded="false" aria-controls="bot-drawer">{face}</button>
  </div>
  <div class="bot-scrim" id="bot-scrim"></div>
  <aside class="bot-drawer" id="bot-drawer" role="dialog" aria-label="Asistente Quant" aria-hidden="true">
    <div class="bot-drawer-head">
      <span class="bot-avatar" aria-hidden="true">🤖</span>
      <div class="who"><b>Quant</b><small><span class="dot-live" style="display:inline-block;margin-right:6px"></span>asistente del pipeline · respuestas preparadas</small></div>
      <button type="button" class="icon-btn" id="bot-reset" aria-label="Reiniciar conversación" title="Reiniciar">↺</button>
      <button type="button" class="icon-btn" id="bot-close" aria-label="Cerrar">✕</button>
    </div>
    <div class="bot-scroll" id="bot-scroll">
      <canvas id="bot-orb" width="320" height="320" aria-hidden="true"></canvas>
      <div class="bot-log" id="bot-log" aria-live="polite"></div>
      <div class="chip-row" id="bot-chips"></div>
    </div>
    <div class="bot-input-row">
      <input type="text" id="bot-input" maxlength="200" placeholder="Pregúntale a Quant…" aria-label="Tu pregunta" autocomplete="off">
      <button type="button" class="bot-send" id="bot-send" aria-label="Enviar">➤</button>
    </div>
    <p class="bot-fine">Respuestas ya preparadas con las cifras verificadas; no es un chat en vivo y no es asesoría financiera. No escribas datos personales.</p>
  </aside>"""


def _kb_item(pregunta: str, respuesta: str, keywords: list[str]) -> dict:
    return {"pregunta": pregunta, "respuesta": respuesta, "keywords": keywords}


def _bot_kb(empresa: str, filing_doc_id: str, verified: dict, fcf: FcfResult, cagr: CagrResult) -> list[dict]:
    """Base de conocimiento del asistente: texto fijo sobre el método y
    respuestas sobre ESTE reporte armadas aquí, en código, con sus mismas
    cifras. Nada se genera en el navegador ni se llama a ningún modelo."""
    kb = []
    rev = verified.get("revenue")
    if rev is not None and rev.value is not None:
        cita = f" Está citado en «{rev.citation.seccion}» ({rev.citation.doc_id}); abre «Ver fuente» en la tarjeta de Ingresos." if rev.citation else ""
        kb.append(_kb_item(
            "¿Cuánto fueron los ingresos?",
            f"En el reporte de ejemplo ({empresa}, {filing_doc_id}) los ingresos son {_fmt_money(rev.value)}.{cita}",
            ["ingresos", "ventas", "revenue", "facturacion", "cuanto"],
        ))
    faltan = [label for key, label in _DISPLAY_ORDER if verified[key].no_verificado]
    if faltan:
        kb.append(_kb_item(
            "¿Qué cifras no se pudieron verificar?",
            "En este reporte quedaron sin verificar: " + ", ".join(faltan) + ". No se usaron en ningún cálculo.",
            ["verificar", "verificado", "verificadas", "faltan", "falta", "cifras", "sin"],
        ))
    else:
        kb.append(_kb_item(
            "¿Qué cifras no se pudieron verificar?",
            "En este reporte todas las cifras de la tabla tienen una cita comprobada contra el documento original.",
            ["verificar", "verificado", "verificadas", "faltan", "falta", "cifras", "sin"],
        ))
    if cagr.value is not None:
        kb.append(_kb_item(
            "¿Cuál es el CAGR de ingresos?",
            f"El CAGR de ingresos de este reporte es {cagr.value:+.2%}. {cagr.nota} Lo calcula el código con cifras ya citadas, no la IA.",
            ["cagr", "crecimiento", "crecio", "tasa", "anual"],
        ))
    if fcf.value is None:
        kb.append(_kb_item(
            "¿Por qué no hay flujo de caja libre (FCF)?",
            f"El FCF no se pudo calcular: {fcf.nota} Es una limitación de los datos disponibles, no un juicio sobre la empresa.",
            ["fcf", "flujo", "caja", "libre", "free", "cash"],
        ))
    kb += [
        _kb_item(
            "¿Cómo se verifica cada cifra?",
            "El código extrae la cifra de los datos estructurados del documento oficial y guarda la frase exacta. "
            "Un verificador vuelve a abrir el documento descargado (con su huella hash) y comprueba que la frase exista "
            "literal. Si no existe, la cifra se descarta y se marca «no verificado». La IA nunca ve el documento crudo.",
            ["verifica", "verificar", "verificacion", "cita", "citas", "hash", "huella", "fuente", "como", "funciona", "pipeline"],
        ),
        _kb_item(
            "¿Qué significa «no verificado»?",
            "Que no se encontró una fuente que respalde la cifra. En ese caso el sistema lo dice en lugar de inventar, "
            "y esa cifra no entra en ningún cálculo.",
            ["verificado", "significa", "inventar", "fuente", "falta"],
        ),
        _kb_item(
            "¿Qué diferencia hay entre Capa A y Capa B?",
            "La Capa A son hechos con cita exacta del documento oficial. La Capa B son escenarios simulados con "
            "supuestos que tú ves y cambias: muestran probabilidades, no predicciones. Nunca se mezclan: nada "
            "simulado cruza hacia los hechos, y una cita nunca justifica un precio simulado.",
            ["capa", "diferencia", "hechos", "simulado", "simulacion", "escenarios", "separadas", "mezclan"],
        ),
        _kb_item(
            "¿Qué es el Monte Carlo y qué no es?",
            "Simula miles de caminos posibles del precio con un modelo (movimiento browniano geométrico) usando μ y σ. "
            "Estima probabilidades y riesgo; no predice el futuro, supone que el pasado reciente se parece al futuro y "
            "subestima caídas extremas. Sus probabilidades no están validadas con un backtest.",
            ["monte", "carlo", "simulacion", "simular", "probabilidad", "probabilidades", "var", "percentil", "gbm", "riesgo", "prediccion"],
        ),
        _kb_item(
            "¿De dónde salen los gráficos en vivo?",
            "De widgets externos de TradingView, cargados en un marco aislado (sandbox). Este proyecto no los "
            "verifica: sirven solo como referencia visual y sus datos pueden ir con retraso.",
            ["tradingview", "grafico", "graficos", "grafica", "vivo", "noticias", "widget", "precio", "precios"],
        ),
        _kb_item(
            "¿Esto es asesoría financiera?",
            "No. Es una herramienta para investigar y justificar. Nunca dice «compra» ni «vende»: la decisión y el "
            "riesgo que aceptas son tuyos.",
            ["asesoria", "financiera", "consejo", "recomendacion", "recomiendas", "invertir", "comprar", "vender", "debo"],
        ),
        _kb_item(
            "¿Qué es el Diario de decisiones?",
            "Un formulario para anotar qué hecho verificado y qué escenario simulado miraste, tu postura y tu "
            "razonamiento, en campos separados. No guarda nada: copias el texto o descargas un .md.",
            ["diario", "decisiones", "decision", "notion", "guardar", "anotar"],
        ),
    ]
    return kb


def _hero(empresa_ejemplo: str, filing_doc_id: str, generated_at: datetime, verified: dict | None = None) -> str:
    cited = derived = missing = 0
    for key, _label in _DISPLAY_ORDER:
        cv = (verified or {}).get(key)
        if cv is None:
            continue
        if cv.no_verificado:
            missing += 1
        elif cv.derivado:
            derived += 1
        else:
            cited += 1
    if missing:
        warn_line = f"{missing} sin verificar: quedan fuera de todo cálculo."
        warn_ico = '<span class="ico ico-warn">!</span>'
    else:
        warn_line = "Ninguna cifra quedó sin verificar."
        warn_ico = '<span class="ico ico-ok">✓</span>'
    return f"""
  <section class="hero wrap">
    <div>
      <span class="eyebrow"><span class="dot-live" aria-hidden="true"></span>Monitor de reportes con citas verificables</span>
      <h1>Qué dice el reporte, <em class="serif grad-text">y qué podría pasar.</em></h1>
      <p class="lead">Dos capas separadas a propósito: arriba, hechos con cita del documento oficial; abajo,
      escenarios simulados que no son predicciones. Nunca se mezclan.</p>
      <div class="chips">
        <span class="pill">{_esc(empresa_ejemplo)}</span>
        <span class="pill">{_esc(filing_doc_id)}</span>
        <span class="pill">generado {_esc(generated_at.strftime('%Y-%m-%d %H:%M UTC'))}</span>
      </div>
      <div class="hero-cta">
        <a class="btn" href="#reporte">Ver el reporte ↓</a>
        <button type="button" class="btn btn-ghost" data-open-bot>🤖 Preguntarle a Quant</button>
      </div>
    </div>
    <aside class="agent-card reveal" aria-label="Estado de la verificación">
      <div class="agent-top"><span class="dot-live" aria-hidden="true"></span>VERIFICACIÓN COMPLETADA</div>
      <div class="agent-metrics">
        <div class="agent-metric"><small>Citadas</small><b>{cited}</b></div>
        <div class="agent-metric"><small>Derivadas</small><b>{derived}</b></div>
        <div class="agent-metric"><small>Sin verificar</small><b>{missing}</b></div>
      </div>
      <ul class="agent-feed">
        <li><span class="ico ico-ok">✓</span><span>{cited} cifras con su frase exacta comprobada en el documento original.</span></li>
        <li><span class="ico ico-info">ƒ</span><span>{derived} derivadas por código a partir de las anteriores, sin IA de por medio.</span></li>
        <li>{warn_ico}<span>{_esc(warn_line)}</span></li>
      </ul>
    </aside>
  </section>"""


def _frontier() -> str:
    return """
    <div class="frontier" role="separator">
      ▲ <strong>HECHOS CON CITA</strong> &nbsp;·&nbsp; frontera: nada simulado cruza hacia arriba &nbsp;·&nbsp; <strong>ESCENARIOS SIMULADOS</strong> ▼
    </div>"""


def _mc_section() -> str:
    return """
    <section class="layer layer-b" id="simulacion" aria-labelledby="mc-title">
      <span class="layer-tag">CAPA B · SIMULADO · SIN VALIDAR</span>
      <h2 id="mc-title">Simulación Monte Carlo</h2>
      <div class="notice-b">
        <p><strong>Esto es una simulación, no un hecho ni una predicción.</strong> Aquí no hay citas del documento:
        los resultados salen de los supuestos que ves abajo. Las probabilidades no están validadas con un
        backtest, así que no las uses para decidir por sí solas.</p>
      </div>
      <div class="mc-controls">
        <div class="field wide">
          <label for="mc-source">Origen de μ y σ</label>
          <select id="mc-source"><option value="">Supuestos manuales (no verificados)</option></select>
        </div>
        <div class="field"><label for="mc-s0">Precio inicial (US$)</label><input id="mc-s0" type="number" step="any" min="0" value="100"></div>
        <div class="field"><label for="mc-mu">μ, retorno anual (%)</label><input id="mc-mu" type="number" step="any" value="8"></div>
        <div class="field"><label for="mc-sigma">σ, volatilidad anual (%)</label><input id="mc-sigma" type="number" step="any" min="0" value="25"></div>
        <div class="field"><label for="mc-days">Días de mercado</label><input id="mc-days" type="number" step="1" min="1" max="756" value="90"></div>
        <div class="field"><label for="mc-paths">Simulaciones</label><input id="mc-paths" type="number" step="100" min="100" max="5000" value="2000"></div>
        <div class="field"><label for="mc-capital">Capital simulado (US$)</label><input id="mc-capital" type="number" step="any" min="0" value="1000"></div>
        <div class="field"><label for="mc-seed">Semilla (reproducible)</label><input id="mc-seed" type="number" step="1" value="42"></div>
        <div class="field"><label>&nbsp;</label><button type="button" id="mc-run" class="btn">Simular</button></div>
      </div>
      <p id="mc-meta" class="mc-meta"></p>
      <p id="mc-error" class="mc-error" role="alert"></p>
      <div id="mc-results" aria-live="polite"></div>
      <div class="limits">
        <strong>Límites de este modelo</strong>
        <ul>
          <li>Supone que el futuro se parece al pasado reciente; los mercados cambian de régimen.</li>
          <li>Retornos con forma de campana: subestima caídas extremas (colas gordas, saltos, gaps).</li>
          <li>No incluye comisiones, impuestos, dividendos ni noticias del reporte.</li>
          <li>Mismo conjunto de supuestos + misma semilla = mismo resultado; otra semilla cambia los números.</li>
        </ul>
      </div>
    </section>"""


def _diary_section() -> str:
    return """
    <section class="layer" id="diario" aria-labelledby="diary-title">
      <div class="diary">
        <h2 id="diary-title">Diario de decisiones</h2>
        <p class="section-intro">Anota qué hecho verificado y qué escenario simulado miraste, y por qué.
        Quedan en campos separados. Esta página no guarda nada: copia el texto o descárgalo.</p>
        <div class="grid2">
          <div><label for="diary-fact">Hecho verificado (Capa A)</label>
            <select id="diary-fact"><option value="">— ninguno —</option></select></div>
          <div><label for="diary-scenario">Escenario simulado (Capa B)</label>
            <select id="diary-scenario"><option value="">— ninguno (corre una simulación primero) —</option></select></div>
        </div>
        <fieldset>
          <legend>Mi postura (tuya, no del sistema)</legend>
          <label><input type="radio" name="diary-posture" value="Seguir investigando" checked> Seguir investigando</label>
          <label><input type="radio" name="diary-posture" value="Esperar más información"> Esperar más información</label>
          <label><input type="radio" name="diary-posture" value="Descartar por ahora"> Descartar por ahora</label>
        </fieldset>
        <label for="diary-note">Mi razonamiento (incluye qué argumento en contra consideraste)</label>
        <textarea id="diary-note" maxlength="1000" placeholder="¿Qué me convenció? ¿Qué me haría cambiar de opinión?"></textarea>
        <label for="diary-preview" style="display:block;margin-top:14px">Vista previa (Markdown)</label>
        <textarea id="diary-preview" class="preview" readonly></textarea>
        <div class="actions">
          <button type="button" id="diary-copy" class="btn">Copiar</button>
          <button type="button" id="diary-download" class="btn btn-ghost">Descargar .md</button>
        </div>
        <p id="diary-status" class="hint" role="status"></p>
      </div>
    </section>"""


def _pipeline_section() -> str:
    steps = []
    for i, (icon, title, body) in enumerate(_PIPELINE_STEPS):
        delay = i * 90
        arrow = '<span class="step-arrow" aria-hidden="true">→</span>' if i < len(_PIPELINE_STEPS) - 1 else ""
        steps.append(
            f"""
        <div class="step reveal spot" style="transition-delay:{delay}ms">
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
      <article class="card reveal spot">
        <header class="card-head"><span class="card-icon" aria-hidden="true">🧮</span><h3>FCF</h3></header>
        <p class="card-value"{_count_attr(fcf.value)}>{_esc(_fmt_money(fcf.value))}</p>
        <p class="card-note">{_esc(fcf.nota)}</p>
      </article>
      <article class="card reveal spot">
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
    <section class="try-it reveal" id="prueba" aria-labelledby="try-it-title">
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
    stat_cards = _stat_cards(verified, fcf, cagr)
    bot_kb_json = _json.dumps(_bot_kb(empresa_ejemplo, filing_doc_id, verified, fcf, cagr), ensure_ascii=False, separators=(",", ":"))
    revenue_series_points = [
        {"period_end": cv.period_end, "value": cv.value}
        for cv in (verified.get("revenue_series") or [])
        if cv.value is not None
    ]
    revenue_chart = _revenue_line_chart_svg(revenue_series_points)
    chart_card = (
        f'<div class="card chart-card reveal spot"><h3>📈 Ingresos por año (mismo documento citado arriba)</h3>{revenue_chart}</div>'
        if revenue_chart
        else ""
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
<meta name="theme-color" content="#06070d">
<title>{_esc(empresa_ejemplo)} — Reporte Quant Lab</title>
<style>{_STYLE}</style>
</head>
<body>
  {_bg_fx()}
  <div id="scroll-progress"></div>
  {_site_header()}
  {_hero(empresa_ejemplo, filing_doc_id, generated_at, verified)}
  <main class="wrap">
    <section class="layer layer-a" id="reporte">
      <span class="layer-tag">CAPA A · HECHOS VERIFICADOS</span>
      {_risk_banner(verified, fcf)}
      <h2>📊 Cifras con fuente</h2>
      <p class="section-intro">Cada tarjeta dice si la cifra está citada, es derivada de otras, o no se pudo verificar.</p>
      {stat_cards}
      {chart_card}
      <div class="grid">{cards}
      </div>
      <h2>🧮 Cálculos</h2>
      {_calc_cards(fcf, cagr)}
      {cambios_section}
      {_try_it_section(companies)}
    </section>
    {_frontier()}
    {_mc_section()}
    {_diary_section()}
    <section class="layer" aria-label="Cómo se verifica">
      {_pipeline_section()}
    </section>
  </main>
  <footer>
    <div class="wrap">
      <p><strong>{_esc(DISCLAIMER.replace('**', ''))}</strong></p>
      <p>Herramienta de investigación, no es asesoría financiera. No sugiere comprar ni vender.</p>
      <p class="footer-link">
        <a href="{_REPO_URL}" target="_blank" rel="noopener noreferrer">Código fuente ↗</a>
      </p>
    </div>
  </footer>
  {_bot_markup()}
  <div id="bot-data" hidden data-kb="{_esc(bot_kb_json)}"></div>
  <script>{_SCRIPT}</script>
</body>
</html>
"""
