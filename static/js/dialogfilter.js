/* The folder dialogs (Move / Put in a folder, the checked bar's Move, a row's Move, a folder's own
 * Move to: dialog.put-dialog) have the layout and feel of the Assign dialogs (the owner, 2026-10-22):
 * the standard picker, as app/templates/_pick.html draws it: "Filter by name…", Clear and how many
 * folders show (filter.js), then a side folder list (All folders, Checked while the folders are
 * check boxes, Uncategorized where the dialog offers "out of every folder": pinned at the top; then
 * the folders, nested and indented) beside a tab naming what's shown over a framed table, "Folder",
 * one row per folder, indented by its depth just as in the side list (static/js/folderfilter.js
 * draws the side list and the tab). Where folders are checked (Put in folder's "Copy instead"),
 * Check all shown / Uncheck all and "N checked" sit on their own line under the filter. Each
 * opening starts with the filter empty and the list on All.
 *
 * window.qgenFolderPick: html() the holder a script-made dialog puts its picker in; fill(holder,
 * folders, o) its rows ([{id, name, depth, icon}], o.type 'radio' / 'checkbox', o.name, o.top: the words
 * for "out of every folder" or none, o.each(folder, input, label)); fromSelect(select) the folders
 * of an indented <select> (folder_tree.indent). A dialog drawn by the server has the holder
 * (data-folder-pick) with its rows in script[data-pick-rows], drawn the first time it opens. */
(function () {
  var n = 0;
  function icon(name) { return window.qgenIcon ? window.qgenIcon(name) : ''; }
  var pick = window.qgenFolderPick = {};

  var TABLE = '<div class="table-wrap pick-wrap"><table class="pick-table">'
    + '<thead><tr><th class="tick-col"><span class="sr-only">Check</span></th><th>Folder</th></tr></thead><tbody></tbody></table></div>';
  pick.html = function () { return '<div class="field pick-people folder-pick" data-folder-pick>' + TABLE + '</div>'; };

  //a dialog drawn by the server (a folder's Move to) brings its folders as [[id, name, depth, icon]]
  //in script[data-pick-rows]: round buttons named data-name, data-checked chosen to begin with
  function fromRows(holder) {
    var data = holder.querySelector('script[data-pick-rows]');
    if (!data || holder.querySelector('table')) return;
    holder.insertAdjacentHTML('beforeend', TABLE);
    var rows = JSON.parse(data.textContent).map(function (f) { return { id: String(f[0]), name: f[1], depth: f[2], icon: f[3] }; });
    pick.fill(holder, rows, { type: 'radio', name: holder.dataset.name, top: holder.dataset.mainLabel,
      each: function (f, r) { if (String(f.id) === holder.dataset.checked) r.defaultChecked = r.checked = true; } });
  }

  //(a row per folder; "out of every folder" first, right after All as in the side list: the owner,
  //2026-10-22, it was last)
  pick.fill = function (holder, folders, o) {
    var body = holder.querySelector('tbody');
    body.textContent = '';
    if (o.top) holder.dataset.mainLabel = o.top;
    (o.top ? [{ id: 'top', name: o.top, depth: 1 }] : []).concat(folders).forEach(function (f) {
      var tr = document.createElement('tr'), c = document.createElement('td'), t = document.createElement('td');
      tr.dataset.box = 'folder:' + f.id; tr.dataset.depth = f.depth; tr.dataset.folderName = f.name; tr.dataset.icon = f.icon || 'folder';
      c.className = 'tick-col';
      var i = document.createElement('input');
      i.type = o.type || 'radio'; i.name = o.name; i.value = f.id; i.id = 'folder-pick-row-' + (++n);
      c.appendChild(i);
      var lab = document.createElement('label');
      lab.htmlFor = i.id;
      //(indented one level per depth, 14px, exactly as the side list: the owner, 2026-10-22; every
      //level had the same 12px before)
      if (f.depth > 1) lab.style.paddingLeft = ((f.depth - 1) * 14) + 'px';
      lab.innerHTML = icon(f.id === 'top' ? 'tray' : f.icon || 'folder');  // (a student's Archive folder: a person)
      var nm = document.createElement('span');
      nm.textContent = f.name;
      lab.appendChild(nm);
      t.appendChild(lab);
      tr.appendChild(c); tr.appendChild(t);
      body.appendChild(tr);
      if (o.each) o.each(f, i, lab);
    });
    if (holder.qgenPick) holder.qgenPick.redraw();
  };

  //the folders of a <select> indented by folder_tree.indent (three non-breaking spaces a level);
  //its "top" choice is the words for "out of every folder"
  pick.fromSelect = function (sel) {
    var out = { folders: [], top: null };
    Array.prototype.forEach.call(sel.options, function (o) {
      if (!o.value) return;
      var text = o.textContent, pad = (text.match(/^\u00a0+/) || [''])[0].length;
      if (o.value === 'top') { out.top = text.trim(); return; }
      out.folders.push({ id: o.value, name: text.replace(/^\u00a0+/, ''), depth: Math.floor(pad / 3) + 1, disabled: o.disabled, icon: o.dataset.icon });
    });
    return out;
  };

  //the amber "What happens:" box's lines (an empty one left out)
  pick.happens = function (ul, lines) {
    ul.textContent = '';
    lines.forEach(function (t) {
      if (!t) return;
      var li = document.createElement('li');
      li.textContent = t;
      ul.appendChild(li);
    });
  };

  //the side list's folders, from the rows: each folder holds its own row and its folders' rows
  function treeOf(holder) {
    var out = [], path = [];
    holder.querySelectorAll('tbody tr[data-box]').forEach(function (tr) {
      var id = tr.dataset.box.slice(7);
      if (!/^\d+$/.test(id)) return;  // (out of every folder: in none, so under Uncategorized)
      var depth = +tr.dataset.depth || 1;
      var node = { id: +id, name: tr.dataset.folderName || tr.textContent.trim(), count: 0, keys: [], children: [], icon: tr.dataset.icon || 'folder' };
      path.length = Math.min(path.length, depth - 1);
      (path.length ? path[path.length - 1].children : out).push(node);
      path.push(node);
      path.forEach(function (p) { p.keys.push(tr.dataset.box); p.count++; });
    });
    return out;
  }

  function build(holder) {
    if (holder.qgenPick) return holder.qgenPick;
    var d = holder.closest('dialog'), wrap = holder.querySelector('.pick-wrap');
    var box = document.createElement('div'), ds = box.dataset;
    box.className = 'folder-filter';
    ds.prefix = 'folder:'; ds.allLabel = 'All folders'; ds.unit = 'folder'; ds.units = 'folders';
    ds.start = 'all'; ds.style = 'list'; ds.remember = holder.dataset.remember || 'folder-pick';
    //(Uncategorized only where the dialog offers "out of every folder"; left out otherwise)
    if (holder.dataset.mainLabel) ds.mainLabel = holder.dataset.mainLabel; else ds.hideEmpty = '';
    var tree = document.createElement('script');
    tree.type = 'application/json'; tree.className = 'folder-filter-tree';
    tree.textContent = JSON.stringify(treeOf(holder));
    var list = document.createElement('div');
    list.className = 'folder-filter-list'; list.id = 'folder-pick-' + (++n);
    //(a drag bar static/js/grip.js already put under the table moves with it: on a page, it was left
    //at the top, beside the filter: the owner, 2026-10-22)
    var grip = wrap.nextElementSibling && wrap.nextElementSibling.classList.contains('grip-bar') ? wrap.nextElementSibling : null;
    box.appendChild(tree); box.appendChild(list); list.appendChild(wrap);
    if (grip) list.appendChild(grip);
    //the filter, as filter_bar() draws it
    var bar = document.createElement('div');
    bar.className = 'btn-row small pick-bar filter-bar';
    bar.setAttribute('data-filter-bar', '');
    bar.dataset.filter = '#' + list.id; bar.dataset.items = 'tr[data-box]'; bar.dataset.one = 'folder'; bar.dataset.many = 'folders';
    bar.innerHTML = '<span class="filter-box"><input type="search" class="filter-list" placeholder="Filter by name…" aria-label="Filter folders by name" title="Type part of a name to show only the folders that match">'
      + '<button type="button" class="btn btn-secondary btn-sm" data-filter-clear title="Show all the folders again">Clear</button></span>'
      + '<span class="pick-count muted" data-filter-count aria-live="polite"></span>';
    //(folders to check: the standard Check all shown / Uncheck all, beside "N checked")
    var checks = document.createElement('div');
    checks.className = 'btn-row small write-to-checks';
    checks.innerHTML = '<button type="button" class="btn btn-secondary btn-sm" data-dlg-check="all" title="Check every folder in the list below (the ones that match the filter)">Check all shown</button>'
      + '<button type="button" class="btn btn-secondary btn-sm" data-dlg-check="none" title="Uncheck every folder">Uncheck all</button>'
      + '<span class="muted small" data-pick-count aria-live="polite"></span>';
    holder.appendChild(bar); holder.appendChild(checks); holder.appendChild(box);
    function boxes() { return Array.prototype.slice.call(list.querySelectorAll('tbody input[type=checkbox]')); }
    //(only while the folders are check boxes: moving picks one, so they'd mean nothing then)
    function sync() {
      var all = boxes();
      checks.hidden = !all.length;
      checks.querySelector('[data-pick-count]').textContent = all.filter(function (c) { return c.checked && !c.disabled; }).length + ' checked';
    }
    checks.addEventListener('click', function (e) {
      var b = e.target.closest('[data-dlg-check]');
      if (!b) return;
      boxes().forEach(function (c) {
        if (c.disabled) return;
        var tr = c.closest('tr');
        if (b.dataset.dlgCheck === 'none') c.checked = false;
        else if (!tr.hidden && !tr.closest('[hidden]')) c.checked = true;
        c.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
    holder.addEventListener('change', sync);
    //(the dialog's title: where folderfilter.js puts the side list's Expand all / Collapse all)
    var head = d && d.querySelector('[data-pick-head]');
    if (head) {
      if (!head.id) head.id = 'folder-pick-head-' + (++n);
      d.setAttribute('aria-labelledby', head.id);
      d.removeAttribute('aria-label');
    }
    box.setAttribute('data-folder-filter', '');
    if (window.qgenFolderFilterSetUp) window.qgenFolderFilterSetUp(box);
    if (window.qgenFilterBar) window.qgenFilterBar(bar);
    var input = bar.querySelector('input.filter-list');
    sync();
    return (holder.qgenPick = {
      box: box,
      //(rows filled again: counted and filtered again; no Checked folder without check boxes)
      redraw: function () {
        sync();
        if (!boxes().length && box.dataset.shown === 'checked') box.qgenChoose('all'); else if (box.qgenRedraw) box.qgenRedraw();
      },
      reset: function () {
        input.value = '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        if (box.qgenChoose) box.qgenChoose('all');
        sync();
      }
    });
  }
  pick.build = build;

  function watch() {
    new MutationObserver(function (records) {
      records.forEach(function (r) {
        var d = r.target;
        if (r.attributeName === 'open' && d.open && d.matches && d.matches('dialog.put-dialog')) {
          setTimeout(function () {
            var h = d.querySelector('[data-folder-pick]');
            if (h) { fromRows(h); build(h).reset(); }
          }, 0);
        }
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
