/* Cards marked data-elastic (Home's awards: both ways; every Dashboard card and Home's other
 * cards, data-elastic-dir="v": only taller) stretch and float over what's around them instead of
 * pushing it (the owner, 2026-10-14):
 *  - each keeps its place in the grid (the room it had when the page was laid out); whatever
 *    it grows by afterwards (opened, new rows coming in, sized by hand) lies over the cards
 *    beside and below it, raised with a shadow. Folding it back lets the others move up.
 *  - its corner handle: drag to make it wider (toward the side with more room, up to the page's
 *    width) and taller (its list shows more; static/js/grip.js keeps that height); the arrow
 *    keys work too, double-click (or Home) for its usual size. Remembered in this browser.
 * Not on a phone (one column): there the cards take the whole width and push as usual. */
(function () {
  var STEP = 40, NARROW = 760;
  function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function stored(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function narrow() { return window.innerWidth <= NARROW; }
  //the card last stretched or opened lies on top of the others
  var top = 20;
  function raise(card) { card.style.zIndex = String(++top); }

  function setUp(card) {
    if (card.dataset.elasticOn) return;
    card.dataset.elasticOn = '1';
    var tallOnly = card.dataset.elasticDir === 'v';  // (only taller: no wider)
    var key = 'qgen-elastic:' + location.pathname + ':' + card.dataset.elastic;
    //(Home's awards were pulled wider by their side edge before: that width still counts)
    var extra = parseFloat(stored(key)) || parseFloat(stored('qgen-stretch:' + location.pathname + ':' + card.dataset.elastic)) || 0;
    var rest = null;  // the room it has in the grid
    var tall = parseFloat(stored(key + ':h')) || 0;  // (a card with no list inside: its own extra height)
    var corner = document.createElement('div');
    corner.className = 'elastic-corner';
    corner.tabIndex = 0;
    corner.setAttribute('role', 'separator');
    var tallOnlyAttr = card.dataset.elasticDir === 'v';
    corner.title = tallOnlyAttr ? 'Drag down to make this card taller, over the cards below (double-click: its usual size)' : 'Drag to make this card wider or taller, over the others (double-click: its usual size)';
    corner.setAttribute('aria-label', tallOnlyAttr ? 'Make this card taller or shorter (drag, or use the up and down arrow keys; Home for its usual size)' : 'Make this card wider or taller (drag, or use the arrow keys; Home for its usual size)');
    if (tallOnlyAttr) corner.classList.add('tall-only');
    corner.innerHTML = '<span aria-hidden="true"></span>';
    card.appendChild(corner);

    //the list inside that shows more when the card is taller (the first one with more in it)
    function area() {
      var all = Array.prototype.filter.call(card.querySelectorAll('[data-grip]'), function (el) { return el.offsetParent !== null && el._gripSet; });
      return all.filter(function (el) { return el.scrollHeight > el.clientHeight + 2; })[0] || all[all.length - 1] || null;
    }

    //how wide it can be: toward the side with more room
    function room() {
      card.style.width = ''; card.style.marginLeft = '';
      var main = card.closest('main') || document.body, page = main.getBoundingClientRect(), r = card.getBoundingClientRect();
      var cs = getComputedStyle(main);
      var left = r.left - page.left - parseFloat(cs.paddingLeft), right = page.right - parseFloat(cs.paddingRight) - r.right;
      return { base: r.width, max: Math.max(0, Math.max(left, right)), toLeft: left > right };
    }
    function widen(want, keep) {
      if (tallOnly) want = 0;
      if (narrow()) { card.style.width = ''; card.style.marginLeft = ''; corner.hidden = true; float(); return; }
      corner.hidden = false;
      var g = room();
      extra = Math.max(0, Math.min(want, g.max));
      corner.classList.toggle('on-left', g.toLeft);
      if (extra) {
        card.style.width = (g.base + extra) + 'px';
        if (g.toLeft) card.style.marginLeft = (-extra) + 'px';
      }
      if (keep) store(key, extra ? String(Math.round(extra)) : null);
      float();
    }

    //it keeps the room it has; anything more lies over the others (a negative bottom margin, so
    //the grid, static/js/masonry.js, still sees the old height)
    function float() {
      if (narrow()) { card.style.marginBottom = ''; card.classList.remove('is-floating'); rest = null; return; }
      card.style.marginBottom = '';
      var h = card.getBoundingClientRect().height;
      if (rest === null || h < rest) rest = h;  // (smaller: the others move up into the room)
      var over = h - rest;
      if (over > 1) card.style.marginBottom = (-over) + 'px';
      card.classList.toggle('is-floating', over > 1 || extra > 0);
    }

    function heighten(h, keep) {
      tall = Math.max(0, h);
      card.style.minHeight = tall && !narrow() ? (card._baseH + tall) + 'px' : '';
      if (keep) store(key + ':h', tall ? String(Math.round(tall)) : null);
      float();
    }
    card._baseH = card.getBoundingClientRect().height;
    widen(extra, false);
    if (tall) heighten(tall, false);
    if (window.ResizeObserver) new ResizeObserver(function () { float(); }).observe(card);
    card.addEventListener('toggle', function () { if (card.open) raise(card); });
    corner.addEventListener('keydown', function () { raise(card); });

    //drag the corner: sideways for the width, up and down for the height of its list
    corner.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      raise(card);
      var x0 = e.clientX, y0 = e.clientY, w0 = extra, toLeft = corner.classList.contains('on-left');
      var a = area(), h0 = a ? a.getBoundingClientRect().height : 0, t0 = tall;
      if (!tall) card._baseH = card.getBoundingClientRect().height;
      corner.setPointerCapture(e.pointerId);
      document.documentElement.classList.add(tallOnly ? 'elastic-sizing-v' : 'elastic-sizing');
      function move(ev) {
        widen(w0 + (toLeft ? x0 - ev.clientX : ev.clientX - x0), false);
        //(its list shows more first; once all of it shows, the card itself gets taller)
        var dy = ev.clientY - y0, used = 0;
        if (a) { a._gripSet(h0 + dy, false); used = a.getBoundingClientRect().height - h0; }
        heighten(t0 + Math.max(0, dy - Math.max(0, used)), false);
      }
      function up() {
        corner.removeEventListener('pointermove', move);
        corner.removeEventListener('pointerup', up);
        corner.removeEventListener('pointercancel', up);
        document.documentElement.classList.remove('elastic-sizing', 'elastic-sizing-v');
        widen(extra, true);
        if (a) a._gripSet(a.getBoundingClientRect().height, true);
        heighten(tall, true);
      }
      corner.addEventListener('pointermove', move);
      corner.addEventListener('pointerup', up);
      corner.addEventListener('pointercancel', up);
    });
    function usual() {
      widen(0, true);
      heighten(0, true);
      card.querySelectorAll('[data-grip]').forEach(function (el) { if (el._gripReset) el._gripReset(); });
    }
    corner.addEventListener('dblclick', usual);
    corner.addEventListener('keydown', function (e) {
      var grow = corner.classList.contains('on-left') ? 'ArrowLeft' : 'ArrowRight', a = area();
      if (e.key === grow) widen(extra + STEP, true);
      else if (e.key === (grow === 'ArrowLeft' ? 'ArrowRight' : 'ArrowLeft')) widen(extra - STEP, true);
      else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && a) a._gripSet(a.getBoundingClientRect().height + (e.key === 'ArrowDown' ? STEP : -STEP), true);
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') heighten(tall + (e.key === 'ArrowDown' ? STEP : -STEP), true);
      else if (e.key === 'Home') usual();
      else return;
      e.preventDefault();
    });
    //the window or a side panel changing the width: the grid is laid out afresh, then each card
    //keeps its new room again
    var timer;
    window.addEventListener('resize', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { if (!card.isConnected) return; var want = parseFloat(stored(key)) || 0; rest = null; card.style.marginBottom = ''; widen(want, false); }, 150);
    });
  }

  //once the page has settled (the grid laid out, lists at their kept heights), and again for
  //cards a live update draws afresh (the Dashboard's)
  function scan() { document.querySelectorAll('[data-elastic]').forEach(setUp); }
  function start() { setTimeout(scan, 250); }
  if (document.readyState === 'complete') start(); else window.addEventListener('load', start);
  if (window.MutationObserver) new MutationObserver(function () { clearTimeout(scan._t); scan._t = setTimeout(scan, 250); })
    .observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
})();
