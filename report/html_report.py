"""Página web del reporte (adicional, fuera del alcance original del MVP,
ver SPEC.md sección 3). Es un único archivo HTML autocontenido y estático:
no hay backend, no hay formularios, no se guarda nada en el navegador.
Diseño v2 (Capa A hechos verificados · Capa B simulación · Diario), oscuro (a pedido explícito de
un look de tablero más vistoso), animada, y pensada para explicar el sistema de
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

    // Gráfica y noticias en vivo: iframes aislados de TradingView (mismo
    // patrón que TradePro). La página nunca llama a nada; el navegador de
    // quien visita sí, directo a TradingView, dentro de un marco con
    // sandbox. El símbolo se valida antes de armar la URL, aunque hoy
    // siempre venga de nuestros propios datos.
    var SYMBOL_PATTERN = /^[A-Z]+:[A-Z.]{1,10}$/;

    function liveWidgetFrame(symbol, widgetPath, title, extraClass) {
      var frame = document.createElement("iframe");
      frame.className = "live-frame" + (extraClass ? " " + extraClass : "");
      frame.src =
        "https://s.tradingview.com/embed-widget/" + widgetPath + "/?symbol=" +
        encodeURIComponent(symbol) + "&locale=es&colorTheme=dark";
      frame.loading = "lazy";
      frame.title = title;
      frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      return frame;
    }

    function liveSection(ticker, symbol) {
      var wrap = document.createElement("div");
      wrap.className = "try-it-live";

      var chartCard = document.createElement("div");
      chartCard.className = "card live-card";
      var chartTitle = document.createElement("h4");
      chartTitle.textContent = "📈 Gráfica en vivo";
      chartCard.appendChild(chartTitle);
      chartCard.appendChild(liveWidgetFrame(symbol, "symbol-overview", "Gráfica en vivo de " + ticker, "live-frame-chart"));
      wrap.appendChild(chartCard);

      var newsCard = document.createElement("div");
      newsCard.className = "card live-card";
      var newsTitle = document.createElement("h4");
      newsTitle.textContent = "📰 Noticias en vivo";
      newsCard.appendChild(newsTitle);
      newsCard.appendChild(liveWidgetFrame(symbol, "timeline", "Noticias en vivo de " + ticker, "live-frame-news"));
      wrap.appendChild(newsCard);

      var note = document.createElement("p");
      note.className = "live-note";
      note.textContent = "Widget externo de TradingView, no verificado por este proyecto — úsalo solo como referencia visual.";
      wrap.appendChild(note);

      return wrap;
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

_TRADINGVIEW_ORIGIN = "https://s.tradingview.com"

_CSP = (
    "default-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    f"script-src 'self' 'sha256-{_SCRIPT_HASH}'; "
    "img-src 'self'; "
    f"frame-src {_TRADINGVIEW_ORIGIN}; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

_STYLE = """
  :root {
    --bg: #0A0D11;
    --s1: #10151B;
    --s2: #161C24;
    --line: #232B35;
    --mint: #6BE3BE;
    --vio: #BBA8FF;
    --amb: #F6BC52;
    --cor: #FF8F80;
    --paper: #E9EEF3;
    --ink: #12161C;
    --text: #E6EBF1;
    --muted: #8D98A6;
    --radius: 14px;
    --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0; background: var(--bg); color: var(--text); line-height: 1.55;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  a { color: var(--mint); }
  h1, h2, h3, h4 { line-height: 1.2; margin: 0; }
  #scroll-progress {
    position: fixed; top: 0; left: 0; height: 3px; width: 0%; z-index: 50;
    background: linear-gradient(90deg, var(--mint), var(--vio)); transition: width .1s linear;
  }
  .wrap { max-width: 1120px; margin: 0 auto; padding: 0 20px; }
  .site-header { border-bottom: 1px solid var(--line); background: rgba(10,13,17,.92); position: sticky; top: 0; z-index: 40; }
  .site-header .wrap { display: flex; align-items: center; gap: 18px; padding-top: 12px; padding-bottom: 12px; flex-wrap: wrap; }
  .brand { font-weight: 700; letter-spacing: .02em; }
  .brand span { color: var(--mint); }
  .nav { display: flex; gap: 6px; flex: 1; flex-wrap: wrap; }
  .nav a { color: var(--muted); text-decoration: none; padding: 6px 12px; border-radius: 999px; font-size: .9rem; }
  .nav a:hover, .nav a:focus-visible { color: var(--text); background: var(--s2); }
  .pill { font-size: .78rem; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); background: var(--s1); }
  .strip { background: var(--s1); border-bottom: 1px solid var(--line); font-size: .85rem; color: var(--muted); }
  .strip .wrap { padding-top: 8px; padding-bottom: 8px; }
  .hero { padding: 44px 20px 20px; }
  .hero h1 { font-size: clamp(1.9rem, 4.5vw, 2.9rem); letter-spacing: -.02em; max-width: 18ch; }
  .hero p { color: var(--muted); max-width: 62ch; margin: 12px 0 0; }
  .hero .chips { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
  .layer { margin: 28px 0; }
  .layer-tag { display: inline-block; font-family: var(--mono); font-size: .75rem; letter-spacing: .08em; padding: 4px 10px; border-radius: 6px; margin-bottom: 12px; }
  .layer-a .layer-tag { color: var(--mint); background: rgba(107,227,190,.12); border: 1px solid rgba(107,227,190,.35); }
  .layer-b .layer-tag { color: var(--vio); background: rgba(187,168,255,.12); border: 1px dashed rgba(187,168,255,.5); }
  .layer h2 { font-size: 1.4rem; margin: 22px 0 8px; }
  .section-intro { color: var(--muted); margin: 0 0 14px; max-width: 70ch; }
  .risk { border: 1px solid rgba(246,188,82,.5); background: rgba(246,188,82,.08); border-radius: var(--radius); padding: 18px 20px; }
  .risk h2 { margin-top: 0; color: var(--amb); font-size: 1.15rem; }
  .risk ul { margin: 6px 0 10px; padding-left: 20px; }
  .risk-note { color: var(--muted); font-size: .9rem; margin: 8px 0 0; }
  .stat-row, .calc-grid, .grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }
  .stat-row { margin-bottom: 14px; }
  .stat-card, .card { background: var(--s1); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px; }
  .stat-card { display: flex; gap: 12px; align-items: center; }
  .stat-icon, .card-icon { font-size: 1.3rem; }
  .stat-label { margin: 0; color: var(--muted); font-size: .85rem; }
  .stat-value, .card-value { margin: 2px 0 0; font-family: var(--mono); font-size: 1.35rem; font-weight: 600; }
  .card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .card-head h3 { font-size: 1rem; flex: 1; }
  .card-note { color: var(--muted); font-size: .88rem; margin: 8px 0 0; }
  .card-detail { margin-top: 10px; font-size: .88rem; color: var(--muted); }
  .card-detail summary { cursor: pointer; color: var(--mint); }
  blockquote { margin: 8px 0 0; padding: 8px 12px; border-left: 3px solid var(--mint); background: var(--s2); color: var(--text); font-family: var(--mono); font-size: .8rem; overflow-wrap: anywhere; }
  .badge { font-size: .72rem; padding: 3px 9px; border-radius: 999px; border: 1px solid; white-space: nowrap; }
  .badge-ok { color: var(--mint); border-color: rgba(107,227,190,.5); background: rgba(107,227,190,.1); }
  .badge-info { color: var(--vio); border-color: rgba(187,168,255,.5); background: rgba(187,168,255,.1); }
  .badge-warn { color: var(--amb); border-color: rgba(246,188,82,.5); background: rgba(246,188,82,.1); }
  .chart-card { margin-bottom: 14px; }
  .chart-card h3 { font-size: 1rem; margin-bottom: 8px; }
  .line-chart { width: 100%; height: auto; }
  .chart-line { stroke: var(--mint); stroke-width: 2.5; }
  .chart-dot { fill: var(--mint); }
  .chart-fade-start { stop-color: var(--mint); stop-opacity: .3; }
  .chart-fade-end { stop-color: var(--mint); stop-opacity: 0; }
  .chart-value-label, .chart-year-label { fill: var(--muted); font-size: 11px; font-family: var(--mono); }
  .frontier { margin: 40px 0 10px; padding: 18px 0; border-top: 2px dashed var(--line); border-bottom: 2px dashed var(--line); text-align: center; color: var(--muted); font-family: var(--mono); font-size: .85rem; letter-spacing: .04em; }
  .frontier strong { color: var(--text); }
  .notice-b { border: 1px dashed rgba(187,168,255,.55); background: rgba(187,168,255,.07); border-radius: var(--radius); padding: 14px 18px; margin-bottom: 16px; }
  .notice-b p { margin: 0; }
  .mc-controls { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); background: var(--s1); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px; }
  .field label, .try-it-label { display: block; font-size: .8rem; color: var(--muted); margin-bottom: 4px; }
  .field.wide { grid-column: 1 / -1; }
  input, select, textarea, button { font: inherit; }
  input[type="number"], select, textarea { width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; }
  input:focus-visible, select:focus-visible, textarea:focus-visible, button:focus-visible, summary:focus-visible, a:focus-visible { outline: 2px solid var(--mint); outline-offset: 2px; }
  .btn { background: var(--mint); color: #062016; border: 0; border-radius: 8px; padding: 10px 18px; font-weight: 700; cursor: pointer; }
  .btn:disabled { opacity: .6; cursor: progress; }
  .btn-ghost { background: transparent; color: var(--ink); border: 1px solid #9AA6B4; }
  .mc-meta { color: var(--muted); font-size: .85rem; margin: 10px 0 0; }
  .mc-error { color: var(--cor); min-height: 1.2em; margin: 8px 0 0; font-size: .9rem; }
  .mc-stats { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-top: 16px; }
  .mc-stats-3 { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
  .mc-stat { background: var(--s1); border: 1px dashed rgba(187,168,255,.45); border-radius: var(--radius); padding: 14px 16px; }
  .mc-stat.mc-risk { border-color: rgba(255,143,128,.6); background: rgba(255,143,128,.06); }
  .mc-stat-label { margin: 0; color: var(--muted); font-size: .82rem; }
  .mc-stat-value { margin: 4px 0 0; font-family: var(--mono); font-size: 1.5rem; font-weight: 700; }
  .mc-risk .mc-stat-value { color: var(--cor); }
  .mc-stat-note { margin: 2px 0 0; color: var(--muted); font-size: .78rem; }
  .mc-figure { margin: 16px 0 0; background: var(--s1); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px; }
  .mc-figure figcaption { color: var(--muted); font-size: .85rem; margin-bottom: 8px; }
  .mc-chart { width: 100%; height: auto; }
  .mc-band-outer { fill: rgba(187,168,255,.14); }
  .mc-band-inner { fill: rgba(187,168,255,.22); }
  .mc-path { fill: none; stroke: rgba(187,168,255,.35); stroke-width: 1; }
  .mc-median { fill: none; stroke: var(--vio); stroke-width: 2.5; }
  .mc-capital-line { stroke: var(--amb); stroke-width: 1.5; stroke-dasharray: 5 4; }
  .mc-axis { fill: var(--muted); font-size: 11px; font-family: var(--mono); }
  .mc-bar-gain { fill: rgba(187,168,255,.7); }
  .mc-bar-loss { fill: rgba(255,143,128,.75); }
  .limits { color: var(--muted); font-size: .88rem; margin-top: 16px; }
  .limits ul { padding-left: 20px; margin: 6px 0 0; }
  .diary { background: var(--paper); color: var(--ink); border-radius: var(--radius); padding: 22px; margin-top: 8px; }
  .diary h2 { margin-top: 0; }
  .diary .section-intro, .diary label, .diary .hint { color: #4A5563; }
  .diary .grid2 { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
  .diary select, .diary textarea { background: #fff; color: var(--ink); border-color: #B7C1CC; }
  .diary fieldset { border: 1px solid #B7C1CC; border-radius: 8px; padding: 8px 12px; margin: 14px 0; }
  .diary legend { font-size: .8rem; color: #4A5563; padding: 0 6px; }
  .diary fieldset label { display: inline-flex; gap: 6px; align-items: center; margin-right: 16px; font-size: .95rem; color: var(--ink); }
  .diary textarea { min-height: 110px; resize: vertical; }
  .diary .preview { font-family: var(--mono); font-size: .8rem; min-height: 170px; }
  .diary .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
  .diary .hint { font-size: .82rem; margin: 6px 0 0; }
  .pipeline-track { display: flex; flex-wrap: wrap; gap: 10px; align-items: stretch; }
  .step { flex: 1 1 170px; background: var(--s1); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px 16px; }
  .step h3 { font-size: .98rem; margin: 6px 0; }
  .step p { margin: 0; color: var(--muted); font-size: .86rem; }
  .step-icon { font-size: 1.4rem; }
  .step-arrow { align-self: center; color: var(--muted); }
  .try-it { background: var(--s1); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 20px; margin-top: 18px; }
  .try-it-warning { background: rgba(246,188,82,.08); border: 1px solid rgba(246,188,82,.4); border-radius: 10px; padding: 10px 14px; font-size: .88rem; margin: 0 0 14px; }
  .try-it-head { display: flex; gap: 12px; align-items: center; margin-bottom: 10px; }
  .try-it h2 { margin: 0; font-size: 1.2rem; }
  .bot-avatar { font-size: 1.6rem; }
  .bot-avatar-sm { font-size: 1.1rem; margin-right: 6px; }
  .try-it-select { max-width: 340px; }
  .try-it-result { margin-top: 14px; }
  .try-it-result-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .try-it-price { font-family: var(--mono); font-size: .9rem; }
  .try-it-figures { display: grid; gap: 6px; margin-top: 10px; }
  .try-it-figure { display: flex; gap: 10px; align-items: center; border-bottom: 1px solid var(--line); padding: 6px 0; }
  .try-it-figure-label { flex: 1; color: var(--muted); }
  .try-it-figure-value { font-family: var(--mono); }
  .try-it-live { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); margin-top: 14px; }
  .live-card h4 { margin-bottom: 8px; }
  .live-frame { width: 100%; border: 0; border-radius: 8px; background: var(--bg); }
  .live-frame-chart { height: 280px; }
  .live-frame-news { height: 320px; }
  .live-note { grid-column: 1 / -1; color: var(--muted); font-size: .82rem; margin: 0; }
  .chat-card { margin-top: 14px; border: 1px solid var(--line); border-radius: var(--radius); padding: 14px; background: var(--bg); }
  .chat-head { display: flex; align-items: center; }
  .chat-warn { color: var(--muted); font-size: .82rem; margin: 6px 0 10px; }
  .chat-log { display: grid; gap: 8px; margin-bottom: 10px; }
  .chat-bubble { padding: 10px 12px; border-radius: 12px; max-width: 90%; font-size: .92rem; }
  .chat-bubble-user { background: var(--s2); justify-self: end; }
  .chat-bubble-bot { background: rgba(107,227,190,.1); border: 1px solid rgba(107,227,190,.3); }
  .chat-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
  .chat-question-btn { background: var(--s2); color: var(--text); border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; cursor: pointer; }
  .chat-question-btn:disabled { opacity: .5; cursor: default; }
  footer { margin-top: 48px; border-top: 1px solid var(--line); padding: 24px 0 40px; color: var(--muted); font-size: .88rem; }
  footer p { margin: 4px 0; }
  .js-ready .reveal { opacity: 0; transform: translateY(14px); transition: opacity .5s ease, transform .5s ease; }
  .js-ready .reveal.is-visible { opacity: 1; transform: none; }
  @media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    .js-ready .reveal { opacity: 1; transform: none; transition: none; }
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


def _stat_cards(verified: dict) -> str:
    """3 tarjetas grandes con los números que más importan de un vistazo —
    los mismos que ya están citados en el grid de abajo, solo con más
    jerarquía visual (estilo tablero)."""
    keys = (("revenue", "Ingresos"), ("ebitda", "EBITDA (derivado)"), ("net_income", "Utilidad neta"))
    cards = []
    for key, label in keys:
        cv = verified.get(key)
        if cv is None:
            continue
        icon = _CONCEPT_ICONS.get(key, "🔎")
        cards.append(
            f"""
      <div class="stat-card reveal">
        <span class="stat-icon" aria-hidden="true">{icon}</span>
        <div>
          <p class="stat-label">{_esc(label)}</p>
          <p class="stat-value"{_count_attr(cv.value)}>{_esc(_fmt_money(cv.value))}</p>
        </div>
      </div>"""
        )
    if not cards:
        return ""
    return f'<div class="stat-row">{"".join(cards)}</div>'


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
      <article class="card reveal" style="transition-delay:{delay}ms" data-key="{_esc(key)}" data-figure-label="{_esc(label)}">
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
      <span class="brand">Quant <span>Lab</span></span>
      <nav class="nav" aria-label="Secciones">
        <a href="#reporte">1 · Reporte</a>
        <a href="#simulacion">2 · Simulación</a>
        <a href="#diario">3 · Diario</a>
        <a href="#como-funciona">Cómo se verifica</a>
      </nav>
      <span class="pill">Solo investigación</span>
    </div>
  </header>
  <div class="strip"><div class="wrap">Análisis informativo, no es asesoría financiera. Nunca dice "compra" ni "vende": la decisión es tuya.</div></div>"""


def _hero(empresa_ejemplo: str, filing_doc_id: str, generated_at: datetime) -> str:
    return f"""
  <section class="hero wrap">
    <h1>Qué dice el reporte, y qué podría pasar.</h1>
    <p>Dos capas separadas a propósito: arriba, hechos con cita del documento oficial; abajo, escenarios
    simulados que no son predicciones. Nunca se mezclan.</p>
    <div class="chips">
      <span class="pill">{_esc(empresa_ejemplo)}</span>
      <span class="pill">{_esc(filing_doc_id)}</span>
      <span class="pill">generado {_esc(generated_at.strftime('%Y-%m-%d %H:%M UTC'))}</span>
    </div>
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
    stat_cards = _stat_cards(verified)
    revenue_series_points = [
        {"period_end": cv.period_end, "value": cv.value}
        for cv in (verified.get("revenue_series") or [])
        if cv.value is not None
    ]
    revenue_chart = _revenue_line_chart_svg(revenue_series_points)
    chart_card = (
        f'<div class="card chart-card reveal"><h3>📈 Ingresos por año (mismo documento citado arriba)</h3>{revenue_chart}</div>'
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
<title>{_esc(empresa_ejemplo)} — Reporte Quant Lab</title>
<style>{_STYLE}</style>
</head>
<body>
  <div id="scroll-progress"></div>
  {_site_header()}
  {_hero(empresa_ejemplo, filing_doc_id, generated_at)}
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
  <script>{_SCRIPT}</script>
</body>
</html>
"""
