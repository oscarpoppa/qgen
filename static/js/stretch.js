/* A box marked data-stretch (Home's awards) can be pulled wider by its side edge, over
 * whatever is beside it, up to the width of the page. It grows toward the side with more
 * room. Double-click the edge (or press Home on it) for the normal width; the arrow keys
 * work too. The width is remembered in this browser. Not on a phone, where the boxes
 * already take the whole width. */
(function () {
  var STEP = 40;
  function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function stored(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  document.querySelectorAll('[data-stretch]').forEach(function (box) {
    var key = 'qgen-stretch:' + location.pathname + ':' + box.dataset.stretch;
    var edge = document.createElement('div');
    edge.className = 'stretch-edge';
    edge.tabIndex = 0;
    edge.setAttribute('role', 'separator');
    edge.setAttribute('aria-orientation', 'vertical');
    edge.title = 'Drag sideways to make this wider (double-click: back to normal)';
    edge.setAttribute('aria-label', 'Make this box wider or narrower (drag, or use the left and right arrow keys)');
    edge.innerHTML = '<span aria-hidden="true"></span>';
    box.appendChild(edge);
    var extra = parseFloat(stored(key)) || 0;

    //its normal width, and how far it can grow (toward the side with more room)
    function room() {
      box.style.width = '';
      box.style.marginLeft = '';
      var main = box.closest('main') || document.body, page = main.getBoundingClientRect(), r = box.getBoundingClientRect();
      var cs = getComputedStyle(main);  // up to the page's content edge, not into its padding
      var left = r.left - page.left - parseFloat(cs.paddingLeft), right = page.right - parseFloat(cs.paddingRight) - r.right;
      return { base: r.width, max: Math.max(left, right), toLeft: left > right };
    }
    function apply(want, keep) {
      var g = room();
      var off = g.max < 24;  // nowhere to grow (a phone)
      edge.hidden = off;
      extra = off ? 0 : Math.max(0, Math.min(want, g.max));
      edge.classList.toggle('on-left', g.toLeft);
      if (extra) {
        box.style.width = (g.base + extra) + 'px';
        if (g.toLeft) box.style.marginLeft = (-extra) + 'px';
      }
      box.classList.toggle('is-stretched', extra > 0);
      edge.setAttribute('aria-valuenow', Math.round(extra));
      if (keep) store(key, extra ? String(Math.round(extra)) : null);
      return g;
    }
    apply(extra, false);

    edge.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      var start = extra, x0 = e.clientX, toLeft = edge.classList.contains('on-left');
      edge.setPointerCapture(e.pointerId);
      document.documentElement.classList.add('stretching');
      function move(ev) { apply(start + (toLeft ? x0 - ev.clientX : ev.clientX - x0), false); }
      function up() {
        edge.removeEventListener('pointermove', move);
        edge.removeEventListener('pointerup', up);
        edge.removeEventListener('pointercancel', up);
        document.documentElement.classList.remove('stretching');
        apply(extra, true);
      }
      edge.addEventListener('pointermove', move);
      edge.addEventListener('pointerup', up);
      edge.addEventListener('pointercancel', up);
    });
    edge.addEventListener('dblclick', function () { apply(0, true); });
    edge.addEventListener('keydown', function (e) {
      var grow = edge.classList.contains('on-left') ? 'ArrowLeft' : 'ArrowRight';
      var shrink = grow === 'ArrowLeft' ? 'ArrowRight' : 'ArrowLeft';
      if (e.key === grow) apply(extra + STEP, true);
      else if (e.key === shrink) apply(extra - STEP, true);
      else if (e.key === 'Home') apply(0, true);
      else return;
      e.preventDefault();
    });
    //the window or a side panel changing the width: as wide as it was, if it still fits
    var want = extra, timer;
    edge.addEventListener('pointerup', function () { want = extra; });
    edge.addEventListener('keyup', function () { want = extra; });
    edge.addEventListener('dblclick', function () { want = 0; });
    window.addEventListener('resize', function () { clearTimeout(timer); timer = setTimeout(function () { apply(want, false); }, 100); });
  });
})();
