/* Areas that scroll inside themselves (a folder page's list, the boxes that open in it, the
 * Dashboard's lists...) get a wide bar underneath to drag them taller or shorter (or the up
 * and down arrow keys on it). The height is remembered in this browser, for that area on that
 * page. Every such area has its bar (on a phone the page scrolls instead, and there's none). */
(function () {
  var AREAS = [
    '.folder-main > #folder-items', '.folder-main > .list-scroll',
    '#folder-items > details.sub-box > .sub-body', 'details.item-box > .box-body',
    'details.result-folder > .result-folder-body', 'details.month-box > .table-wrap',
    'details.done-box > .quiz-grid', '.dash-card .dash-list', 'details.grading-group > .table-wrap',
    '.pick-list', 'details.subject-box > .box-body', '.order-list', 'ol.attempt-list'
  ];
  var MIN = 96, STEP = 48;
  function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function stored(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  //which area on this page: its kind and the box it's in, so the same one gets its height back
  function keyOf(el, kind) {
    var home = el.closest('[data-box],[data-sub],[data-folder-box],[data-quiz],[id]');
    var who = home ? (home.dataset.box || home.dataset.sub || home.dataset.folderBox || home.dataset.quiz || home.id) : '';
    return 'qgen-grip:' + location.pathname + ':' + kind + ':' + who;
  }
  //it scrolls inside itself here (not on a phone, where the page scrolls instead)
  function scrolls(el) { return getComputedStyle(el).overflowY === 'auto'; }

  function attach(el, kind) {
    if (el.dataset.grip) return;
    el.dataset.grip = '1';
    var key = keyOf(el, kind), bar = document.createElement('div');
    bar.className = 'grip-bar';
    bar.setAttribute('role', 'separator');
    bar.setAttribute('aria-orientation', 'horizontal');
    bar.tabIndex = 0;
    bar.title = 'Drag to make this taller or shorter';
    bar.setAttribute('aria-label', 'Make this area taller or shorter (drag, or use the up and down arrow keys)');
    bar.innerHTML = '<span aria-hidden="true"></span>';
    el.insertAdjacentElement('afterend', bar);

    function set(h, keep) {
      h = Math.max(MIN, Math.min(Math.round(h), el.scrollHeight + 2));
      el.style.maxHeight = h + 'px';
      if (keep) store(key, String(h));
      show();
    }
    //the bar: on every area that scrolls inside itself (and is on show)
    function show() {
      if (!scrolls(el)) el.style.maxHeight = '';  // a phone: no height of its own
      bar.hidden = !(scrolls(el) && el.offsetParent !== null);
    }
    var saved = parseInt(stored(key), 10);
    if (saved && scrolls(el)) el.style.maxHeight = Math.max(MIN, saved) + 'px';

    bar.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      var startY = e.clientY, startH = el.getBoundingClientRect().height;
      bar.setPointerCapture(e.pointerId);
      document.documentElement.classList.add('grip-resizing');
      function move(ev) { set(startH + ev.clientY - startY, false); }
      function up() {
        bar.removeEventListener('pointermove', move);
        bar.removeEventListener('pointerup', up);
        bar.removeEventListener('pointercancel', up);
        document.documentElement.classList.remove('grip-resizing');
        set(el.getBoundingClientRect().height, true);
      }
      bar.addEventListener('pointermove', move);
      bar.addEventListener('pointerup', up);
      bar.addEventListener('pointercancel', up);
    });
    bar.addEventListener('keydown', function (e) {
      var step = e.key === 'ArrowDown' ? STEP : e.key === 'ArrowUp' ? -STEP : 0;
      if (!step) return;
      e.preventDefault();
      set(el.getBoundingClientRect().height + step, true);
    });
    //double-click: back to the usual height
    bar.addEventListener('dblclick', function () { el.style.maxHeight = ''; store(key, null); show(); });
    el._gripShow = show;
    show();
  }

  function scan() {
    AREAS.forEach(function (sel) { document.querySelectorAll(sel).forEach(function (el) { attach(el, sel); }); });
    document.querySelectorAll('[data-grip]').forEach(function (el) { if (el._gripShow) el._gripShow(); });
  }
  //boxes opening and closing, searches, the window's size and pages that redraw parts of themselves
  document.addEventListener('toggle', function () { setTimeout(scan, 0); }, true);
  document.addEventListener('qgen-filtered', function () { setTimeout(scan, 0); });
  window.addEventListener('resize', function () { clearTimeout(scan._t); scan._t = setTimeout(scan, 150); });
  if (window.MutationObserver) new MutationObserver(function () { clearTimeout(scan._m); scan._m = setTimeout(scan, 100); })
    .observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
  scan();
})();
