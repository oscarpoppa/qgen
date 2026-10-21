/* A list's columns that only an open row fills (td.row-more) show once a row is open: the table is
 * marked .has-open-row here, and app.css hides them otherwise. (Asked in the stylesheet itself,
 * "a table with no open row", Firefox checked every row on every change: 1.3 s of Problems'
 * 2.4 s; the owner, 2026-10-21.) */
(function () {
  function mark(table) {
    if (table) table.classList.toggle('has-open-row', !!table.querySelector('details.row-fold[open]'));
  }
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (d && d.matches && d.matches('details.row-fold')) mark(d.closest('table'));
  }, true);
  function all() { document.querySelectorAll('table').forEach(function (t) { if (t.querySelector('details.row-fold')) mark(t); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', all); else all();
})();
