/* A list table's empty cells (a sparse column: no average yet, no status, no date) show a muted dash,
 * so a blank reads as "none" rather than as something missing (the owner, 2026-10-26). Every list
 * table (table.even-cols, and any table in a .table-wrap); not the check box or buttons' cells. */
(function () {
  var SHOWS = 'img, svg, input, button, select, textarea, a, .badge, .side-dot, .status-icon, details, .no-data';
  function fill(root) {
    (root || document).querySelectorAll('table.even-cols > tbody > tr > td, .table-wrap > table > tbody > tr > td').forEach(function (td) {
      if (td.classList.contains('tick-col') || td.classList.contains('actions')) return;
      if (td.textContent.trim() || td.querySelector(SHOWS)) return;
      var dash = document.createElement('span');
      dash.className = 'no-data';
      dash.title = 'None yet';
      dash.textContent = '—';
      td.appendChild(dash);
    });
  }
  window.qgenNoData = fill;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { fill(); });
  else fill();
  document.addEventListener('qgen-swapped', function () { fill(); });   // (a list swapped in without a reload)
})();
