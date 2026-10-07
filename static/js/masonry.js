/* Boxes in a grid (Home, the Dashboard, the quiz cards on My quizzes, a problem's examples)
 * take only the height they need, and the ones below move up into the space, instead of
 * every row being as tall as its tallest box and leaving holes under the short ones.
 *
 * Each box spans as many thin grid rows as its height needs (the grid keeps its columns and
 * left-to-right order, and a box spanning every column still does). Done again whenever a
 * box changes size: opening or folding it, live updates, a search hiding cards, a side panel
 * or the window changing the width. Without this script the grid is laid out as before. */
(function () {
  var GRIDS = '.dash-grid, .grid', UNIT = 4;
  var pending = [];

  function lay(grid) {
    var cs = getComputedStyle(grid);
    if (cs.display !== 'grid') return;
    var gap = parseFloat(cs.rowGap) || 0;
    if (!grid.classList.contains('masonry-on')) {
      grid.dataset.gap = gap;
      grid.classList.add('masonry-on');  // thin rows, no row gap (each box adds its own)
    }
    gap = parseFloat(grid.dataset.gap) || 0;
    Array.prototype.forEach.call(grid.children, function (box) {
      if (box.hidden || getComputedStyle(box).display === 'none') return;
      var m = getComputedStyle(box), h = box.getBoundingClientRect().height + parseFloat(m.marginTop) + parseFloat(m.marginBottom);
      box.style.gridRowEnd = 'span ' + Math.max(1, Math.ceil((h + gap) / UNIT));
    });
  }
  function soon(grid) {
    if (pending.indexOf(grid) === -1) pending.push(grid);
    //a timer, not requestAnimationFrame: that waits while the tab isn't on screen
    if (pending.length === 1) setTimeout(function () {
      var grids = pending; pending = [];
      grids.forEach(function (g) { if (g.isConnected) lay(g); });
    }, 16);
  }

  var seen = window.WeakSet ? new WeakSet() : null;
  var watch = window.ResizeObserver ? new ResizeObserver(function (entries) {
    entries.forEach(function (e) { if (e.target.parentElement) soon(e.target.parentElement); });
  }) : null;
  function scan() {
    document.querySelectorAll(GRIDS).forEach(function (grid) {
      Array.prototype.forEach.call(grid.children, function (box) {
        if (seen && seen.has(box)) return;
        if (seen) seen.add(box);
        if (watch) watch.observe(box);
      });
      soon(grid);
    });
  }
  //pages that redraw parts of themselves (the Dashboard's live boxes)
  if (window.MutationObserver) new MutationObserver(function () { clearTimeout(scan._t); scan._t = setTimeout(scan, 50); })
    .observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
  //and straight away for a box opening or folding, or a search hiding cards
  function all() { document.querySelectorAll(GRIDS).forEach(soon); }
  document.addEventListener('toggle', all, true);
  document.addEventListener('qgen-filtered', all);
  window.addEventListener('resize', all);
  scan();
})();
