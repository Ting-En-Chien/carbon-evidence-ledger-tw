/**
 * Phase 11C — fail-open viewport scroll reveal + count-up.
 * Progressive enhancement only. Content stays visible unless motion-ready
 * is added AFTER a working IntersectionObserver is initialized.
 * Presentation only. No network. No Streamlit reruns.
 *
 * Runs in the Streamlit main document via st.html(unsafe_allow_javascript),
 * with a parent-document fallback when executed inside components.html.
 */
(function () {
  var w;
  var doc;
  try {
    // Prefer the document this script actually runs in (st.html → main page).
    // Only climb to parent when we are inside a same-origin iframe binder.
    if (window.parent && window.parent !== window) {
      try {
        void window.parent.document.documentElement;
        w = window.parent;
        doc = w.document;
      } catch (errParent) {
        w = window;
        doc = document;
      }
    } else {
      w = window;
      doc = document;
    }
  } catch (err) {
    return; // no usable document → never hide content
  }
  if (!doc || !doc.documentElement) return;

  // Re-scan after Streamlit rerenders without rebinding listeners.
  if (doc.documentElement.getAttribute("data-cel-scroll-bound") === "1") {
    if (typeof w.__celObserveTargets === "function") {
      try {
        w.__celObserveTargets();
      } catch (e) {}
    }
    return;
  }

  // Fail-open: do not add motion-ready until observer init succeeds.
  if (typeof w.IntersectionObserver !== "function") {
    return;
  }

  var reduce = false;
  try {
    reduce = w.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (e) {
    reduce = false;
  }

  // In-memory one-time keys (survive Streamlit rerenders on this window;
  // clear on hard refresh so count-up can play again).
  if (!w.__celSeenKeys) w.__celSeenKeys = {};

  // Reduced motion: never gate visibility; still mark for count finals.
  if (reduce) {
    doc.documentElement.setAttribute("data-cel-scroll-bound", "1");
    function revealAllReduced() {
      var nodes = doc.querySelectorAll("[data-cel-reveal]");
      for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        el.classList.add("is-visible");
        el.setAttribute("data-cel-animated", "1");
        var key = el.getAttribute("data-cel-key") || "";
        if (key) w.__celSeenKeys[key] = 1;
        var counts = el.querySelectorAll("[data-cel-count]");
        for (var c = 0; c < counts.length; c++) {
          var n = counts[c];
          n.setAttribute("data-cel-counted", "1");
          n.textContent = n.getAttribute("data-cel-final") || n.textContent;
        }
      }
    }
    revealAllReduced();
    w.__celObserveTargets = revealAllReduced;
    try {
      var moR = new w.MutationObserver(function () {
        revealAllReduced();
      });
      moR.observe(doc.body || doc.documentElement, {
        childList: true,
        subtree: true,
      });
    } catch (e2) {}
    return;
  }

  function fmtInt(n) {
    return Math.round(n).toLocaleString();
  }
  function fmtFloat(n, d) {
    return n.toLocaleString(undefined, {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    });
  }

  var COUNT_MS = 1100;

  function runCountUp(el) {
    if (!el || el.getAttribute("data-cel-counted") === "1") return;
    var finalText = el.getAttribute("data-cel-final") || el.textContent || "";
    var target = parseFloat(el.getAttribute("data-cel-target") || "");
    var decimals = parseInt(el.getAttribute("data-cel-decimals") || "0", 10);
    var total = parseInt(el.getAttribute("data-cel-ratio-total") || "0", 10);
    var isRatio = el.getAttribute("data-cel-ratio") === "1";
    var delay = parseInt(el.getAttribute("data-cel-delay") || "0", 10);
    var duration = parseInt(el.getAttribute("data-cel-duration") || "", 10);
    if (!isFinite(duration) || duration <= 0) duration = COUNT_MS;
    el.setAttribute("data-cel-counted", "1");
    if (!isFinite(target)) {
      el.textContent = finalText;
      return;
    }

    function start() {
      var t0 = performance.now();
      function tick(now) {
        var t = Math.min(1, (now - t0) / duration);
        var eased = 1 - Math.pow(1 - t, 3);
        if (isRatio) {
          el.textContent = fmtInt(target * eased) + " / " + fmtInt(total);
        } else if (decimals > 0) {
          el.textContent = fmtFloat(target * eased, decimals);
        } else {
          el.textContent = fmtInt(target * eased);
        }
        if (t < 1) w.requestAnimationFrame(tick);
        else el.textContent = finalText;
      }
      el.textContent = isRatio
        ? "0 / " + fmtInt(total)
        : decimals > 0
          ? fmtFloat(0, decimals)
          : "0";
      w.requestAnimationFrame(tick);
    }

    if (delay > 0) w.setTimeout(start, delay);
    else start();
  }

  function wasSeen(key) {
    if (!key) return false;
    try {
      return !!w.__celSeenKeys[key];
    } catch (e) {
      return false;
    }
  }

  function rememberKey(key) {
    if (!key) return;
    try {
      w.__celSeenKeys[key] = 1;
    } catch (e) {}
  }

  function markVisible(el, opts) {
    opts = opts || {};
    if (!el || el.getAttribute("data-cel-animated") === "1") return;
    el.classList.add("is-visible");
    el.setAttribute("data-cel-animated", "1");
    rememberKey(el.getAttribute("data-cel-key") || "");
    var counts = el.querySelectorAll("[data-cel-count]");
    for (var i = 0; i < counts.length; i++) {
      if (opts.skipCount) {
        counts[i].setAttribute("data-cel-counted", "1");
        counts[i].textContent =
          counts[i].getAttribute("data-cel-final") || counts[i].textContent;
      } else {
        runCountUp(counts[i]);
      }
    }
  }

  function viewportHeight() {
    return w.innerHeight || doc.documentElement.clientHeight || 0;
  }

  function isInViewport(el) {
    try {
      var rect = el.getBoundingClientRect();
      var vh = viewportHeight();
      // Partially visible and not far below the fold.
      return rect.top < vh * 0.92 && rect.bottom > 0 && rect.top < vh;
    } catch (e) {
      return false;
    }
  }

  var lastY = w.scrollY || doc.documentElement.scrollTop || 0;
  var scrollingDown = true;
  var initialPass = true;
  var motionArmed = false;

  function readScrollY() {
    var y = w.scrollY || doc.documentElement.scrollTop || 0;
    // Streamlit often scrolls an inner container rather than the window.
    try {
      var roots = [
        doc.querySelector('[data-testid="stAppViewContainer"]'),
        doc.querySelector(".stApp"),
        doc.querySelector("section.main"),
        doc.scrollingElement,
      ];
      for (var i = 0; i < roots.length; i++) {
        var node = roots[i];
        if (node && typeof node.scrollTop === "number" && node.scrollTop > y) {
          y = node.scrollTop;
        }
      }
    } catch (e) {}
    return y;
  }

  function onScroll() {
    var y = readScrollY();
    scrollingDown = y >= lastY - 2;
    lastY = y;
  }

  function shouldReveal(entry) {
    if (!entry.isIntersecting) return false;
    var el = entry.target;
    if (el.getAttribute("data-cel-animated") === "1") return false;
    if (initialPass) return true;
    if (scrollingDown) return true;
    var vh = viewportHeight();
    var top = entry.boundingClientRect.top;
    return top >= 0 && top < vh * 0.85;
  }

  var obs;
  try {
    obs = new w.IntersectionObserver(
      function (entries) {
        for (var i = 0; i < entries.length; i++) {
          var entry = entries[i];
          if (!shouldReveal(entry)) continue;
          markVisible(entry.target);
          try {
            obs.unobserve(entry.target);
          } catch (err) {}
        }
        initialPass = false;
      },
      { threshold: [0, 0.12, 0.25], root: null, rootMargin: "0px 0px -8% 0px" }
    );
  } catch (errObs) {
    return; // observer creation failed → never hide
  }

  function observeTargets() {
    var nodes = doc.querySelectorAll(
      "[data-cel-reveal]:not([data-cel-observed='1'])"
    );
    for (var j = 0; j < nodes.length; j++) {
      var el = nodes[j];
      el.setAttribute("data-cel-observed", "1");
      var key = el.getAttribute("data-cel-key") || "";
      if (wasSeen(key)) {
        // Already revealed this page load — keep visible, do not replay count-up.
        markVisible(el, { skipCount: true });
        continue;
      }
      try {
        obs.observe(el);
      } catch (errObs2) {
        markVisible(el, { skipCount: true });
        continue;
      }
      // Streamlit late-DOM: reveal immediately if already on-screen after arm.
      if (motionArmed && isInViewport(el)) {
        markVisible(el);
        try {
          obs.unobserve(el);
        } catch (eUn) {}
      }
    }
  }

  function bindScrollListeners() {
    try {
      w.addEventListener("scroll", onScroll, { passive: true, capture: true });
    } catch (eScroll) {}
    try {
      var roots = [
        doc.querySelector('[data-testid="stAppViewContainer"]'),
        doc.querySelector(".stApp"),
        doc.querySelector("section.main"),
      ];
      for (var i = 0; i < roots.length; i++) {
        if (roots[i]) {
          roots[i].addEventListener("scroll", onScroll, {
            passive: true,
            capture: true,
          });
        }
      }
    } catch (eRoot) {}
  }

  function armMotionReady() {
    if (motionArmed) return;
    // Reveal anything already in the viewport BEFORE gating CSS.
    observeTargets();
    var pending = doc.querySelectorAll(
      "[data-cel-reveal]:not(.is-visible):not([data-cel-animated='1'])"
    );
    for (var i = 0; i < pending.length; i++) {
      var el = pending[i];
      if (isInViewport(el)) {
        markVisible(el);
        try {
          obs.unobserve(el);
        } catch (e3) {}
      }
    }
    doc.documentElement.classList.add("motion-ready");
    motionArmed = true;
    // Failsafe: if anything is still gated after 2.5s, force finals visible.
    w.setTimeout(function () {
      var stuck = doc.querySelectorAll(
        "html.motion-ready [data-cel-reveal]:not(.is-visible):not([data-cel-animated='1'])"
      );
      if (!stuck.length) return;
      for (var s = 0; s < stuck.length; s++) {
        markVisible(stuck[s], { skipCount: true });
      }
    }, 2500);
  }

  doc.documentElement.setAttribute("data-cel-scroll-bound", "1");
  w.__celObserveTargets = observeTargets;
  bindScrollListeners();

  // Arm after a frame so targets from this Streamlit run can exist;
  // MutationObserver covers widgets rendered after the injector.
  w.requestAnimationFrame(function () {
    try {
      armMotionReady();
    } catch (eArm) {
      doc.documentElement.classList.remove("motion-ready");
      return;
    }
    try {
      var mo = new w.MutationObserver(function () {
        observeTargets();
      });
      mo.observe(doc.body || doc.documentElement, {
        childList: true,
        subtree: true,
      });
    } catch (eMo) {}
  });
})();
