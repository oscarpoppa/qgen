/* Every dialog that picks a folder (Put in folder, a row's Move, a folder's Move, the Archive's
 * Move: dialog.put-dialog with its ul.put-list) gets the standard picker's top: "Filter by name…",
 * Clear and how many folders show (filter.js), and, where folders are checked (Put in folder),
 * Check all shown / Uncheck all beside its "N checked" (the owner, 2026-10-20). The filter starts
 * empty each time the dialog opens. */
(function () {
  var n = 0;
  function setup(d) {
    var list = d.querySelector('ul.put-list');
    if (!list) return;
    var bar = d.querySelector('.dlg-filter');
    if (!bar) {
      if (!list.id) list.id = 'dlg-list-' + (++n);
      bar = document.createElement('div');
      bar.className = 'btn-row small pick-bar filter-bar dlg-filter';
      bar.setAttribute('data-filter-bar', '');
      bar.dataset.filter = '#' + list.id; bar.dataset.items = 'li';
      bar.dataset.one = 'folder'; bar.dataset.many = 'folders';
      bar.innerHTML = '<span class="filter-box"><input type="search" class="filter-list" placeholder="Filter by name…" aria-label="Filter folders by name" title="Type part of a name to show only the folders that match">'
        + '<button type="button" class="btn btn-secondary btn-sm" data-filter-clear title="Show all the folders again">Clear</button></span>'
        + '<span class="pick-count muted" data-filter-count aria-live="polite"></span>';
      var tools = d.querySelector('.assign-many-tools');
      (tools || list).parentNode.insertBefore(bar, tools || list);
      //(the standard dialog for listed things, as the pickers' (the owner, 2026-10-21): a tab naming
      //the list, "All folders" and how many, over a framed panel holding the list as square rows
      //under a heading, "Folder")
      var frame = document.createElement('div');
      frame.className = 'put-frame';
      frame.innerHTML = '<div class="folder-filter-rows folder-filter-onetab"><div class="folder-tabs">'
        + '<span class="folder-tab folder-tab-name" aria-pressed="true">' + (window.qgenIcon ? window.qgenIcon('folders') : '')
        + '<span class="box-title">All folders</span><span class="badge box-count" data-put-total></span></span></div></div>'
        + '<div class="put-panel"><div class="table-wrap put-table"><div class="put-head" aria-hidden="true">Folder</div></div></div>';
      list.parentNode.insertBefore(frame, list);
      frame.querySelector('.put-table').appendChild(list);
      var total = frame.querySelector('[data-put-total]');
      function recount() { var n = list.querySelectorAll(':scope > li').length; total.textContent = n; total.title = n + (n === 1 ? ' folder' : ' folders'); }
      recount();
      new MutationObserver(recount).observe(list, { childList: true });
      if (window.qgenFilterBar) window.qgenFilterBar(bar);
      //(Enter in the filter box never sends the dialog's form: a folder's Move is a form)
      bar.querySelector('input.filter-list').addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
      //(a list filled in after the dialog opens, like Put in folder's: counted and filtered again)
      new MutationObserver(function () { if (bar.qgenRun) bar.qgenRun(); checksFit(); }).observe(list, { childList: true, subtree: true, attributes: true, attributeFilter: ['type'] });
      //(folders to check: the standard Check all shown / Uncheck all, beside "N checked")
      if (tools && !tools.querySelector('[data-dlg-check]')) {
        tools.classList.add('write-to-checks');
        tools.insertAdjacentHTML('afterbegin',
          '<button type="button" class="btn btn-secondary btn-sm" data-dlg-check="all" title="Check every folder in the list below (the ones that match the filter)">Check all shown</button>'
          + '<button type="button" class="btn btn-secondary btn-sm" data-dlg-check="none" title="Uncheck every folder">Uncheck all</button>');
        tools.addEventListener('click', function (e) {
          var b = e.target.closest('[data-dlg-check]');
          if (!b) return;
          list.querySelectorAll('input[type=checkbox]').forEach(function (c) {
            if (c.disabled) return;
            if (b.dataset.dlgCheck === 'none') c.checked = false;
            else if (c.closest('li').offsetParent) c.checked = true;
            c.dispatchEvent(new Event('change', { bubbles: true }));
          });
        });
      }
    }
    checksFit();
    //(each opening starts with the whole list)
    var input = bar.querySelector('input.filter-list');
    input.value = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
  //Check all shown / Uncheck all only while the folders are check boxes (Put in folder's "Copy
  //instead" checks several; moving picks one, so they'd mean nothing then)
  function checksFit() {
    document.querySelectorAll('dialog.put-dialog').forEach(function (d) {
      var some = !!d.querySelector('ul.put-list input[type=checkbox]');
      d.querySelectorAll('[data-dlg-check]').forEach(function (b) { b.hidden = !some; });
    });
  }
  function watch() {
    new MutationObserver(function (records) {
      records.forEach(function (r) {
        var d = r.target;
        if (r.attributeName === 'open' && d.open && d.matches && d.matches('dialog.put-dialog')) setTimeout(function () { setup(d); }, 0);
        //every dialog with a filter opens with the cursor in it, ready to type (not on a touch
        //screen, where that would pop up the keyboard: the user critic, 2026-10-20)
        if (r.attributeName === 'open' && d.open && d.tagName === 'DIALOG' && !matchMedia('(pointer: coarse)').matches) {
          setTimeout(function () {
            var f = d.querySelector('input.filter-list');
            if (f && f.offsetParent) f.focus();
          }, 30);
        }
      });
    }).observe(document.body, { attributes: true, attributeFilter: ['open'], subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch); else watch();
})();
