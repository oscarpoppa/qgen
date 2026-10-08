/* Sideways dividers: drag one (or use the left and right arrow keys on it) to make what's
 * beside it wider or narrower; double-click puts it back. The width is remembered in this
 * browser. Two of them:
 *  - folder pages: between the folder list and the list (one width for every folder page)
 *  - the Notices / Messages panel: its left edge */
(function () {
  var STEP = 16;
  function stored(k) { try { return parseInt(localStorage.getItem(k), 10) || 0; } catch (e) { return 0; } }
  function store(k, v) { try { if (v) localStorage.setItem(k, String(v)); else localStorage.removeItem(k); } catch (e) {} }

  //bar: the divider; width(): the width now; set(px): apply one; min/max(): the limits;
  //grows: +1 if dragging right makes it wider (the folder list), -1 if left does (the panel)
  function divider(bar, key, width, set, min, max, grows, label) {
    bar.setAttribute('role', 'separator');
    bar.setAttribute('aria-orientation', 'vertical');
    bar.setAttribute('aria-label', label + ' (drag, or use the left and right arrow keys)');
    bar.title = 'Drag to make this wider or narrower; double-click to put it back';
    bar.tabIndex = 0;
    function fit(px, keep) {
      px = Math.round(Math.max(min(), Math.min(max(), px)));
      set(px);
      if (keep) store(key, px);
    }
    var saved = stored(key);
    if (saved) fit(saved, false);
    bar.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      var startX = e.clientX, startW = width();
      bar.setPointerCapture(e.pointerId);
      bar.classList.add('dragging');
      document.documentElement.classList.add('col-resizing');
      function move(ev) { fit(startW + grows * (ev.clientX - startX), false); }
      function up() {
        bar.removeEventListener('pointermove', move);
        bar.removeEventListener('pointerup', up);
        bar.removeEventListener('pointercancel', up);
        bar.classList.remove('dragging');
        document.documentElement.classList.remove('col-resizing');
        fit(width(), true);
      }
      bar.addEventListener('pointermove', move);
      bar.addEventListener('pointerup', up);
      bar.addEventListener('pointercancel', up);
    });
    bar.addEventListener('keydown', function (e) {
      var d = e.key === 'ArrowRight' ? STEP : e.key === 'ArrowLeft' ? -STEP : 0;
      if (!d) return;
      e.preventDefault();
      fit(width() + grows * d, true);
    });
    bar.addEventListener('dblclick', function () { set(null); store(key, null); });
  }

  //1. folder pages
  var layout = document.querySelector('.folders-layout'), side = layout && layout.querySelector(':scope > .folder-side');
  if (side) {
    var bar = document.createElement('div');
    bar.className = 'vsplit folder-split';
    side.insertAdjacentElement('afterend', bar);
    divider(bar, 'qgen-side-width', function () { return side.getBoundingClientRect().width; },
      function (px) { if (px) layout.style.setProperty('--side-w', px + 'px'); else layout.style.removeProperty('--side-w'); },
      function () { return 160; }, function () { return Math.min(480, layout.getBoundingClientRect().width * 0.45); },
      1, 'Make the folder list wider or narrower');
  }

  //4. the Notices / Messages panel
  var dock = document.getElementById('dock'), root = document.documentElement;
  if (dock) {
    var edge = document.createElement('div');
    edge.className = 'vsplit dock-edge';
    dock.insertBefore(edge, dock.firstChild);
    divider(edge, 'qgen-dock-width', function () { return dock.getBoundingClientRect().width; },
      function (px) { if (px) root.style.setProperty('--dock-w', px + 'px'); else root.style.removeProperty('--dock-w'); },
      function () { return 280; }, function () { return Math.min(760, window.innerWidth * 0.6); },
      -1, 'Make the Notices and Messages panel wider or narrower');
  }
})();
