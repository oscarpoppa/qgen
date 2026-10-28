/* Boxes in a grid (Home, the Dashboard, the quiz cards on My quizzes, a problem's examples)
 * take only the height they need, and the ones below move up into the space, instead of
 * every row being as tall as its tallest box and leaving holes under the short ones.
 *
 * Each box spans as many thin grid rows as its height needs and stays in its own column (the
 * boxes take the columns in turn, left to right; a box spanning every column still does). Done again whenever a
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
    //each box keeps its own column (in order: left, middle, right, left…) and only moves up or
    //down as the ones above it grow or shrink, never across to another column (the owner,
    //2026-10-26: the tiles jumped from side to side); a box as wide as the grid starts below them all
    var cols = cs.gridTemplateColumns.split(' ').filter(Boolean).length || 1;
    var tops = [], i = 0, c;
    for (c = 0; c < cols; c++) tops.push(1);
    function spanOf(box) {
      var m = getComputedStyle(box), h = box.getBoundingClientRect().height + parseFloat(m.marginTop) + parseFloat(m.marginBottom);
      return Math.max(1, Math.ceil((h + gap) / UNIT));
    }
    //cards that can be dragged to another column (Home, the Dashboard: the owner, 2026-10-26):
    //each goes where it was put (remembered in this browser), the rest take the columns in turn
    if (grid.dataset.movable && cols > 1) {
      var saved = placesOf(grid), lists = [], n = 0;
      for (c = 0; c < cols; c++) lists.push([]);
      var follow = [];
      Array.prototype.forEach.call(grid.children, function (box, k) {
        if (box.hidden || getComputedStyle(box).display === 'none') return;
        var at = saved[box.dataset.box];
        if (at) lists[Math.min(at[0], cols - 1)].push({ box: box, seq: at[1], k: k });
        //(a card not moved yet that's meant to come right after another, data-follows: under it, in its column; the
        //Dashboard's Student notes under Site at a glance, the owner 2026-10-28)
        else if (box.dataset.follows) { follow.push({ box: box, k: k }); return; }
        else { lists[n % cols].push({ box: box, seq: n, k: k }); }
        n++;
      });
      follow.forEach(function (f) {
        for (c = 0; c < cols; c++) {
          var lead = lists[c].filter(function (it) { return it.box.dataset.box === f.box.dataset.follows; })[0];
          if (lead) { lists[c].push({ box: f.box, seq: lead.seq + 0.01, k: f.k }); return; }  // (a little after it, so a card following that one comes next)
        }
        lists[n++ % cols].push({ box: f.box, seq: n, k: f.k });
      });
      lists.forEach(function (list, c) {
        list.sort(function (a, b) { return a.seq - b.seq || a.k - b.k; });
        list.forEach(function (it, s) {
          var span = spanOf(it.box);
          it.box.style.gridColumn = (c + 1) + ' / span 1';
          it.box.style.gridRow = tops[c] + ' / span ' + span;
          it.box._place = [c, s];
          //(a note on the heading: the owner, 2026-10-26)
          var head = it.box.querySelector('summary');
          if (head && !head.title) head.title = 'Drag to move this card';
          tops[c] += span;
        });
      });
    } else Array.prototype.forEach.call(grid.children, function (box) {
      if (box.hidden || getComputedStyle(box).display === 'none') return;
      var span = spanOf(box);
      if (box.classList.contains('dash-wide') || cols === 1) {
        var top = Math.max.apply(null, tops);
        box.style.gridColumn = cols === 1 ? '' : '1 / -1';
        box.style.gridRow = top + ' / span ' + span;
        for (c = 0; c < cols; c++) tops[c] = top + span;
        i = 0;
      } else {
        c = i++ % cols;
        box.style.gridColumn = (c + 1) + ' / span 1';
        box.style.gridRow = tops[c] + ' / span ' + span;
        tops[c] += span;
      }
    });
    //laid out: a page that hid its boxes until now (the Dashboard) shows them, in place
    var settling = grid.closest('.dash-settling');
    if (settling) setTimeout(function () { settling.classList.remove('dash-settling'); }, 30);
  }
  function placesOf(grid) {
    try { return JSON.parse(localStorage.getItem('qgen-cards:' + grid.dataset.movable)) || {}; } catch (e) { return {}; }
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
  window.qgenRelayout = all;
  window.qgenLayNow = lay;  // (at once, not on the next timer: the Dashboard after redrawing its boxes, dashboard.js)  // (a box's room changed without its size changing: elastic.js)
  document.addEventListener('toggle', all, true);
  document.addEventListener('qgen-filtered', all);
  window.addEventListener('resize', all);
  scan();

  //dragging a card by its heading to another column, or higher or lower in one (mouse or pen;
  //on a phone there's one column); a line shows where it will go
  var drag = null;
  function columnsOf(grid) {
    var cs = getComputedStyle(grid), r = grid.getBoundingClientRect(), x = r.left + parseFloat(cs.paddingLeft);
    var gapX = parseFloat(cs.columnGap) || 0;
    return cs.gridTemplateColumns.split(' ').filter(Boolean).map(function (w) {
      var col = { left: x, width: parseFloat(w) }; x += col.width + gapX; return col;
    });
  }
  function target(e) {
    var grid = drag.grid, cols = columnsOf(grid), c = 0, d = Infinity;
    cols.forEach(function (col, k) { var m = Math.abs(e.clientX - (col.left + col.width / 2)); if (m < d) { d = m; c = k; } });
    var here = Array.prototype.filter.call(grid.children, function (b) {
      return b !== drag.box && b._place && b._place[0] === c && !b.hidden && b.offsetParent;
    }).sort(function (a, b) { return a._place[1] - b._place[1]; });
    var at = here.filter(function (b) { var r = b.getBoundingClientRect(); return r.top + r.height / 2 < e.clientY; }).length;
    var gr = grid.getBoundingClientRect(), y;
    if (!here.length) y = gr.top;
    else if (at === 0) y = here[0].getBoundingClientRect().top - 6;
    else y = here[at - 1].getBoundingClientRect().bottom + 6;
    return { col: c, at: at, here: here, left: cols[c].left - gr.left, width: cols[c].width, top: y - gr.top };
  }
  document.addEventListener('pointerdown', function (e) {
    if (e.button !== 0 || e.pointerType === 'touch') return;
    var head = e.target.closest && e.target.closest('summary');
    if (!head || e.target.closest('a, button, input, select, label')) return;
    var box = head.parentElement, grid = box && box.parentElement;
    if (!grid || !grid.dataset || !grid.dataset.movable || !box._place) return;
    if (getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length < 2) return;
    //(no text selected while dragging: app.css, user-select on the heading; not preventDefault here, which kept a
    //clicked heading from taking focus, so Space/Enter didn't fold it: the code critic, 2026-10-26)
    drag = { box: box, grid: grid, x: e.clientX, y: e.clientY, on: false };
  });
  document.addEventListener('pointermove', function (e) {
    if (!drag) return;
    if (!drag.on) {
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) < 8) return;
      drag.on = true;
      drag.box.classList.add('card-dragging');
      document.body.classList.add('cards-dragging');
      drag.line = document.createElement('div');
      drag.line.className = 'card-drop-line';
      drag.grid.appendChild(drag.line);
    }
    e.preventDefault();
    drag.box.style.transform = 'translate(' + (e.clientX - drag.x) + 'px,' + (e.clientY - drag.y) + 'px)';
    var t = drag.t = target(e);
    drag.line.style.left = t.left + 'px'; drag.line.style.width = t.width + 'px'; drag.line.style.top = t.top + 'px';
  });
  function end(e, keep) {
    if (!drag) return;
    var d = drag; drag = null;
    if (!d.on) return;
    d.box.classList.remove('card-dragging');
    document.body.classList.remove('cards-dragging');
    d.box.style.transform = '';
    d.line.remove();
    //(the heading's click after a drag doesn't open or fold the card)
    var head = d.box.querySelector('summary');
    function stop(ev) { ev.preventDefault(); ev.stopPropagation(); }
    head.addEventListener('click', stop, true);
    setTimeout(function () { head.removeEventListener('click', stop, true); }, 0);
    if (!keep || !d.t) return;
    //every shown card's place is written down, so the layout stays as it is now
    var saved = placesOf(d.grid), cols = {};
    Array.prototype.forEach.call(d.grid.children, function (b) {
      if (b === d.box || !b._place || b.hidden || !b.offsetParent) return;
      (cols[b._place[0]] = cols[b._place[0]] || []).push(b);
    });
    Object.keys(cols).forEach(function (c) {
      var list = cols[c].sort(function (a, b) { return a._place[1] - b._place[1]; });
      if (+c === d.t.col) list.splice(d.t.at, 0, d.box);
      list.forEach(function (b, s) { saved[b.dataset.box] = [+c, s]; });
    });
    if (!cols[d.t.col]) saved[d.box.dataset.box] = [d.t.col, 0];
    try { localStorage.setItem('qgen-cards:' + d.grid.dataset.movable, JSON.stringify(saved)); } catch (err) {}
    soon(d.grid);
  }
  document.addEventListener('pointerup', function (e) { end(e, true); });
  document.addEventListener('pointercancel', function (e) { end(e, false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') end(e, false); });
})();
