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
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (d && d.matches && d.matches('details.row-fold')) mark(d.closest('table'));
  }, true);
  function all() { document.querySelectorAll('table').forEach(function (t) { if (t.querySelector('details.row-fold')) mark(t); }); }
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
