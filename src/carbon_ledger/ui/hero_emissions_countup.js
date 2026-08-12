/**
 * Dedicated primary emissions KPI count-up (已計算排放量).
 * Independent of scroll-reveal / viewport observers.
 * Fail-open: DOM defaults to the final formatted value.
 * Presentation only. No network.
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

  if (!w.__celHeroSeen) w.__celHeroSeen = {};
  if (!w.__celHeroGen) w.__celHeroGen = {};

  var DURATION_MS = 1400;

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

  function showFinal(el) {
    var finalText = el.getAttribute("data-cel-final") || el.textContent || "";
    el.textContent = finalText;
    el.setAttribute("data-cel-hero-done", "1");
  }

  function runCountUp(el, run) {
    var finalText = el.getAttribute("data-cel-final") || el.textContent || "";
    var target = parseFloat(el.getAttribute("data-cel-target") || "");
    var decimals = parseInt(el.getAttribute("data-cel-decimals") || "0", 10);
    if (!isFinite(target)) {
      showFinal(el);
      if (run) w.__celHeroSeen[run] = 1;
      return;
    }

    var gen = (w.__celHeroGen[run || "_"] = (w.__celHeroGen[run || "_"] || 0) + 1);
    var myGen = gen;
    el.setAttribute("data-cel-hero-done", "1");
    el.textContent = fmt(0, decimals);

    var t0 = performance.now();
    var finished = false;

    function finish() {
      if (finished) return;
      if (run && w.__celHeroGen[run] !== myGen) return;
      if (!run && w.__celHeroGen._ !== myGen) return;
      finished = true;
      el.textContent = finalText;
      if (run) w.__celHeroSeen[run] = 1;
    }

    // Failsafe: never leave the KPI stuck at 0 / mid-count.
    w.setTimeout(function () {
      finish();
    }, DURATION_MS + 400);

    function tick(now) {
      if (run && w.__celHeroGen[run] !== myGen) return;
      if (!run && w.__celHeroGen._ !== myGen) return;
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
    var run = el.getAttribute("data-cel-hero-run") || "";
    var play = el.getAttribute("data-cel-hero-play") === "1";

    if (el.getAttribute("data-cel-hero-done") === "1") {
      // Node already processed; keep final text if Streamlit reuses markup.
      return;
    }

    // Same analysis already finished counting in this tab → no replay.
    if (run && w.__celHeroSeen[run]) {
      showFinal(el);
      return;
    }

    if (!play || reducedMotion()) {
      showFinal(el);
      if (run && play && reducedMotion()) w.__celHeroSeen[run] = 1;
      return;
    }

    try {
      runCountUp(el, run);
    } catch (errPlay) {
      showFinal(el);
      if (run) w.__celHeroSeen[run] = 1;
    }
  }

  function scan() {
    var nodes = doc.querySelectorAll('[data-cel-hero-emissions="1"]');
    for (var i = 0; i < nodes.length; i++) {
      handle(nodes[i]);
    }
  }

  if (doc.documentElement.getAttribute("data-cel-hero-bound") !== "1") {
    doc.documentElement.setAttribute("data-cel-hero-bound", "1");
    try {
      var mo = new w.MutationObserver(function () {
        scan();
      });
      mo.observe(doc.body || doc.documentElement, {
        childList: true,
        subtree: true,
      });
    } catch (eMo) {}
    w.__celHeroScan = scan;
  } else if (typeof w.__celHeroScan === "function") {
    // Re-injected after Streamlit rerun — scan again without rebinding.
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
