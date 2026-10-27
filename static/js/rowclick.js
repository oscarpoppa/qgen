/* A row in a folder's list opens (or goes) wherever its name does, from anywhere on the row (the owner, 2026-10-23: a standard for every
 * list in a folder, so nobody has to aim at the name): a row that folds open folds open or shut; a row whose name is a link goes
 * to it. Icons, buttons, links and boxes keep doing their own thing, and so does selecting text; a click on the rest of an open row,
 * its open part too, folds it shut (the owner, 2026-10-27). */
(function () {
  var LISTS = '.folder-filter-list, #scan-away, #scan-current, .folder-main';
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button) return;
    var t = e.target;
    if (!t.closest || t.closest('a, button, input, select, textarea, label, summary, dialog, td.tick-col, [data-no-rowclick], details.row-pop, .folder-chip, .pick-chip, .grip-bar, [contenteditable], [role=separator]')) return;
    var row = t.closest('tbody > tr');
    if (!row) return;
    var table = row.closest('table');
    if (!table) return;
    if (window.getSelection && String(window.getSelection()).length) return;
    //(a row that folds open, in any list on the site: anywhere on it opens it or folds it shut, its open part too, but
    //for what's in it that does something of its own (links, chips, buttons, boxes: left out above); the owner,
    //2026-10-27: the open part showed the pointing hand and did nothing)
    var fold = row.querySelector(':scope > td > details.row-fold');
    if (fold) {
      fold.open = !fold.open;
      return;
    }
    if (!table.closest(LISTS)) return;
    //(a row whose name is a link: that link)
    var link = row.querySelector(':scope > td a.name-link[href], :scope > td:first-child a[href]:not([data-page-zoom])');
    if (!link || link.closest('.btn')) return;
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, ctrlKey: e.ctrlKey, metaKey: e.metaKey, shiftKey: e.shiftKey }));
  });
})();
