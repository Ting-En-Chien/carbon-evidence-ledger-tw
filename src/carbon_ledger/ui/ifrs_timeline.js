/**
 * IFRS disclosure timeline track animation.
 * Presentation only. Does not mutate capital, applicability, or obligations.
 * Fail-open: DOM defaults to the final progress width.
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

  if (!w.__celTimelineSeen) w.__celTimelineSeen = {};
  if (!w.__celTimelineGen) w.__celTimelineGen = {};

  var DURATION_MS = 1400;
  var START_HOLD_MS = 450;

  function reducedMotion() {
    try {
      return w.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {
      return false;
    }
  }

  function runKey(root) {
    return root.getAttribute("data-cel-timeline-run") || "";
  }

  function targetPct(root) {
    var raw = parseFloat(root.getAttribute("data-cel-timeline-progress") || "0");
    if (!isFinite(raw)) return 0;
    return Math.max(0, Math.min(100, raw));
  }

  function logicalCount(root) {
    var n = parseInt(root.getAttribute("data-cel-timeline-count") || "0", 10);
    return n > 0 ? n : 0;
  }

  function revealCap(root) {
    var raw = parseInt(root.getAttribute("data-cel-timeline-reveal") || "-1", 10);
    return isFinite(raw) ? raw : -1;
  }

  function scopedDots(root, scope) {
    return root.querySelectorAll(
      "[data-cel-timeline-scope='" + scope + "'] [data-cel-timeline-dot]"
    );
  }

  function setWidth(bar, pct) {
    bar.style.width = pct + "%";
    bar.setAttribute("data-cel-timeline-width", String(pct));
  }

  function applyDots(nodes, reach, cap) {
    var i;
    for (i = 0; i < nodes.length; i++) {
      if (i <= reach + 0.02 && i <= cap + 0.02) {
        nodes[i].setAttribute("data-cel-timeline-visible", "1");
      } else {
        nodes[i].setAttribute("data-cel-timeline-visible", "0");
      }
    }
  }

  function revealMobileRail(root, reach, cap) {
    var items = root.querySelectorAll(
      "[data-cel-timeline-scope='mobile'] [data-cel-timeline-mobile-item]"
    );
    var i;
    var lastReached = Math.min(Math.floor(reach + 0.02), cap);
    for (i = 0; i < items.length; i++) {
      if (i < lastReached) {
        items[i].setAttribute("data-cel-rail-reached", "1");
      } else {
        items[i].setAttribute("data-cel-rail-reached", "0");
      }
    }
  }

  function revealDots(root, pct) {
    var count = logicalCount(root);
    if (!count) return;
    var cap = revealCap(root);
    var reach = count <= 1 ? 0 : (pct / 100) * (count - 1);
    applyDots(scopedDots(root, "desktop"), reach, cap);
    applyDots(scopedDots(root, "mobile"), reach, cap);
    revealMobileRail(root, reach, cap);
  }

  function showFinal(root) {
    var bar = root.querySelector("[data-cel-timeline-bar]");
    var pct = targetPct(root);
    if (bar) setWidth(bar, pct);
    revealDots(root, pct);
    root.setAttribute("data-cel-timeline-done", "1");
  }

  function animate(root, token) {
    var bar = root.querySelector("[data-cel-timeline-bar]");
    if (!bar) {
      showFinal(root);
      if (token) w.__celTimelineSeen[token] = 1;
      return;
    }
    var gen = (w.__celTimelineGen[token || "_"] =
      (w.__celTimelineGen[token || "_"] || 0) + 1);
    var myGen = gen;
    var end = targetPct(root);
    setWidth(bar, 0);
    revealDots(root, 0);
    root.setAttribute("data-cel-timeline-done", "0");

    var t0 = 0;
    var finished = false;

    function finish() {
      if (finished) return;
      if (token && w.__celTimelineGen[token] !== myGen) return;
      finished = true;
      setWidth(bar, end);
      revealDots(root, end);
      root.setAttribute("data-cel-timeline-done", "1");
      if (token) w.__celTimelineSeen[token] = 1;
    }

    w.setTimeout(finish, START_HOLD_MS + DURATION_MS + 250);

    function tick(now) {
      if (token && w.__celTimelineGen[token] !== myGen) return;
      if (finished) return;
      if (!t0) t0 = now;
      var t = Math.min(1, Math.max(0, (now - t0) / DURATION_MS));
      var eased = 1 - Math.pow(1 - t, 3);
      var pct = end * eased;
      setWidth(bar, pct);
      revealDots(root, pct);
      if (t < 1) {
        w.requestAnimationFrame(tick);
      } else {
        finish();
      }
    }
    w.setTimeout(function () {
      if (token && w.__celTimelineGen[token] !== myGen) return;
      if (finished) return;
      w.requestAnimationFrame(tick);
    }, START_HOLD_MS);
  }

  function handle(root) {
    if (!root || root.nodeType !== 1) return;
    var token = runKey(root);
    var play = root.getAttribute("data-cel-timeline-play") === "1";

    if (root.getAttribute("data-cel-timeline-done") === "1") {
      return;
    }
    if (token && w.__celTimelineSeen[token]) {
      showFinal(root);
      return;
    }
    if (!play || reducedMotion()) {
      showFinal(root);
      if (token && play && reducedMotion()) w.__celTimelineSeen[token] = 1;
      return;
    }
    try {
      animate(root, token);
    } catch (errPlay) {
      showFinal(root);
      if (token) w.__celTimelineSeen[token] = 1;
    }
  }

  function scan() {
    var nodes = doc.querySelectorAll("[data-cel-timeline='1']");
    for (var i = 0; i < nodes.length; i++) {
      handle(nodes[i]);
    }
  }

  if (doc.documentElement.getAttribute("data-cel-timeline-bound") !== "1") {
    doc.documentElement.setAttribute("data-cel-timeline-bound", "1");
    try {
      var mo = new w.MutationObserver(function () {
        scan();
      });
      mo.observe(doc.body || doc.documentElement, {
        childList: true,
        subtree: true,
      });
    } catch (eMo) {}
    w.__celTimelineScan = scan;
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
