/* The All view of a folder page (_folders.html all_boxes): everything is in one list, each
 * thing once, and a row of folder buttons above it narrows the list to one folder (with the
 * folders inside it). "All" is first and chosen to begin with; then the folders, then
 * Uncategorized (what's in no folder; grayed out when everything is in one). Choosing a folder
 * that has folders inside it shows a second row with those. The chosen folder's own buttons
 * ("Open this folder", "Assign a quiz to this folder") sit at the end of its row. The choice is
 * remembered for the page while the tab is open. A folder button takes a drag like the folder
 * list does (data-drop). Works with the name filter: each hides with its own flag (filter.js). */
(function () {
  var uid = 0;
  function setUp(box) {
    if (box.qgenFolderFilter) return;
    box.qgenFolderFilter = true;
    var data = box.querySelector('.folder-filter-tree'), list = box.querySelector('.folder-filter-list');
    if (!data || !list) return;
    var tree = JSON.parse(data.textContent), prefix = box.dataset.prefix || '';
    //what names a thing: data-box, or another data- attribute (data-key-attr)
    var attr = box.dataset.keyAttr || 'box', sel = 'data-' + attr.replace(/[A-Z]/g, function (c) { return '-' + c.toLowerCase(); });
    function keyOf(el) { return el.dataset[attr]; }
    var units = box.dataset.units || 'things', unit = box.dataset.unit || 'thing';
    var memKey = 'qgen-folder-filter:' + (box.dataset.remember || location.pathname);
    var byId = {}, parentOf = {};
    (function index(nodes, parent) {
      nodes.forEach(function (n) { byId[n.id] = n; parentOf[n.id] = parent === null ? null : String(parent); n.keySet = {}; n.keys.forEach(function (k) { n.keySet[k] = 1; }); index(n.children, n.id); });
    })(tree, null);

    function items() {
      return Array.prototype.filter.call(list.querySelectorAll('[' + sel + '^="' + prefix + '"]'), function (el) {
        return el.parentElement.closest('[' + sel + '^="' + prefix + '"]') === null;  // the things themselves, not parts of them
      });
    }
    var inSome = {};
    tree.forEach(function (n) { if (typeof n.id === 'number') n.keys.forEach(function (k) { inSome[k] = 1; }); });  // (New, In progress: not folders)
    var loose = items().filter(function (el) { return !inSome[keyOf(el)]; }).length;
    function count(n) { return n + ' ' + (n === 1 ? unit : units); }

    if (!list.id) list.id = 'folder-list-' + (++uid);
    var rows = document.createElement('div');
    rows.className = 'folder-filter-rows';
    box.insertBefore(rows, list);

    function button(id, label, n, icon) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'folder-tab';
      b.dataset.folder = id;
      if (window.qgenIcon) b.insertAdjacentHTML('beforeend', window.qgenIcon(icon));
      var name = document.createElement('span');
      name.className = 'box-title';
      name.textContent = label;
      var c = document.createElement('span');
      c.className = 'badge box-count';
      c.textContent = count(n);
      b.appendChild(name);
      b.appendChild(c);
      if (!n && id !== 'all') b.classList.add('is-empty');
      b.title = 'Show ' + (id === 'all' ? 'everything' : 'what’s in “' + label + '”');
      if ('droppable' in box.dataset && id !== 'all' && (id === 'none' || /^\d+$/.test(id))) b.dataset.drop = id === 'none' ? 'top' : id;
      return b;
    }

    var chosen = 'all';
    try { chosen = sessionStorage.getItem(memKey) || 'all'; } catch (e) {}
    if (chosen !== 'all' && chosen !== 'none' && !byId[chosen]) chosen = 'all';
    if (chosen === 'none' && !loose) chosen = 'all';

    function path() {  // the chosen folder and the folders it's in, from the top
      var out = [], id = chosen;
      while (id && byId[id]) { out.unshift(String(id)); id = parentOf[id]; }
      return out;
    }
    function tools(id) {
      var span = document.createElement('span');
      span.className = 'folder-filter-tools-now';
      //Expand all / Collapse all for what this folder shows (boxes.js shows them with two or
      //more boxes, and puts these first: the page's own pair steps aside meanwhile)
      var label = id === null ? (box.dataset.mainLabel || 'Uncategorized') : byId[id].name;
      var pair = document.createElement('span');
      pair.className = 'level-buttons';
      [['open', 'Expand all', 'Open every one in \u201c'], ['close', 'Collapse all', 'Fold every one in \u201c']].forEach(function (b) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-secondary btn-xs';
        btn.dataset.level = b[0];
        btn.dataset.levelOf = '#' + list.id;
        btn.dataset.levelPrefer = '';
        btn.textContent = b[1];
        btn.setAttribute('aria-label', b[1] + ' in ' + label);
        btn.title = b[2] + label + '\u201d';
        pair.appendChild(btn);
      });
      span.appendChild(pair);
      var t = box.querySelector('template.folder-filter-tools[data-for="' + id + '"]');
      if (t) span.appendChild(t.content.cloneNode(true));
      var n = byId[id], url = n ? n.url : box.dataset.mainUrl;
      if (!url) return span;
      var open = document.createElement('a');
      open.className = 'btn btn-secondary btn-xs';
      open.href = url;
      open.textContent = 'Open this folder';
      open.title = n ? 'Go into “' + n.name + '” to see just what’s in it' : 'See just what’s in no folder';
      span.appendChild(open);
      return span;
    }

    function draw() {
      rows.textContent = '';
      var p = path();
      //the top row: All, the folders, Uncategorized
      var row = document.createElement('div');
      row.className = 'folder-tabs';
      row.setAttribute('role', 'group');
      row.setAttribute('aria-label', 'Folders');
      var label = document.createElement('span');
      label.className = 'folder-tabs-label';
      label.textContent = 'Folders';
      row.appendChild(label);
      row.appendChild(button('all', box.dataset.allLabel || 'All', items().length, 'folders'));
      tree.forEach(function (n) { row.appendChild(button(String(n.id), n.name, n.count, n.icon || 'folder')); });
      var none = button('none', box.dataset.mainLabel || 'Uncategorized', loose, 'tray');
      if (!loose) { none.disabled = true; none.title = 'Everything is in a folder'; }
      row.appendChild(none);
      rows.appendChild(row);
      //a row for the folders inside each chosen folder
      p.forEach(function (id) {
        var n = byId[id];
        if (!n.children.length) return;
        var sub = document.createElement('div');
        sub.className = 'folder-tabs folder-tabs-inner';
        sub.setAttribute('role', 'group');
        sub.setAttribute('aria-label', 'Folders in ' + n.name);
        var l = document.createElement('span');
        l.className = 'folder-tabs-label';
        l.textContent = 'In “' + n.name + '”';
        sub.appendChild(l);
        n.children.forEach(function (c) { sub.appendChild(button(String(c.id), c.name, c.count, 'folder')); });
        rows.appendChild(sub);
      });
      //which buttons are chosen: the folder and the ones it's in
      rows.querySelectorAll('.folder-tab').forEach(function (b) {
        var on = b.dataset.folder === chosen || p.indexOf(b.dataset.folder) !== -1;
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        b.setAttribute('aria-expanded', on ? 'true' : 'false');
      });
      //the chosen folder's own buttons at the end of the last row
      if (chosen !== 'all') {
        var t = tools(chosen === 'none' ? null : chosen);
        if (t.childNodes.length) rows.lastElementChild.appendChild(t);
      }
    }

    function apply() {
      var keep = chosen === 'all' ? null : chosen === 'none' ? null : byId[chosen].keySet;
      items().forEach(function (el) {
        var k = keyOf(el), hide = chosen === 'none' ? !!inSome[k] : keep ? !keep[k] : false;
        window.qgenHideRow ? window.qgenHideRow(el, 'folder', hide) : (el.hidden = hide);
      });
      //a folder with nothing in it says so
      var shown = items().some(function (el) { return !el.hidden; });
      var note = box.querySelector('.folder-filter-empty');
      if (!note) {
        note = document.createElement('p');
        note.className = 'card empty small folder-filter-empty';
        list.parentElement.insertBefore(note, list.nextSibling);
      }
      note.hidden = shown || chosen === 'all';
      list.hidden = !shown && chosen !== 'all';  // (no empty frame above the note)
      note.textContent = chosen === 'none' ? 'Everything is in a folder.' : 'Nothing in \u201c' + (byId[chosen] ? byId[chosen].name : '') + '\u201d yet.';
      //empty tables' headings and the counts follow
      list.querySelectorAll('table').forEach(function (t) {
        var rowsIn = t.querySelectorAll('tbody tr[data-box]');
        if (rowsIn.length) t.hidden = Array.prototype.every.call(rowsIn, function (r) { return r.hidden; });
      });
      document.querySelectorAll('[data-filter-bar]').forEach(function (bar) { if (bar.qgenRun) bar.qgenRun(); });
      if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();
    }

    rows.addEventListener('click', function (e) {
      var b = e.target.closest('.folder-tab');
      if (!b || b.disabled) return;
      var id = b.dataset.folder;
      //pressing the chosen folder again goes back up a level (or to All)
      if (id === chosen) id = byId[id] && parentOf[id] ? parentOf[id] : 'all';
      choose(id);
    });
    //the folder list down the side picks the same folders here, in place (no new page)
    function same(a, url) { if (!url) return false; var u = new URL(url, location.href); return a.pathname === u.pathname && a.search === u.search; }
    function sideFor(a) {
      if (same(a, box.dataset.allUrl)) return 'all';
      if (same(a, box.dataset.mainUrl)) return loose ? 'none' : null;
      for (var id in byId) if (/^\d+$/.test(id) && same(a, byId[id].url)) return id;
      return null;
    }
    function markSide() {
      document.querySelectorAll('.side-row a[href]').forEach(function (a) {
        var id = sideFor(a);
        if (id === null) return;
        var on = id === chosen;
        a.closest('.side-row').classList.toggle('current', on);
        if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
      });
    }
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('.side-row a[href]');
      if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var id = sideFor(a);
      if (id === null) return;
      e.preventDefault();
      choose(id);
    });
    function choose(id) {
      chosen = id;
      try { sessionStorage.setItem(memKey, chosen); } catch (err) {}
      draw();
      apply();
      markSide();
    }
    draw();
    apply();
    markSide();
  }
  function all() { document.querySelectorAll('[data-folder-filter]').forEach(setUp); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', all); else all();
})();
