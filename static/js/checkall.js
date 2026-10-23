/* Check all / Uncheck all on every list of check boxes outside the folder pages (pickers on the
 * Assign page and the quiz editor, the Assign, Write to and folder dialogs...): one check box in the
 * list's heading row, over the column of check boxes, as on the folder pages (static/js/filebar.js).
 * Checked when everything shown is checked, half-checked when some are; a click checks everything
 * shown (the folder chosen, the names that match), or, when all of it is checked already, unchecks
 * what's shown (the rest stays as it is). Each box it changes sends "change", so the page's own scripts keep up. (The owner,
 * 2026-10-22: one box that toggles, in the standard place, instead of two buttons.) */
(function () {
  function rowBoxes(table) {
    return Array.prototype.slice.call(table.querySelectorAll('tbody td.tick-col input[type="checkbox"]'));
  }
  function shown(c) { var tr = c.closest('tr'); return tr && tr.getClientRects().length > 0 && !c.disabled; }

  function sync(table) {
    var head = table.qgenCheckAll;
    if (!head) return;
    var boxes = rowBoxes(table);
    //(a list whose rows are round buttons now, Choose pictures' one-picture mode: none)
    head.hidden = !boxes.length;
    var list = boxes.filter(shown), on = list.filter(function (c) { return c.checked; }).length;
    head.checked = !!list.length && on === list.length;
    head.indeterminate = on > 0 && on < list.length;
    head.disabled = !list.length;
    var words = head.checked ? 'Uncheck all' : 'Check all shown';
    head.title = words; head.setAttribute('aria-label', words);
  }

  function setUp(table) {
    if (table.qgenCheckAll || table.closest('.folder-main') || !rowBoxes(table).length) return;
    var th = table.querySelector('thead tr > th:first-child');
    if (!th || th.querySelector('input')) return;
    var head = document.createElement('input');
    head.type = 'checkbox'; head.className = 'check-all';
    th.classList.add('tick-col');
    //(only its hidden words go: the list's Expand all / Collapse all may be in this cell already)
    th.querySelectorAll(':scope > .sr-only').forEach(function (el) { el.remove(); });
    th.insertBefore(head, th.firstChild);
    table.qgenCheckAll = head;
    head.addEventListener('change', function () {
      //(only what shows, both ways: problems in another folder stay checked; the owner, 2026-10-23)
      var list = rowBoxes(table).filter(shown);
      var every = list.length && list.every(function (c) { return c.checked; });
      list.forEach(function (c) {
        if (c.checked === !every) return;
        c.checked = !every;
        c.dispatchEvent(new Event('change', { bubbles: true }));
      });
      sync(table);
    });
    sync(table);
  }

  //(a row's name checks its box, where the name doesn't open the row: the folder pages' Pictures and
  //Other files; pickers and dialogs do it with their labels. The owner, 2026-10-23)
  document.addEventListener('click', function (e) {
    var td = e.target.closest && e.target.closest('.folder-main td');
    if (!td || e.target.closest('a, button, input, select, label, summary, details')) return;
    var tick = td.previousElementSibling;
    if (!tick || !tick.classList.contains('tick-col') || td.querySelector('details.row-fold')) return;
    var c = tick.querySelector('input[type="checkbox"]');
    if (!c || c.disabled) return;
    c.checked = !c.checked;
    c.dispatchEvent(new Event('change', { bubbles: true }));
  });

  var soon = null;
  function all() {
    soon = null;
    document.querySelectorAll('table').forEach(function (t) { setUp(t); sync(t); });
  }
  function later() { if (!soon) soon = setTimeout(all, 30); }
  //(lists drawn or filled later, a dialog opening, a folder or filter changing what shows)
  ['change', 'input', 'click', 'qgen-shown', 'qgen-filtered', 'qgen-checked'].forEach(function (ev) { document.addEventListener(ev, later, true); });
  new MutationObserver(function (records) {
    if (records.some(function (r) { return r.attributeName === 'open' || r.addedNodes.length; })) later();
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['open'] });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', all); else all();
  //(and once the page's own scripts have checked what's already chosen: a quiz's problems)
  window.addEventListener('load', later);
})();
