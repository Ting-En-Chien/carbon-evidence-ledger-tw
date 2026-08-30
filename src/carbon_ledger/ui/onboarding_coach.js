/**
 * Action-driven onboarding coachmark runtime.
 *
 * Presentation only. Measures the live product element with
 * getBoundingClientRect() on every render, positions the Streamlit-rendered
 * coachmark card next to it, and paints a rounded spotlight with a light
 * dim outside the target. Never triggers a Streamlit rerun and never marks
 * a step complete.
 *
 * Runs in the Streamlit main document via st.html(unsafe_allow_javascript),
 * with a parent-document fallback when executed inside components.html.
 */
(function () {
  var w = window;
  var doc = document;
  try {
    // st.html runs in the app document.  On Community Cloud that document is
    // itself inside a same-origin wrapper, so climbing unconditionally would
    // search the wrapper and leave the real coachmark parked off-screen.
    // Only climb for the legacy components.html fallback, whose own document
    // does not contain the Streamlit coach host.
    var currentHasHost = !!doc.querySelector(".st-key-cel_onboarding_coach");
    if (!currentHasHost && window.parent && window.parent !== window) {
      var parentDoc = window.parent.document;
      if (parentDoc.querySelector(".st-key-cel_onboarding_coach")) {
        w = window.parent;
        doc = parentDoc;
      }
    }
  } catch (errParent) {}
  if (!doc || !doc.body) return;

  var HOST = ".st-key-cel_onboarding_coach";
  var SPOT_ID = "cel-onboarding-spotlight";
  var MIN_SIZE = 8;
  var GAP = 12;
  var EDGE = 12;
  var HEADER = 88;
  var OFFSCREEN = "-10000px";
  var DIR_PREF = { right: 4, left: 3, top: 2, bottom: 1 };

  var NONCE = "n" + Date.now() + "." + Math.random().toString(36).slice(2, 8);
  var root = doc.documentElement;

  function beat() {
    root.setAttribute("data-cel-coach-alive", String(Date.now()));
  }

  /** A binding whose realm was torn down stops beating; then we take over. */
  function bindingAlive() {
    var raw = root.getAttribute("data-cel-coach-alive");
    var ts = raw ? parseInt(raw, 10) : 0;
    return ts > 0 && Date.now() - ts < 1600;
  }

  function owned() {
    return root.getAttribute("data-cel-coach-owner") === NONCE;
  }

  if (root.getAttribute("data-cel-coach-bound") === "1" && bindingAlive()) {
    if (typeof w.__celCoachSync === "function") {
      try {
        w.__celCoachSync(true);
      } catch (e) {}
    }
    return;
  }
  root.setAttribute("data-cel-coach-bound", "1");
  root.setAttribute("data-cel-coach-owner", NONCE);
  beat();

  var state = {
    misses: 0,
    lastStep: "",
    scrolled: "",
    path: "",
    timer: null,
    revealToken: ""
  };

  function currentPath() {
    try {
      return String(w.location.pathname || "");
    } catch (e) {
      return "";
    }
  }

  /**
   * Hidden means hidden: offscreen, invisible and inert. Inline !important
   * beats the stylesheet's !important defaults, so the card can never be
   * left as bare text in the page flow.
   */
  function hideHost(host) {
    if (!host) return;
    host.removeAttribute("data-cel-coach-ready");
    host.removeAttribute("data-cel-coach-placement");
    host.setAttribute("data-cel-coach-pending", "1");
    var style = host.style;
    try {
      style.setProperty("visibility", "hidden", "important");
      style.setProperty("opacity", "0", "important");
      style.setProperty("pointer-events", "none", "important");
      style.setProperty("position", "fixed", "important");
      style.setProperty("left", OFFSCREEN, "important");
      style.setProperty("top", OFFSCREEN, "important");
    } catch (e) {}
  }

  function hideAllHosts() {
    var hosts;
    try {
      hosts = doc.querySelectorAll(HOST);
    } catch (e) {
      return;
    }
    for (var i = 0; i < hosts.length; i++) hideHost(hosts[i]);
  }

  function showHost(host) {
    if (!host) return;
    var style = host.style;
    try {
      style.setProperty("visibility", "visible", "important");
      style.setProperty("opacity", "1", "important");
      style.setProperty("pointer-events", "auto", "important");
    } catch (e) {}
    host.removeAttribute("data-cel-coach-pending");
    host.setAttribute("data-cel-coach-ready", "1");
  }

  /**
   * A Streamlit rerun can leave the previous host mounted for a frame. The
   * newest connected host with a config wins; every other one is hidden so
   * no stale coordinates or stale copy survive.
   */
  function pickHost() {
    var hosts;
    try {
      hosts = doc.querySelectorAll(HOST);
    } catch (e) {
      return null;
    }
    var chosen = null;
    for (var i = 0; i < hosts.length; i++) {
      var host = hosts[i];
      var connected =
        typeof host.isConnected === "boolean"
          ? host.isConnected
          : doc.body.contains(host);
      if (!connected) continue;
      var anchor = host.querySelector("[data-cel-coach-config]");
      if (!anchor || !anchor.getAttribute("data-cel-coach-config")) continue;
      chosen = host;
    }
    for (var j = 0; j < hosts.length; j++) {
      if (hosts[j] !== chosen) hideHost(hosts[j]);
    }
    return chosen;
  }

  function readConfig() {
    var host = pickHost();
    if (!host) return null;
    var anchor = host.querySelector("[data-cel-coach-config]");
    if (!anchor) return null;
    var raw = anchor.getAttribute("data-cel-coach-config");
    if (!raw) return null;
    var cfg;
    try {
      cfg = JSON.parse(raw);
    } catch (e) {
      return null;
    }
    if (!cfg || !cfg.selectors || !cfg.selectors.length) return null;
    cfg.host = host;
    return cfg;
  }

  function usable(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el === doc.body || el === doc.documentElement) return false;
    var rect;
    try {
      rect = el.getBoundingClientRect();
    } catch (e) {
      return false;
    }
    if (rect.width < MIN_SIZE || rect.height < MIN_SIZE) return false;
    var style;
    try {
      style = w.getComputedStyle(el);
    } catch (e) {
      return true;
    }
    if (!style) return true;
    if (style.display === "none") return false;
    if (style.visibility === "hidden") return false;
    if (parseFloat(style.opacity || "1") === 0) return false;
    return true;
  }

  function firstSized(root, depth) {
    if (!root || root.nodeType !== 1 || depth > 4) return null;
    if (usable(root)) return root;
    var kids = root.children || [];
    for (var i = 0; i < kids.length; i++) {
      var found = firstSized(kids[i], depth + 1);
      if (found) return found;
    }
    return null;
  }

  /** Next element in document order after el (siblings, then ancestors'). */
  function nextInDocOrder(el) {
    var cur = el;
    while (cur && cur !== doc.body) {
      if (cur.nextElementSibling) return cur.nextElementSibling;
      cur = cur.parentElement;
    }
    return null;
  }

  /**
   * Zero-size markers are legitimate anchors, so walk forward in document
   * order to the first real sized element instead of drawing a wrong box.
   */
  function resolve(el) {
    if (usable(el)) return el;
    var cur = el;
    for (var hops = 0; hops < 6; hops++) {
      var next = nextInDocOrder(cur);
      if (!next) break;
      var found = firstSized(next, 0);
      if (found) return found;
      cur = next;
    }
    var parent = el ? el.parentElement : null;
    for (var up = 0; up < 3 && parent; up++) {
      if (usable(parent)) return parent;
      parent = parent.parentElement;
    }
    return null;
  }

  function measurableContent(el) {
    if (!el || el.nodeType !== 1) return false;
    var box = contentBox(el);
    return box.width >= MIN_SIZE && box.height >= MIN_SIZE;
  }

  function isNamedSelector(sel) {
    var s = String(sel || "");
    return (
      s.indexOf("data-cel-onboarding-target") !== -1 ||
      s.indexOf("st-key-cel_onb_") !== -1
    );
  }

  /**
   * Named onboarding groups wrap several live controls. Keep the keyed
   * wrapper (or its column) even when the wrapper's own rect is empty —
   * never walk forward to a single sibling button.
   */
  function promoteGroup(el) {
    if (!el || el.nodeType !== 1) return null;
    var named = null;
    try {
      named = el.closest("[class*='st-key-cel_onb_']");
    } catch (e) {
      named = null;
    }
    if (named && named !== doc.body && named !== doc.documentElement) {
      if (measurableContent(named) || usable(named)) return named;
    }
    if (el.getAttribute && el.getAttribute("data-cel-onboarding-target")) {
      var column = null;
      try {
        column =
          el.closest('[data-testid="stColumn"]') ||
          el.closest('[data-testid="column"]') ||
          el.closest(".stColumn");
      } catch (eCol) {
        column = null;
      }
      if (column && measurableContent(column)) return column;
      var parent = el.parentElement;
      for (var up = 0; up < 8 && parent; up++) {
        if (parent === doc.body || parent === doc.documentElement) break;
        if (measurableContent(parent)) return parent;
        parent = parent.parentElement;
      }
    }
    return resolve(el);
  }

  /** True when the customer is already inside the flow this step points at. */
  function suppressed(selectors) {
    if (!selectors || !selectors.length) return false;
    for (var i = 0; i < selectors.length; i++) {
      var node;
      try {
        node = doc.querySelector(selectors[i]);
      } catch (e) {
        continue;
      }
      if (node) return true;
    }
    return false;
  }

  /** Route match fires before the new page mounts any DOM marker. */
  function routeSuppressed(patterns) {
    if (!patterns || !patterns.length) return false;
    var path = currentPath();
    if (!path) return false;
    for (var i = 0; i < patterns.length; i++) {
      var pattern = String(patterns[i] || "");
      if (pattern && path.indexOf(pattern) !== -1) return true;
    }
    return false;
  }

  function collectResolved(selectors) {
    var found = [];
    if (!selectors || !selectors.length) return found;
    for (var i = 0; i < selectors.length; i++) {
      var nodes;
      try {
        nodes = doc.querySelectorAll(selectors[i]);
      } catch (e) {
        continue;
      }
      for (var j = 0; j < nodes.length; j++) {
        var resolved = promoteGroup(nodes[j]);
        if (resolved) found.push(resolved);
      }
    }
    return found;
  }

  function firstMeasurable(found) {
    for (var i = 0; i < found.length; i++) {
      var measured = contentBox(found[i]);
      if (measured.width >= MIN_SIZE && measured.height >= MIN_SIZE) {
        return found[i];
      }
    }
    return null;
  }

  function findTarget(selectors) {
    var named = [];
    var rest = [];
    if (!selectors || !selectors.length) return null;
    for (var s = 0; s < selectors.length; s++) {
      if (isNamedSelector(selectors[s])) named.push(selectors[s]);
      else rest.push(selectors[s]);
    }
    var namedFound = collectResolved(named);
    var namedHit = firstMeasurable(namedFound);
    if (namedHit) return namedHit;
    var found = collectResolved(rest);
    if (!found.length) return null;
    var safe = mainSafeRect();
    var best = found[0];
    var bestArea = Infinity;
    for (var k = 0; k < found.length; k++) {
      var measured = contentBox(found[k]);
      var area = Math.max(0, measured.width) * Math.max(0, measured.height);
      if (!targetTooLarge(measured, safe)) return found[k];
      if (area < bestArea) {
        bestArea = area;
        best = found[k];
      }
    }
    return best;
  }

  function spotlight(create) {
    var node = doc.getElementById(SPOT_ID);
    if (!node && create) {
      node = doc.createElement("div");
      node.id = SPOT_ID;
      node.className = "cel-coach-spotlight";
      node.setAttribute("aria-hidden", "true");
      doc.body.appendChild(node);
    }
    return node;
  }

  function removeSpotlight() {
    var node = doc.getElementById(SPOT_ID);
    if (node && node.parentNode) node.parentNode.removeChild(node);
  }

  function teardown() {
    removeSpotlight();
    hideAllHosts();
    doc.documentElement.removeAttribute("data-cel-coach-step");
    doc.documentElement.removeAttribute("data-cel-coach-paused");
    doc.documentElement.removeAttribute("data-cel-coach-suppressed");
    state.misses = 0;
    state.lastStep = "";
    state.scrolled = "";
  }

  function pause() {
    removeSpotlight();
    hideAllHosts();
    doc.documentElement.setAttribute("data-cel-coach-paused", "1");
  }

  function boxOf(el) {
    var r = el.getBoundingClientRect();
    return {
      left: r.left,
      top: r.top,
      right: r.right,
      bottom: r.bottom,
      width: r.width,
      height: r.height
    };
  }

  function visibleSidebarRect() {
    var el = doc.querySelector('[data-testid="stSidebar"]');
    if (!el) return null;
    var r = boxOf(el);
    if (r.width < 80 || r.height < 40) return null;
    if (r.right <= GAP) return null;
    return r;
  }

  function mainSafeRect() {
    var vw = w.innerWidth || doc.documentElement.clientWidth || 1200;
    var vh = w.innerHeight || doc.documentElement.clientHeight || 800;
    var left = EDGE;
    var top = EDGE;
    var right = vw - EDGE;
    var bottom = vh - EDGE;
    var sidebar = visibleSidebarRect();
    if (sidebar) {
      left = Math.max(left, Math.ceil(sidebar.right) + GAP);
    }
    var header = doc.querySelector('[data-testid="stHeader"]');
    if (header && usable(header)) {
      var hb = boxOf(header);
      if (hb.bottom > 0) top = Math.max(top, Math.ceil(hb.bottom) + GAP);
    }
    var marker = doc.querySelector(".cel-topbar-marker");
    if (marker) {
      var row =
        (marker.closest && marker.closest('[data-testid="stHorizontalBlock"]')) ||
        marker;
      var tb = boxOf(row);
      if (tb.bottom > 0) top = Math.max(top, Math.ceil(tb.bottom) + GAP);
    }
    var footer = doc.querySelector(
      "[data-cel-boundary-footer], .st-key-cel_boundary_footer"
    );
    if (footer && usable(footer)) {
      var fb = boxOf(footer);
      if (fb.top > 0 && fb.top < vh) {
        bottom = Math.min(bottom, Math.floor(fb.top) - GAP);
      }
    }
    if (right - left < 96) right = Math.min(vw - EDGE, left + 96);
    if (bottom - top < 80) bottom = Math.min(vh - EDGE, top + 80);
    return {
      left: left,
      top: top,
      right: right,
      bottom: bottom,
      width: right - left,
      height: bottom - top
    };
  }

  function targetTooLarge(box, safe) {
    var safeW = Math.max(1, safe.width || safe.right - safe.left);
    var vh = w.innerHeight || doc.documentElement.clientHeight || 800;
    return box.width > safeW * 0.7 || box.height > vh * 0.55;
  }

  /**
   * Streamlit containers and markdown blocks stretch to the full main
   * column. Spotlight and placement must wrap the ink of the text plus the
   * live controls, not that empty full-width box — otherwise "right of the
   * target" is always off-screen.
   */
  function contentBox(el) {
    var union = null;
    function add(r) {
      if (!r || r.width < 1 || r.height < 1) return;
      if (!union) {
        union = {
          left: r.left,
          top: r.top,
          right: r.right,
          bottom: r.bottom
        };
        return;
      }
      union.left = Math.min(union.left, r.left);
      union.top = Math.min(union.top, r.top);
      union.right = Math.max(union.right, r.right);
      union.bottom = Math.max(union.bottom, r.bottom);
    }
    try {
      var walker = doc.createTreeWalker(el, w.NodeFilter.SHOW_TEXT);
      var node;
      while ((node = walker.nextNode())) {
        if (!String(node.nodeValue || "").trim()) continue;
        var range = doc.createRange();
        range.selectNodeContents(node);
        var r = range.getBoundingClientRect();
        var parent = node.parentElement;
        var display = "";
        var fontSize = 16;
        try {
          if (parent) {
            var style = w.getComputedStyle(parent);
            display = String(style.display || "");
            fontSize = parseFloat(style.fontSize) || 16;
          }
        } catch (errStyle) {}
        var vwNow = w.innerWidth || doc.documentElement.clientWidth || 1200;
        var text = String(node.nodeValue || "").trim();
        var wideColumn = r.width > vwNow * 0.7;
        if (wideColumn) {
          var hasCJK = /[\u4e00-\u9fff]/.test(text);
          var inkW = Math.min(
            r.width,
            Math.max(MIN_SIZE, text.length * fontSize * (hasCJK ? 1.05 : 0.7))
          );
          add({
            left: r.left,
            top: r.top,
            right: r.left + inkW,
            bottom: r.bottom
          });
          continue;
        }
        add(r);
      }
    } catch (e) {}
    var parts;
    try {
      parts = el.querySelectorAll(
        "button, input, textarea, select, label, " +
          "[data-testid='stAlert'], [data-testid='stNotification'], " +
          "[data-testid='stFileUploader'], [data-baseweb='select'], " +
          "[data-testid='stCheckbox'], [data-testid='stDateInput'], " +
          "[data-testid='stNumberInput'], [data-testid='stWidgetLabel'], " +
          "[role='radiogroup'], [role='radio']"
      );
    } catch (e) {
      parts = [];
    }
    for (var i = 0; i < parts.length; i++) {
      var control = parts[i];
      if (!usable(control)) continue;
      if (control.closest && control.closest(HOST)) continue;
      add(boxOf(control));
    }
    if (!union) {
      var full = boxOf(el);
      return {
        left: full.left,
        top: full.top,
        right: full.right,
        bottom: full.bottom,
        width: full.width,
        height: full.height
      };
    }
    return {
      left: union.left,
      top: union.top,
      right: union.right,
      bottom: union.bottom,
      width: union.right - union.left,
      height: union.bottom - union.top
    };
  }

  function clamp(value, minV, maxV) {
    if (maxV < minV) return minV;
    return Math.max(minV, Math.min(maxV, value));
  }

  function areaOverlap(a, b) {
    var w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    var h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 0 && h > 0 ? w * h : 0;
  }

  function inside(outer, inner) {
    return (
      inner.left >= outer.left - 1 &&
      inner.top >= outer.top - 1 &&
      inner.right <= outer.right + 1 &&
      inner.bottom <= outer.bottom + 1
    );
  }

  function collectProtected(target) {
    var sel =
      "input, textarea, select, button, [role='radio'], " +
      "[data-testid='stFileUploader'], [data-testid='stAlert'], " +
      "[data-testid='stNotification'], [data-baseweb='select'], " +
      "[data-testid='stCheckbox'], [data-testid='stDateInput'], " +
      "[data-testid='stNumberInput'], [data-testid='stWidgetLabel']";
    var nodes;
    try {
      nodes = doc.querySelectorAll(sel);
    } catch (e) {
      return [];
    }
    var out = [];
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!usable(el)) continue;
      if (el === target || (target.contains && target.contains(el))) continue;
      if (el.closest && el.closest(HOST)) continue;
      if (el.closest && el.closest('[data-testid="stToolbar"]')) continue;
      if (el.closest && el.closest('[data-testid="stStatusWidget"]')) continue;
      var r = boxOf(el);
      if (r.width < MIN_SIZE || r.height < MIN_SIZE) continue;
      var vwNow = w.innerWidth || doc.documentElement.clientWidth || 1200;
      if (r.width > vwNow * 0.55 && r.height < 40) continue;
      out.push({ el: el, rect: r });
    }
    var header = doc.querySelector('[data-testid="stHeader"]');
    if (header && usable(header)) {
      var headerBox = boxOf(header);
      if (headerBox.width >= MIN_SIZE && headerBox.height >= MIN_SIZE) {
        out.push({ el: header, rect: headerBox });
      }
    }
    var sidebar = visibleSidebarRect();
    if (sidebar) {
      var sideEl = doc.querySelector('[data-testid="stSidebar"]');
      if (sideEl) out.push({ el: sideEl, rect: sidebar });
    }
    var marker = doc.querySelector(".cel-topbar-marker");
    if (marker) {
      var row =
        (marker.closest && marker.closest('[data-testid="stHorizontalBlock"]')) ||
        marker;
      if (row && usable(row) && row !== target) {
        var rowBox = boxOf(row);
        if (rowBox.width >= MIN_SIZE && rowBox.height >= MIN_SIZE) {
          out.push({ el: row, rect: rowBox });
        }
      }
    }
    return out;
  }

  function applyHostPosition(host, left, top, name) {
    try {
      host.style.setProperty("position", "fixed", "important");
      host.style.setProperty("left", Math.round(left) + "px", "important");
      host.style.setProperty("top", Math.round(top) + "px", "important");
    } catch (e) {
      host.style.left = Math.round(left) + "px";
      host.style.top = Math.round(top) + "px";
    }
    host.setAttribute("data-cel-coach-placement", name);
  }

  function place(host, rect, target) {
    var cw = host.offsetWidth || 300;
    var ch = host.offsetHeight || 130;
    if (cw < MIN_SIZE || ch < MIN_SIZE) return false;
    var safe = mainSafeRect();
    var targetBox = {
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom
    };
    var protectedEls = collectProtected(target);
    var minLeft = safe.left;
    var maxLeft = safe.right - cw;
    var minTop = safe.top;
    var maxTop = safe.bottom - ch;
    var options = [
      {
        name: "right",
        left: clamp(targetBox.right + GAP, minLeft, maxLeft),
        top: clamp(targetBox.top, minTop, maxTop),
        space: safe.right - (targetBox.right + GAP) - cw
      },
      {
        name: "left",
        left: clamp(targetBox.left - GAP - cw, minLeft, maxLeft),
        top: clamp(targetBox.top, minTop, maxTop),
        space: targetBox.left - GAP - safe.left - cw
      },
      {
        name: "top",
        left: clamp(targetBox.left, minLeft, maxLeft),
        top: targetBox.top - GAP - ch,
        space: targetBox.top - GAP - safe.top - ch
      },
      {
        name: "bottom",
        left: clamp(targetBox.left, minLeft, maxLeft),
        top: targetBox.bottom + GAP,
        space: safe.bottom - (targetBox.bottom + GAP) - ch
      }
    ];
    function insideSafe(box) {
      return (
        box.left >= safe.left - 0.5 &&
        box.top >= safe.top - 0.5 &&
        box.right <= safe.right + 0.5 &&
        box.bottom <= safe.bottom + 0.5
      );
    }
    var scored = [];
    for (var i = 0; i < options.length; i++) {
      var cand = options[i];
      var box = {
        left: cand.left,
        top: cand.top,
        right: cand.left + cw,
        bottom: cand.top + ch
      };
      if (!insideSafe(box)) continue;
      if (areaOverlap(box, targetBox) > 0) continue;
      var nearest = Infinity;
      var blocked = false;
      for (var p = 0; p < protectedEls.length; p++) {
        var pr = protectedEls[p].rect;
        if (areaOverlap(box, pr) > 0) {
          blocked = true;
          break;
        }
        var dx = Math.max(pr.left - box.right, box.left - pr.right, 0);
        var dy = Math.max(pr.top - box.bottom, box.top - pr.bottom, 0);
        nearest = Math.min(nearest, Math.sqrt(dx * dx + dy * dy));
      }
      if (blocked) continue;
      scored.push({
        name: cand.name,
        left: cand.left,
        top: cand.top,
        space: cand.space,
        nearest: nearest === Infinity ? 0 : nearest
      });
    }
    scored.sort(function (a, b) {
      var aDir = DIR_PREF[a.name] || 0;
      var bDir = DIR_PREF[b.name] || 0;
      if (bDir !== aDir) return bDir - aDir;
      if (b.space !== a.space) return b.space - a.space;
      if (b.nearest !== a.nearest) return b.nearest - a.nearest;
      return 0;
    });
    var pick = scored[0];
    if (!pick) {
      var fallbacks = [
        { name: "corner-tr", left: safe.right - cw, top: safe.top },
        { name: "corner-br", left: safe.right - cw, top: safe.bottom - ch }
      ];
      for (var f = 0; f < fallbacks.length; f++) {
        var fb = fallbacks[f];
        var fbox = {
          left: fb.left,
          top: fb.top,
          right: fb.left + cw,
          bottom: fb.top + ch
        };
        if (!insideSafe(fbox)) continue;
        if (areaOverlap(fbox, targetBox) > 0) continue;
        var fHit = false;
        for (var q = 0; q < protectedEls.length; q++) {
          if (areaOverlap(fbox, protectedEls[q].rect) > 0) {
            fHit = true;
            break;
          }
        }
        if (!fHit) {
          pick = fb;
          break;
        }
      }
      if (!pick) {
        var stepY = 8;
        var dockLeft = safe.right - cw;
        for (var y = safe.top; y <= safe.bottom - ch; y += stepY) {
          var scan = {
            left: dockLeft,
            top: y,
            right: dockLeft + cw,
            bottom: y + ch
          };
          if (!insideSafe(scan)) continue;
          if (areaOverlap(scan, targetBox) > 0) continue;
          var scanHit = false;
          for (var t = 0; t < protectedEls.length; t++) {
            if (areaOverlap(scan, protectedEls[t].rect) > 0) {
              scanHit = true;
              break;
            }
          }
          if (!scanHit) {
            pick = { name: "dock-right", left: dockLeft, top: y };
            break;
          }
        }
      }
    }
    if (!pick) return false;
    var left = clamp(pick.left, safe.left, Math.max(safe.left, safe.right - cw));
    var topPos = clamp(pick.top, safe.top, Math.max(safe.top, safe.bottom - ch));
    var placed = {
      left: left,
      top: topPos,
      right: left + cw,
      bottom: topPos + ch
    };
    if (!insideSafe(placed)) return false;
    applyHostPosition(host, left, topPos, pick.name);
    return true;
  }

  function reveal(target, key) {
    if (state.scrolled === key) return;
    state.scrolled = key;
    var rect = target.getBoundingClientRect();
    var vh = w.innerHeight || doc.documentElement.clientHeight;
    if (rect.top >= 0 && rect.bottom <= vh) return;
    var reduce = false;
    try {
      reduce =
        !!w.matchMedia &&
        w.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {}
    try {
      target.scrollIntoView({
        block: "center",
        inline: "nearest",
        behavior: reduce ? "auto" : "smooth"
      });
    } catch (e) {
      try {
        target.scrollIntoView(true);
      } catch (e2) {}
    }
  }

  function sync(force) {
    // A route change must blank the previous page's hint immediately, before
    // anything is measured against the new DOM.
    var path = currentPath();
    if (state.path !== path) {
      state.path = path;
      state.misses = 0;
      state.scrolled = "";
      removeSpotlight();
      hideAllHosts();
    }

    var cfg = readConfig();
    if (!cfg) {
      // Onboarding ended, was dismissed, or the host was remounted without a
      // config: nothing may stay on screen.
      teardown();
      return;
    }
    var host = cfg.host;
    var key = String(cfg.version || "") + ":" + String(cfg.id || cfg.step);
    if (state.lastStep !== key) {
      state.lastStep = key;
      state.misses = 0;
      state.scrolled = "";
      hideHost(host);
      doc.documentElement.removeAttribute("data-cel-coach-paused");
    }
    doc.documentElement.setAttribute(
      "data-cel-coach-step",
      String(cfg.id || cfg.step)
    );

    // Suppression is decided before any target lookup.
    if (routeSuppressed(cfg.routeSuppress) || suppressed(cfg.suppress)) {
      // Inside the real setup flow: unmount the hint, keep the step.
      removeSpotlight();
      hideAllHosts();
      root.setAttribute("data-cel-coach-suppressed", "1");
      return;
    }
    root.removeAttribute("data-cel-coach-suppressed");

    var target = findTarget(cfg.selectors);
    if (!target) {
      // Hidden on the very first miss. maxMisses only decides when to stop
      // retrying; it never keeps the card on screen.
      state.misses += 1;
      removeSpotlight();
      hideAllHosts();
      if (state.misses >= (cfg.maxMisses || 40)) pause();
      return;
    }

    if (force) reveal(target, key);

    var measured = contentBox(target);
    if (measured.width < MIN_SIZE || measured.height < MIN_SIZE) {
      state.misses += 1;
      removeSpotlight();
      hideAllHosts();
      return;
    }

    // Measure and position while still hidden. The first reveal waits one
    // animation frame so the card never paints at the off-screen default.
    // Later syncs update in place — hiding a ready card every beat flickers.
    var firstReveal = host.getAttribute("data-cel-coach-ready") !== "1";
    if (firstReveal) hideHost(host);
    var placed = place(host, measured, target);
    if (!placed) {
      hideHost(host);
      return;
    }
    var pad = typeof cfg.pad === "number" ? cfg.pad : 8;
    var token = key;
    state.revealToken = token;
    var paint = function () {
      if (!owned()) return;
      if (state.revealToken !== token) return;
      var liveCfg = readConfig();
      if (!liveCfg) {
        teardown();
        return;
      }
      var liveKey =
        String(liveCfg.version || "") + ":" + String(liveCfg.id || liveCfg.step);
      if (liveKey !== key) return;
      var liveHost = liveCfg.host;
      var live = findTarget(liveCfg.selectors);
      if (!live) {
        hideHost(liveHost);
        removeSpotlight();
        return;
      }
      var box = contentBox(live);
      if (box.width < MIN_SIZE || box.height < MIN_SIZE) {
        hideHost(liveHost);
        removeSpotlight();
        return;
      }
      if (!place(liveHost, box, live)) {
        hideHost(liveHost);
        return;
      }
      var livePad = typeof liveCfg.pad === "number" ? liveCfg.pad : pad;
      var spot = spotlight(true);
      spot.style.left = Math.round(box.left - livePad) + "px";
      spot.style.top = Math.round(box.top - livePad) + "px";
      spot.style.width = Math.round(box.width + livePad * 2) + "px";
      spot.style.height = Math.round(box.height + livePad * 2) + "px";
      spot.style.borderRadius =
        (typeof liveCfg.radius === "number" ? liveCfg.radius : 14) + "px";
      state.misses = 0;
      doc.documentElement.removeAttribute("data-cel-coach-paused");
      showHost(liveHost);
    };
    if (firstReveal) w.requestAnimationFrame(paint);
    else paint();
  }

  function schedule(force) {
    if (!owned()) return;
    beat();
    if (state.timer) w.cancelAnimationFrame(state.timer);
    state.timer = w.requestAnimationFrame(function () {
      state.timer = null;
      try {
        sync(force);
      } catch (e) {}
    });
  }

  w.__celCoachSync = function (force) {
    schedule(!!force);
  };

  try {
    w.addEventListener("popstate", function () {
      // Route change: blank first, re-measure on the next frame.
      try {
        removeSpotlight();
        hideAllHosts();
      } catch (e) {}
      schedule(false);
    });
    w.addEventListener("resize", function () {
      schedule(false);
    });
    w.addEventListener(
      "scroll",
      function () {
        schedule(false);
      },
      true
    );
  } catch (e) {}

  try {
    var observer = new w.MutationObserver(function () {
      schedule(false);
    });
    observer.observe(doc.body, {
      childList: true,
      subtree: true,
      attributes: true,
      // Never observe "style": this runtime writes inline styles itself.
      attributeFilter: [
        "class",
        "data-cel-coach-config",
        "data-cel-onboarding-target"
      ]
    });
  } catch (e) {}

  // Steady low-frequency re-measure covers layout shifts that mutation and
  // scroll events do not surface (fonts, charts, sidebar transitions).
  try {
    var beatTimer = w.setInterval(function () {
      if (!owned()) {
        w.clearInterval(beatTimer);
        return;
      }
      schedule(false);
    }, 400);
  } catch (e) {}

  schedule(true);
})();
