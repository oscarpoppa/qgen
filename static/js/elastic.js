/* Cards marked data-elastic (Home's awards: both ways; every Dashboard card and Home's other
 * cards, data-elastic-dir="v": only taller) stretch and float over what's around them instead of
 * pushing it (the owner, 2026-10-14):
 *  - each keeps its place in the grid (the room it had when the page was laid out); whatever
 *    it grows by afterwards (opened, new rows coming in, sized by hand) lies over the cards
 *    beside and below it, raised with a shadow. Folding it back lets the others move up.
 *  - a pull bar along its bottom makes it taller (its list shows more first, static/js/grip.js
 *    keeps that height; then the card itself grows); one that also gets wider has a pull bar on
 *    its growing side (toward the side with more room, up to the page's width) and a corner for
 *    both. The arrow keys work too; double-click (or Home) for its usual size. Remembered in
 *    this browser.
 * Not on a phone (one column): there the cards take the whole width and push as usual. */
(function () {
  var STEP = 40, NARROW = 760;
  function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function stored(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function narrow() { return window.innerWidth <= NARROW; }
  //the card last stretched or opened lies on top of the others, but always under the top bar,
  //the side panels and pop-overs (z-index 5 and 6; the top bar is 10)
  function raise(card) {
    document.querySelectorAll('[data-elastic]').forEach(function (c) { c.style.zIndex = ''; });
    card.style.zIndex = '6';
  }
  //Expand all / Collapse all (and a window resize): the cards are laid out afresh, each in its
  //natural place, pushing as usual, instead of all floating over one another; each then keeps
  //its new room (the owner, 2026-10-14)
  var fresh = 0;
  function relay() {
    fresh = Date.now() + 600;
    document.querySelectorAll('[data-elastic]').forEach(function (c) { if (c._elasticFloat) c._elasticFloat(); });
    if (window.qgenRelayout) window.qgenRelayout();
  }
  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('[data-level]')) relay();
  });

  function setUp(card) {
    if (card.dataset.elasticOn) return;
    card.dataset.elasticOn = '1';
    var tallOnly = card.dataset.elasticDir === 'v';  // (only taller: no wider)
    var key = 'qgen-elastic:' + location.pathname + ':' + card.dataset.elastic;
    //(Home's awards were pulled wider by their side edge before: that width still counts)
    var extra = parseFloat(stored(key)) || parseFloat(stored('qgen-stretch:' + location.pathname + ':' + card.dataset.elastic)) || 0;
    var rest = null;  // the room it has in the grid
    var tall = parseFloat(stored(key + ':h')) || 0;  // (a card with no list inside: its own extra height)
    //a card that only gets taller is as tall as what's in it: no extra height of its own, and its
    //pull bar only while its list holds more than shows (the owner, 2026-10-20: a card that can't
    //grow has no drag bar; one whose list runs past the window scrolls it)
    if (tallOnly) { tall = 0; store(key + ':h', null); }
    //its handles: a pull bar along the bottom (taller); a card that also gets wider has a pull
    //bar on its growing side and a corner for both at once (the owner, 2026-10-14)
    var handles = [];
    function handle(cls, axes, title, label) {
      var h = document.createElement('div');
      h.className = cls;
      h.dataset.axes = axes;
      h.tabIndex = 0;
      h.setAttribute('role', 'separator');
      if (axes !== 'xy') h.setAttribute('aria-orientation', axes === 'y' ? 'horizontal' : 'vertical');
      h.title = title + ' (double-click: its usual size)';
      h.setAttribute('aria-label', label + '; Home for its usual size');
      h.innerHTML = '<span aria-hidden="true"></span>';
      card.appendChild(h);
      handles.push(h);
      return h;
    }
    handle('elastic-bar', 'y', 'Drag down to make this card taller, over the cards below',
           'Make this card taller or shorter (drag, or the up and down arrow keys)');
    if (!tallOnly) {
      handle('elastic-side', 'x', 'Drag sideways to make this card wider, over the cards beside it', 'Make this card wider or narrower (drag, or the left and right arrow keys)');
      handle('elastic-corner', 'xy', 'Drag to make this card wider and taller, over the others', 'Make this card wider or taller (drag, or the arrow keys)');
    }

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
      if (narrow()) { card.style.width = ''; card.style.marginLeft = ''; handles.forEach(function (h) { h.hidden = true; }); float(); return; }
      handles.forEach(function (h) { h.hidden = false; });
      if (card._elasticBar) card._elasticBar();
      var g = room();
      extra = Math.max(0, Math.min(want, g.max));
      handles.forEach(function (h) { h.classList.toggle('on-left', g.toLeft); });
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
      //(hidden, e.g. folded into the Dashboard's strip of chips: it has no room of its own; shown
      //again, it's laid out afresh, never floating over the card that takes its place)
      if (!card.offsetParent || h < 1) { rest = null; card.classList.remove('is-floating'); return; }
      if (Date.now() < fresh) rest = null;  // (laid out afresh: see relay())
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
    function barShown() {
      if (!tallOnly) return;
      var a = area(), more = !!a && a.scrollHeight > a.clientHeight + 2;
      if (!card._elasticDragging) handles.forEach(function (h) { h.hidden = !more; });
    }
    card._baseH = card.getBoundingClientRect().height;
    widen(extra, false);
    if (tall) heighten(tall, false);
    //(a size kept from before is laid out as it opens, pushing the others like Expand all does,
    //so nothing is covered when the page opens; only what grows from here on floats)
    rest = null; card.style.marginBottom = ''; float();
    if (window.qgenRelayout) window.qgenRelayout();
    if (window.ResizeObserver) new ResizeObserver(function () { float(); barShown(); }).observe(card);
    card._elasticBar = barShown;
    barShown();
    card._elasticFloat = float;
    card.addEventListener('toggle', function () { if (card.open) raise(card); });
    function usual() {
      widen(0, true);
      heighten(0, true);
      card.querySelectorAll('[data-grip]').forEach(function (el) { if (el._gripReset) el._gripReset(); });
    }
    //drag a handle: sideways for the width, up and down for the height (its list shows more
    //first; once all of it shows, the card itself gets taller)
    handles.forEach(function (hd) {
      var sideways = hd.dataset.axes.indexOf('x') !== -1, upDown = hd.dataset.axes.indexOf('y') !== -1;
      hd.addEventListener('pointerdown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        raise(card);
        var x0 = e.clientX, y0 = e.clientY, w0 = extra, toLeft = hd.classList.contains('on-left');
        var a = area(), h0 = a ? a.getBoundingClientRect().height : 0;
        //(its height without the extra, measured now: its list may have grown since)
        var was = card.getBoundingClientRect().height;
        card.style.minHeight = '';
        card._baseH = card.getBoundingClientRect().height;
        var t0 = Math.max(0, was - card._baseH);
        heighten(t0, false);
        hd.setPointerCapture(e.pointerId);
        card._elasticDragging = true;
        document.documentElement.classList.add(!sideways ? 'elastic-sizing-v' : !upDown ? 'elastic-sizing-h' : 'elastic-sizing');
        function move(ev) {
          if (sideways) widen(w0 + (toLeft ? x0 - ev.clientX : ev.clientX - x0), false);
          if (upDown) {
            var dy = ev.clientY - y0, used = 0;
            if (a) { a._gripSet(h0 + dy, false); used = a.getBoundingClientRect().height - h0; }
            if (!tallOnly) heighten(t0 + Math.max(0, dy - Math.max(0, used)), false);
          }
        }
        function up() {
          hd.removeEventListener('pointermove', move);
          hd.removeEventListener('pointerup', up);
          hd.removeEventListener('pointercancel', up);
          document.documentElement.classList.remove('elastic-sizing', 'elastic-sizing-v', 'elastic-sizing-h');
          card._elasticDragging = false;
          widen(extra, true);
          if (a) a._gripSet(a.getBoundingClientRect().height, true);
          heighten(tall, true);
          barShown();
        }
        hd.addEventListener('pointermove', move);
        hd.addEventListener('pointerup', up);
        hd.addEventListener('pointercancel', up);
      });
      hd.addEventListener('dblclick', usual);
      hd.addEventListener('keydown', function (e) {
        raise(card);
        var grow = hd.classList.contains('on-left') ? 'ArrowLeft' : 'ArrowRight', a = area();
        if (sideways && e.key === grow) widen(extra + STEP, true);
        else if (sideways && e.key === (grow === 'ArrowLeft' ? 'ArrowRight' : 'ArrowLeft')) widen(extra - STEP, true);
        else if (upDown && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && a) a._gripSet(a.getBoundingClientRect().height + (e.key === 'ArrowDown' ? STEP : -STEP), true);
        else if (upDown && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && !tallOnly) heighten(tall + (e.key === 'ArrowDown' ? STEP : -STEP), true);
        else if (e.key === 'Home') usual();
        else return;
        e.preventDefault();
      });
    });
    //the window or a side panel changing the width: the grid is laid out afresh, then each card
    //keeps its new room again
    var timer;
    window.addEventListener('resize', function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        if (!card.isConnected) return;
        var want = parseFloat(stored(key)) || 0;
        rest = null; card.style.marginBottom = '';
        heighten(tall, false);  // (a phone: no extra height; back on a computer: as it was)
        widen(want, false);
      }, 150);
    });
  }

  //once the page has settled (the grid laid out, lists at their kept heights), and again for
  //cards a live update draws afresh (the Dashboard's)
  function scan() { document.querySelectorAll('[data-elastic]').forEach(setUp); }
  window.qgenElasticScan = scan;  // (the Dashboard's redraw: dashboard.js)
  //(straight away, before the Dashboard shows its cards, so a card kept taller is taller from the
  //start instead of growing a moment after: the owner, 2026-10-18)
  function start() { setTimeout(scan, 0); }
  if (document.readyState !== 'loading') start(); else document.addEventListener('DOMContentLoaded', start);
  if (window.MutationObserver) new MutationObserver(function () { clearTimeout(scan._t); scan._t = setTimeout(scan, 250); })
    .observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
})();
