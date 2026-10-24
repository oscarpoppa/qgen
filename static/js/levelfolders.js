/* A folder page's two columns start level (the owner, 2026-10-24: "the All folder in the folder list should line up
 * with the All name on the folder tab"; the line under the filter row then meets the middle of the New folder icon,
 * as on All problems, the model page). What's above each column differs from page to page (a title with buttons or
 * without, a page heading with an avatar, the Archive's sections), so the column that's higher is moved down by the
 * difference, measured: the folder list's first row (All) against the name on the open folder's tab. Not when the
 * columns are stacked (a phone). Done before the page shows (base.html's js-setup), and again when the window,
 * fonts or what's above the columns change. The open folder is moved with padding, never its margin: folders.js lift()
 * sets that margin to raise it beside the page's title. */
(function () {
  var watch = null;
  function level() {
    document.querySelectorAll('.folders-layout').forEach(function (layout) {
      var side = layout.querySelector(':scope > .folder-side'), main = layout.querySelector(':scope > .folder-main');
      if (!side || !main) return;
      var all = side.querySelector('.side-top > li .side-row'), tab = main.querySelector('.folder-filter-onetab .folder-tab-name');
      if (!all || !tab) return;
      var s = parseFloat(side.style.marginTop) || 0, m = parseFloat(main.style.paddingTop) || 0;
      var sr = side.getBoundingClientRect(), mr = main.getBoundingClientRect();
      //(stacked on a phone: nothing to line up)
      if (mr.left < sr.right - 1) { if (s || m) { side.style.marginTop = ''; main.style.paddingTop = ''; } return; }
      var a = all.getBoundingClientRect(), t = tab.getBoundingClientRect();
      var dy = Math.round((t.top + t.height / 2) - (a.top + a.height / 2));
      if (!dy) return;
      //(how much lower the folder list starts than the open folder, after this)
      var shift = s - m + dy;
      var ns = Math.max(0, shift), nm = Math.max(0, -shift);
      if (ns !== s) side.style.marginTop = ns ? ns + 'px' : '';
      if (nm !== m) main.style.paddingTop = nm ? nm + 'px' : '';
    });
    //the stash on Scan workbook pages: its folder list (All scans) against its open folder's tab, the same way
    document.querySelectorAll('.stash-split').forEach(function (split) {
      var side = split.querySelector(':scope > .stash-folders'), main = split.querySelector(':scope > .stash-main');
      if (!side || !main) return;
      var all = side.querySelector('.side-row'), tab = main.querySelector('.folder-tab-name') || main.querySelector('.folder-tab');
      if (!all || !tab) return;
      var s = parseFloat(side.style.marginTop) || 0, m = parseFloat(main.style.marginTop) || 0;
      if (main.getBoundingClientRect().left < side.getBoundingClientRect().right - 1) { if (s || m) { side.style.marginTop = ''; main.style.marginTop = ''; } return; }
      var a = all.getBoundingClientRect(), t = tab.getBoundingClientRect();
      var dy = Math.round((t.top + t.height / 2) - (a.top + a.height / 2));
      if (!dy) return;
      var shift = s - m + dy, ns = Math.max(0, shift), nm = Math.max(0, -shift);
      if (ns !== s) side.style.marginTop = ns ? ns + 'px' : '';
      if (nm !== m) main.style.marginTop = nm ? nm + 'px' : '';
    });
    //every folder picker laid out the same way (a dialog's Move to, New folder, Assign's cards, the editors' Folder card):
    //its open-folder tab and list come down until the tab's name is level with the folder list's first row (To do 32,
    //the owner 2026-10-24: "All folders on the left at the same level as the All folders tab on the right")
    document.querySelectorAll('.folder-filter[data-style="list"]').forEach(function (box) {
      //(watched from the first time it's seen: its folder list dragged wider, a side panel opening)
      if (watch && !box._levelWatched) { box._levelWatched = true; watch.observe(box); }
      var side = box.querySelector(':scope > .folder-filter-side'), tabs = box.querySelector(':scope > .folder-filter-onetab');
      var head = side;  // (the folder list itself moves when it's the higher one; the heading over it stays)
      if (!side || !tabs || !box.offsetParent) return;
      var all = side.querySelector('.side-row'), tab = tabs.querySelector('.folder-tab-name') || tabs.querySelector('.folder-tab');
      if (!all || !tab) return;
      var s = parseFloat(head.style.marginTop) || 0, m = parseFloat(tabs.style.marginTop) || 0;
      if (tabs.getBoundingClientRect().left < side.getBoundingClientRect().right - 1) { if (s || m) { head.style.marginTop = ''; tabs.style.marginTop = ''; } return; }
      var a = all.getBoundingClientRect(), t = tab.getBoundingClientRect();
      var dy = Math.round((t.top + t.height / 2) - (a.top + a.height / 2));
      if (!dy) return;
      var shift = s - m + dy, ns = Math.max(0, shift), nm = Math.max(0, -shift);
      if (ns !== s) head.style.marginTop = ns ? ns + 'px' : '';
      if (nm !== m) tabs.style.marginTop = nm ? nm + 'px' : '';
    });
  }
  function soon() { clearTimeout(soon._t); soon._t = setTimeout(level, 0); }
  //(and once more right after, when the page's other scripts have moved things: still before the page shows, base.html)
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { level(); soon(); }); else level();
  window.addEventListener('load', soon);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(soon);
  window.addEventListener('resize', soon);
  //(the title rows wrapping when a side panel opens, a filter showing its count...)
  if (window.ResizeObserver) {
    watch = new ResizeObserver(soon);
    document.querySelectorAll('.folders-layout > .folder-main > :not(.folder-filter):not(div:last-child), .folders-layout > .folder-side, .folders-layout').forEach(function (el) { watch.observe(el); });
  }
  //(a dialog's picker is drawn when it opens; a picker folds open; a filter redraws a list)
  document.addEventListener('toggle', soon, true);
  document.addEventListener('qgen-filtered', soon);
  document.addEventListener('qgen-stash-redrawn', soon);  // (the stash's card drawn again: scan_start.html)
  if (window.MutationObserver) new MutationObserver(function (rs) {
    if (rs.some(function (r) { return r.target.tagName === 'DIALOG' && r.target.open; })) setTimeout(level, 30);
  }).observe(document.body, { attributes: true, attributeFilter: ['open'], subtree: true });
  window.qgenLevelFolders = level;
})();
