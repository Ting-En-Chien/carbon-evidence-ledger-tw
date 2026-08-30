/**
 * Reusable analysis-result KPI count-up (Scope totals, counts, etc.).
 * Independent of hero_emissions_countup.js — do not duplicate the hero.
 * Fail-open: DOM defaults to the final formatted value.
 * Presentation only. No network. No per-row timers.
 */
(function () {
  var w;
  var doc;
  try {
    w = window;
    doc = document;
  } catch (err) {
    return;
  }
  if (!doc || !doc.documentElement) return;

  if (!w.__celKpiSeen) w.__celKpiSeen = {};
  if (!w.__celKpiGen) w.__celKpiGen = {};

  var DURATION_MS = 1200;

  function reducedMotion() {
    try {
      return w.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {
      return false;
    }
  }

  function fmt(n, decimals) {
    if (decimals > 0) {
      return n.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });
    }
    return Math.round(n).toLocaleString();
  }

  function seenKey(el) {
    var run = el.getAttribute("data-cel-kpi-run") || "";
    var key = el.getAttribute("data-cel-kpi-key") || "";
    return run + "|" + key;
  }

  function showFinal(el) {
    var finalText = el.getAttribute("data-cel-final") || el.textContent || "";
    el.textContent = finalText;
    el.setAttribute("data-cel-kpi-done", "1");
  }

  function runCountUp(el, token) {
    var finalText = el.getAttribute("data-cel-final") || el.textContent || "";
    var target = parseFloat(el.getAttribute("data-cel-target") || "");
    var decimals = parseInt(el.getAttribute("data-cel-decimals") || "0", 10);
    if (!isFinite(target)) {
      showFinal(el);
      if (token) w.__celKpiSeen[token] = 1;
      return;
    }

    var gen = (w.__celKpiGen[token || "_"] =
      (w.__celKpiGen[token || "_"] || 0) + 1);
    var myGen = gen;
    el.setAttribute("data-cel-kpi-done", "1");
    el.textContent = fmt(0, decimals);

    var t0 = performance.now();
    var finished = false;

    function finish() {
      if (finished) return;
      if (token && w.__celKpiGen[token] !== myGen) return;
      if (!token && w.__celKpiGen._ !== myGen) return;
      finished = true;
      el.textContent = finalText;
      if (token) w.__celKpiSeen[token] = 1;
    }

    w.setTimeout(function () {
      finish();
    }, DURATION_MS + 400);

    function tick(now) {
      if (token && w.__celKpiGen[token] !== myGen) return;
      if (!token && w.__celKpiGen._ !== myGen) return;
      if (finished) return;
      var t = Math.min(1, Math.max(0, (now - t0) / DURATION_MS));
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(target * eased, decimals);
      if (t < 1) {
        w.requestAnimationFrame(tick);
      } else {
        finish();
      }
    }
    w.requestAnimationFrame(tick);
  }

  function handle(el) {
    if (!el || el.nodeType !== 1) return;
    var token = seenKey(el);
    var play = el.getAttribute("data-cel-kpi-play") === "1";

    if (el.getAttribute("data-cel-kpi-done") === "1") {
      return;
    }

    if (token && w.__celKpiSeen[token]) {
      showFinal(el);
      return;
    }

    if (!play || reducedMotion()) {
      showFinal(el);
      if (token && play && reducedMotion()) w.__celKpiSeen[token] = 1;
      return;
    }

    try {
      runCountUp(el, token);
    } catch (errPlay) {
      showFinal(el);
      if (token) w.__celKpiSeen[token] = 1;
    }
  }

  function scan() {
    var nodes = doc.querySelectorAll('[data-cel-kpi-metric="1"]');
    for (var i = 0; i < nodes.length; i++) {
      handle(nodes[i]);
    }
  }

  if (doc.documentElement.getAttribute("data-cel-kpi-bound") !== "1") {
    doc.documentElement.setAttribute("data-cel-kpi-bound", "1");
    try {
      var mo = new w.MutationObserver(function () {
        scan();
      });
      mo.observe(doc.body || doc.documentElement, {
        childList: true,
        subtree: true,
      });
    } catch (eMo) {}
    w.__celKpiScan = scan;
  }

  scan();
  try {
    w.requestAnimationFrame(function () {
      scan();
      w.setTimeout(scan, 50);
    });
  } catch (eRaf) {
    scan();
  }
})();
