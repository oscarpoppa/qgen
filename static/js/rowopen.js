/* A list's columns that only an open row fills (td.row-more) show once a row is open: the table is
 * marked .has-open-row here, and app.css hides them otherwise. (Asked in the stylesheet itself,
 * "a table with no open row", Firefox checked every row on every change: 1.3 s of Problems'
 * 2.4 s; the owner, 2026-10-21.) */
(function () {
  function mark(table) {
    if (!table) return;
    var open = !!table.querySelector('details.row-fold[open]');
    //(a sort keeps the columns' widths, measured while these columns were hidden, so they'd open 0 wide
    //and spill over the next column: the widths go back to the table's own once a row opens; the
    //owner's broken Trash row, 2026-10-25)
    if (open && table.dataset.fixedCols && table.querySelector(':scope > thead > tr > th.row-more')) {
      table.querySelectorAll(':scope > thead > tr > th').forEach(function (th) { th.style.width = ''; });
      table.style.tableLayout = '';
      delete table.dataset.fixedCols;
    }
    table.classList.toggle('has-open-row', open);
  }
  //an open row's contents (its facts, chips…) use the room to its right, across the cells whose own
  //contents end above them, the buttons' cell too (the owner, 2026-10-26: "use up the rest of that
  //horizontal space"); the title's column keeps its width (a negative margin as wide as the extra)
  function bottomOf(td) {
    var r = document.createRange(); r.selectNodeContents(td);
    var b = r.getBoundingClientRect();
    return b.height ? b.bottom : -Infinity;
  }
  function widen(d) {
    var td = d.closest('td');
    if (!td) return;
    if (!d.open) { d.style.removeProperty('--row-extra'); d.classList.remove('row-wide'); return; }
    var head = d.querySelector(':scope > summary'), top = head.getBoundingClientRect().bottom + 2;
    var own = td.getBoundingClientRect(), right = own.right, sib = td.nextElementSibling;
    for (; sib; sib = sib.nextElementSibling) {
      var r = sib.getBoundingClientRect();
      if (!r.width || r.left < own.right - 1 || bottomOf(sib) > top) break;
      right = r.right - parseFloat(getComputedStyle(sib).paddingRight);
    }
    var extra = Math.max(0, Math.floor(right - own.right + parseFloat(getComputedStyle(td).paddingRight)));
    d.style.setProperty('--row-extra', extra + 'px');
    d.classList.toggle('row-wide', extra > 0);
  }
  function widenAll(table) {
    //(the old widths off first, so a narrower window is measured afresh)
    var rows = (table || document).querySelectorAll('details.row-fold');
    rows.forEach(function (d) { d.classList.remove('row-wide'); });
    rows.forEach(widen);
  }
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (d && d.matches && d.matches('details.row-fold')) {
      var t = d.closest('table');
      mark(t);
      setTimeout(function () { widenAll(t); }, 0);
    }
  }, true);
  //measured again when a table's width changes (the window, a side panel opening)
  var watch = window.ResizeObserver ? new ResizeObserver(function (entries) {
    entries.forEach(function (en) { widenAll(en.target); });
  }) : null;
  function all() {
    document.querySelectorAll('table').forEach(function (t) {
      if (!t.querySelector('details.row-fold')) return;
      mark(t);
      if (watch && !t._widenWatched) { t._widenWatched = true; watch.observe(t); }
    });
    setTimeout(function () { widenAll(); }, 0);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', all); else all();
  document.addEventListener('qgen-swapped', all);   // (a list swapped in without a reload)
})();

/* A fold-out that pops out over its row (details.row-pop, the owner 2026-10-26): one open at a time, closed by a click
 * anywhere outside it or Esc. */
(function () {
  function closeAll(except) {
    document.querySelectorAll('details.row-pop[open]').forEach(function (d) { if (d !== except) d.open = false; });
  }
  document.addEventListener('click', function (e) {
    var d = e.target.closest && e.target.closest('details.row-pop');
    closeAll(d);
  });
  //(opens upward when there's no room under it in the list's own scrolling box or the window)
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (!d.matches || !d.matches('details.row-pop') || !d.open) return;
    d.classList.remove('pop-up');
    var body = d.querySelector('.row-pop-body');
    if (!body) return;
    var box = d.closest('.folder-scroll') || document.documentElement;
    var limit = Math.min(box === document.documentElement ? innerHeight : box.getBoundingClientRect().bottom, innerHeight);
    var r = body.getBoundingClientRect(), s = d.getBoundingClientRect();
    if (r.bottom > limit && s.top - r.height - 8 > (box === document.documentElement ? 0 : box.getBoundingClientRect().top)) d.classList.add('pop-up');
  }, true);
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var d = document.querySelector('details.row-pop[open]');
    if (!d) return;
    d.open = false;
    var s = d.querySelector(':scope > summary');
    if (s) s.focus();
  });
})();
