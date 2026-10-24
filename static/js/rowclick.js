/* A row in a folder's list opens (or goes) wherever its name does, from anywhere on the row (the owner, 2026-10-23: a standard for every
 * list in a folder, so nobody has to aim at the name): a row that folds open folds open or shut; a row whose name is a link goes
 * to it. Icons, buttons, links, boxes and the words of an open row's inside keep doing their own thing, and so does selecting text. */
(function () {
  var LISTS = '.folder-filter-list, #scan-away, #scan-current, .folder-main';
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button) return;
    var t = e.target;
    if (!t.closest || t.closest('a, button, input, select, textarea, label, summary, dialog, td.tick-col, [data-no-rowclick]')) return;
    var row = t.closest('tbody > tr');
    if (!row) return;
    var table = row.closest('table');
    if (!table || !table.closest(LISTS)) return;
    if (window.getSelection && String(window.getSelection()).length) return;
    //(a row that folds open: anywhere on the row but inside what it holds when open)
    var fold = row.querySelector(':scope > td > details.row-fold');
    if (fold) {
      if (fold.contains(t) && !t.closest('summary')) return;
      fold.open = !fold.open;
      return;
    }
    //(a row whose name is a link: that link)
    var link = row.querySelector(':scope > td a.name-link[href], :scope > td:first-child a[href]:not([data-page-zoom])');
    if (!link || link.closest('.btn')) return;
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, ctrlKey: e.ctrlKey, metaKey: e.metaKey, shiftKey: e.shiftKey }));
  });
})();
