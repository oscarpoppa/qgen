/* <input class="filter" data-filter="#table-id">: hide table rows that don't match.
 * A row can be hidden by more than one filter (the typed text, the Folder menu in the
 * quiz builder): each sets its own flag with qgenHideRow(row, 'name', true/false), and
 * the row shows only when no filter hides it. */
window.qgenHideRow = function (row, key, hide) {
  var flags = (row.dataset.hiddenBy || '').split(' ').filter(function (f) { return f && f !== key; });
  if (hide) flags.push(key);
  row.dataset.hiddenBy = flags.join(' ');
  row.hidden = flags.length > 0;
};

document.querySelectorAll('input.filter[data-filter]').forEach(function (box) {
  var rows = document.querySelectorAll(box.dataset.filter + ' tbody tr');
  box.addEventListener('input', function () {
    var q = box.value.trim().toLowerCase();
    rows.forEach(function (r) { window.qgenHideRow(r, 'text', q && r.textContent.toLowerCase().indexOf(q) === -1); });
    box.dispatchEvent(new CustomEvent('qgen-filtered', { bubbles: true }));
  });
});
