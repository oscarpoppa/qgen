/* The All view of a folder page (_folders.html all_boxes): everything is in one list, each
 * thing once, and a row of folder buttons above it narrows the list to one folder (with the
 * folders inside it). "All" is first and chosen to begin with; then the folders, then
 * Uncategorized (what's in no folder; grayed out when everything is in one). Choosing a folder
 * shows a second row laid out like the top one: "All" (chosen while everything in X is
 * shown), the folders inside it, then "Uncategorized" (what's in none of them; grayed out when X
 * has no folders inside). Every level, All included, has Expand all / Collapse all at its end. The chosen folder's own buttons
 * ("Open this folder", "Assign a quiz to this folder") sit at the end of its row. The page starts on
 * All; the choice is kept only across reloads from the page itself. A folder button takes a drag like the folder
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
    var byId = Object.create(null), parentOf = Object.create(null);  // (no inherited names: ?tab=constructor is just unknown)
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
      //(a plain number, so the tabs fit on one line; the words are in its tooltip)
      c.textContent = n;
      c.title = count(n);
      c.dataset.n = n;
      b.appendChild(name);
      b.appendChild(c);
      b.title = 'Show ' + (id === 'all' ? 'everything' : 'what’s in “' + label + '”');
      //(a real folder opens its own page on a double-click: said here, the owner 2026-10-16)
      if (/^\d+$/.test(id) || (byId[id] && byId[id].url)) b.title += ' (double-click: open this folder)';
      //(nothing in it: grayed; and with no folders inside either, it doesn't open (the folder list
      //still opens it, for its Folder options); one holding only empty folders opens, to show
      //them: the owner, 2026-10-14)
      if (!n && id !== 'all') {
        b.classList.add('is-empty');
        var kids = byId[id] && byId[id].children;
        if (!(kids && kids.length)) { b.disabled = true; b.title = 'Nothing in “' + label + '” yet'; }
      }
      if ('droppable' in box.dataset && id !== 'all' && (id === 'none' || /^\d+$/.test(id))) b.dataset.drop = id === 'none' ? 'top' : id;
      return b;
    }

    //the page starts on All; only coming back to it from itself (a button here that reloads it,
    //e.g. a move or a drop) keeps the folder that was chosen
    //(data-start: the tab an address asks for, e.g. My quizzes?folder=new from Home)
    var chosen = box.dataset.start || 'all', fromHere = false;
    try { fromHere = !!document.referrer && new URL(document.referrer).pathname === location.pathname; } catch (e) {}
    try { if (fromHere && !box.dataset.start) chosen = sessionStorage.getItem(memKey) || 'all'; } catch (e) {}
    //a folder page's own list (data-url-tab) keeps its chosen tab in the address (?tab=), so
    //coming back to it (Save in an editor, a Move, a Delete, the browser's Back) opens the same
    //folder; the menus' links have no ?tab=, so a fresh visit still starts on All
    var urlTab = 'urlTab' in box.dataset ? new URLSearchParams(location.search).get('tab') : null;
    if (urlTab) chosen = urlTab;
    function keepInAddress() {
      if (!('urlTab' in box.dataset) || !window.history || !history.replaceState) return;
      var q = new URLSearchParams(location.search);
      if (chosen === 'all') q.delete('tab'); else q.set('tab', chosen);
      q.delete('show'); q.delete('moved');  // (lit up once, on arrival)
      var s = q.toString();
      history.replaceState(history.state, '', location.pathname + (s ? '?' + s : '') + location.hash);
      document.dispatchEvent(new CustomEvent('qgen-address'));  // the Back trail keeps the new address
    }
    //(a folder's own things, outside the folders inside it: 'self:<id>')
    function base() { return chosen.indexOf('self:') === 0 ? chosen.slice(5) : chosen; }
    function isFolder(id) { return /^\d+$/.test(id) && !!byId[id]; }
    if (chosen !== 'all' && chosen !== 'none' && !byId[base()]) chosen = 'all';
    if (chosen.indexOf('self:') === 0 && !isFolder(base())) chosen = 'all';
    if (chosen === 'none' && (!loose || 'noMain' in box.dataset || !tree.some(function (n) { return isFolder(String(n.id)); }))) chosen = 'all';
    //what's in a folder itself: in it, and in none of the folders inside it
    function own(n) {
      var out = {};
      Object.keys(n.keySet).forEach(function (k) {
        if (!n.children.some(function (c) { return c.keySet[k]; })) out[k] = 1;
      });
      return out;
    }

    function path() {  // the chosen folder and the folders it's in, from the top
      var out = [], id = base();
      while (id && byId[id]) { out.unshift(String(id)); id = parentOf[id]; }
      return out;
    }
    function tools(id) {
      var span = document.createElement('span');
      span.className = 'folder-filter-tools-now';
      //Expand all / Collapse all for what this folder shows (boxes.js shows them with two or
      //more boxes, and puts these first: the page's own pair steps aside meanwhile)
      var label = id === 'all' ? (box.dataset.allLabel || 'All') : id === null ? (box.dataset.mainLabel || 'Uncategorized') : byId[id].name;
      var pair = document.createElement('span');
      pair.className = 'level-buttons';
      [['open', 'Expand all', 'Open every one in \u201c'], ['close', 'Collapse all', 'Fold every one in \u201c']].forEach(function (b) {
        var btn = document.createElement('button');
        btn.type = 'button';
        //(on a card's filter bar, as tall as the bar's Clear: btn-sm)
        btn.className = 'btn btn-secondary ' + (box.dataset.toolsHome ? 'btn-sm' : 'btn-xs');
        btn.dataset.level = b[0];
        btn.dataset.levelOf = '#' + list.id;
        btn.dataset.levelPrefer = '';
        //(an icon button: its words in the tooltip and for screen readers)
        window.qgenIconButton(btn, b[0] === 'open' ? 'lc-expand' : 'lc-collapse', b[1], b[2] + label + '\u201d');
        btn.setAttribute('aria-label', b[1] + ' in ' + label);
        pair.appendChild(btn);
      });
      span.appendChild(pair);
      var t = box.querySelector('template.folder-filter-tools[data-for="' + id + '"]');
      if (t) span.appendChild(t.content.cloneNode(true));
      var n = byId[id], url = n ? n.url : id === null ? box.dataset.mainUrl : '';
      if (!url || !isFolder(String(id)) && id !== null) return span;
      var open = document.createElement('a');
      open.className = 'btn btn-secondary btn-xs';
      open.href = url;
      window.qgenIconButton(open, 'lc-folder-open', 'Open this folder', n ? 'Go into “' + n.name + '” to see just what’s in it' : 'See just what’s in no folder');
      span.appendChild(open);
      return span;
    }

    var tabs = null;
    function tabsBox() {
      if (!tabs) {
        tabs = document.createElement('div');
        tabs.className = 'folder-filter-rows folder-filter-tabs';
        box.insertBefore(tabs, list);
      }
      return tabs;
    }
    function draw() {
      rows.textContent = '';
      var p = path();
      //(experiment, data-style="list": the folders as a list down the side of the card, like the
      //folder list on a folder page, instead of rows of tabs)
      if (box.dataset.style === 'list') {
        rows.classList.add('folder-filter-side');
        //(the owner, 2026-10-13: the same piece as the folder list on the Problems page: its
        //Expand all / Collapse all on top, fold arrows on folders with folders inside, the same
        //rows; a click picks the folder here instead of opening a page)
        var col = document.createElement('div');
        col.className = 'folder-side-list';
        col.setAttribute('role', 'group');
        col.setAttribute('aria-label', 'Folders');
        var levels = document.createElement('div');
        levels.className = 'btn-row small side-levels';
        [['open', 'Expand all', 'Show the folders inside every folder in this list'],
         ['close', 'Collapse all', 'Hide the folders inside every folder (the one picked stays in view)']].forEach(function (l) {
          var lb = document.createElement('button');
          lb.type = 'button'; lb.className = 'btn btn-secondary btn-xs'; lb.dataset.sideLevel = l[0];
          window.qgenIconButton(lb, l[0] === 'open' ? 'lc-expand' : 'lc-collapse', l[1], l[2]);
          levels.appendChild(lb);
        });
        col.appendChild(levels);
        var FOLD = 'qgen-folded-' + (box.dataset.remember || 'pick'), folded = {};
        try { (JSON.parse(localStorage.getItem(FOLD) || '[]') || []).forEach(function (id) { folded[id] = true; }); } catch (err) {}
        function saveFold() { try { localStorage.setItem(FOLD, JSON.stringify(Object.keys(folded))); } catch (err) {} }
        var folds = [];
        function sideRow(btn, depth, node) {
          var r = document.createElement('div');
          r.className = 'side-row';
          r.dataset.depth = depth;
          if (depth > 1) r.style.paddingLeft = ((depth - 1) * 14) + 'px';  // (the side list's indents)
          var f;
          if (node && node.children.length) {
            f = document.createElement('button');
            f.type = 'button'; f.className = 'side-fold';
            f.setAttribute('aria-label', 'Show or hide the folders in ' + node.name);
            f.title = 'Show or hide the folders inside';
            folds.push({ row: r, id: String(node.id), btn: f });
          } else {
            f = document.createElement('span');
            f.className = 'side-fold-space'; f.setAttribute('aria-hidden', 'true');
          }
          r.appendChild(f);
          r.appendChild(btn);
          if (btn.classList.contains('is-empty')) r.classList.add('is-empty');
          col.appendChild(r);
          return r;
        }
        var allBtn = button('all', box.dataset.allLabel || 'All', items().length, 'folders');
        allBtn.classList.add('folder-tab-all');
        sideRow(allBtn, 1, null);
        (function walk(nodes, depth) {
          nodes.forEach(function (n) {
            sideRow(button(String(n.id), n.name, n.count, n.icon || 'folder'), depth, n);
            walk(n.children, depth + 1);
            //(no "Unsorted" line under a folder: every folder list looks like the side list on the
            //Problems page, the owner 2026-10-13; Unsorted is the tab inside an open folder)
          });
        })(tree, 1);
        var noneFolders = !tree.some(function (n) { return isFolder(String(n.id)); });
        var noneBtn = button('none', box.dataset.mainLabel || 'Uncategorized', noneFolders ? 0 : loose, 'tray');
        if (noneFolders) { noneBtn.disabled = true; noneBtn.title = 'There are no folders yet.'; }
        else if (!loose) { noneBtn.disabled = true; noneBtn.title = 'Everything is in a folder'; }
        sideRow(noneBtn, 1, null);
        //folding: the rows after a folder that are deeper belong to it; the folder picked (and the
        //folders it's in) always stay open
        var rowsAll = Array.prototype.slice.call(col.querySelectorAll('.side-row'));
        function inside(r) {
          var i = rowsAll.indexOf(r), d = +r.dataset.depth, out = [];
          for (var j = i + 1; j < rowsAll.length && +rowsAll[j].dataset.depth > d; j++) out.push(rowsAll[j]);
          return out;
        }
        function pickedInside(r) { return inside(r).some(function (x) { return x.querySelector('[aria-pressed="true"]'); }); }
        function drawFolds() {
          rowsAll.forEach(function (x) { x.hidden = false; });
          folds.forEach(function (fo) {
            var open = !folded[fo.id] || pickedInside(fo.row);
            fo.btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (!open) inside(fo.row).forEach(function (x) { x.hidden = true; });
          });
        }
        folds.forEach(function (fo) {
          fo.btn.addEventListener('click', function () {
            if (fo.btn.getAttribute('aria-expanded') === 'true') { if (pickedInside(fo.row)) return; folded[fo.id] = true; }
            else delete folded[fo.id];
            saveFold(); drawFolds();
          });
        });
        if (!folds.length) levels.querySelectorAll('button').forEach(function (lb) { lb.disabled = true; lb.title = lb.textContent.trim() + ': No folder here has folders inside it'; });
        else levels.addEventListener('click', function (e) {
          var lb = e.target.closest('[data-side-level]');
          if (!lb) return;
          folds.forEach(function (fo) { if (lb.dataset.sideLevel === 'open') delete folded[fo.id]; else folded[fo.id] = true; });
          saveFold(); drawFolds();
        });
        col.qgenFolds = drawFolds;
        rows.appendChild(col);
      }
      //(data-tabs on a list: the folder tabs over the list too, as on a folder page: a student's
      //page, the owner 2026-10-13)
      if (box.dataset.style !== 'list' || 'tabs' in box.dataset) {
        var host = box.dataset.style === 'list' ? tabsBox() : rows;
        host.textContent = '';
        //the top row: All, the folders, Uncategorized
        var row = document.createElement('div');
        row.className = 'folder-tabs';
        row.setAttribute('role', 'group');
        row.setAttribute('aria-label', 'Folders');
        var label = document.createElement('span');
        label.className = 'folder-tabs-label';
        label.textContent = 'Folders';
        row.appendChild(label);
        //(no folders at all, only New / In progress: nothing to sort yet, so it counts 0)
        var noFolders = !tree.some(function (n) { return isFolder(String(n.id)); });
        //(a folder's own page with no folders inside: its one tab, open, says the folder's name,
        //just for looks: the list sits under a tab like every other (the owner, 2026-10-15))
        //(My quizzes gives the name as data-tab-name: its empty folder has its own note)
        var plain = box.dataset.allUrl === '' && noFolders && (box.dataset.tabName || box.dataset.name);
        //(data-tab-icon: Uncategorized's tray, New's sparkle...: every open folder has its tab, the owner 2026-10-16)
        var allTab = button('all', plain || (box.dataset.allLabel || 'All'), items().length, plain ? (box.dataset.tabIcon || 'folder') : 'folders');
        allTab.classList.add('folder-tab-all');
        if (plain) { allTab.classList.add('folder-tab-name'); allTab.title = 'Everything in “' + plain + '”'; }
        row.appendChild(allTab);
        tree.forEach(function (n) { row.appendChild(button(String(n.id), n.name, n.count, n.icon || 'folder')); });
        var none = button('none', box.dataset.mainLabel || 'Uncategorized', 'noMain' in box.dataset || noFolders ? 0 : loose, 'tray');
        if ('noMain' in box.dataset) { none.disabled = true; none.title = 'There are no folders inside, so this is the same as ' + (box.dataset.allLabel || 'All'); }
        else if (noFolders) { none.disabled = true; none.title = 'There are no folders yet.'; }
        else if (!loose) { none.disabled = true; none.title = 'Everything is in a folder'; }
        row.appendChild(none);
        //(a folder's own page with no folders inside: no tabs, just its things, as above)
        if (box.dataset.allUrl === '' && noFolders) row.classList.add('folder-tabs-plain');
        //(a folder's own page, empty: just its folders' tabs, grayed, as in the folder list)
        else if (box.dataset.allUrl === '' && !items().length) { row.classList.add('folder-tabs-empty'); none.classList.add('folder-tab-self'); }
        host.appendChild(row);
        //a row for the folders inside each chosen folder
        p.forEach(function (id) {
          var n = byId[id];
          if (!isFolder(id)) return;  // (New, In progress: not folders)
          var sub = document.createElement('div');
          sub.className = 'folder-tabs folder-tabs-inner';
          sub.setAttribute('role', 'group');
          sub.setAttribute('aria-label', 'Folders in ' + n.name);
          //first, the folder itself ("All in “X”"): chosen while the list shows everything in it, so
          //the list never looks like it belongs to the folder beside it
          var whole = button(String(n.id), 'All', n.count, 'folders');
          whole.classList.add('folder-tab-all');
          whole.title = 'Show everything in “' + n.name + '” and the folders inside it';
          sub.appendChild(whole);
          n.children.forEach(function (c) { sub.appendChild(button(String(c.id), c.name, c.count, 'folder')); });
          //last, what's in the folder itself and in none of the folders inside it (like Uncategorized
          //at the top); grayed out when there are no folders inside, since it's the same as All in
          //(no folders inside: nothing is "left over", so it counts 0, not everything in the folder)
          var mine = n.children.length ? Object.keys(own(n)).length : 0;
          var self = button('self:' + n.id, 'Unsorted', mine, 'tray');
          self.classList.add('folder-tab-self');
          self.setAttribute('aria-label', 'Unsorted in “' + n.name + '”');
          if (!n.children.length) { self.disabled = true; self.title = 'There are no folders inside “' + n.name + '”, so this is the same as All'; }
          else self.title = 'Show what’s in “' + n.name + '” and in none of the folders inside it';
          sub.appendChild(self);
          //(an empty folder: its row of tabs is grayed, the chosen one too, so nothing in it catches
          //the eye; the folder's own tab above still shows where you are: the owner, 2026-10-14)
          if (!n.count) sub.classList.add('folder-tabs-empty');
          //(no folders inside it: All and Unsorted would be the same as what's shown, so no tabs,
          //just its things: the owner, 2026-10-14)
          if (!n.children.length) sub.classList.add('folder-tabs-plain');
          host.appendChild(sub);
        });
      }
      //which buttons are chosen: the folder and the ones it's in
      box.querySelectorAll('.folder-filter-rows .folder-tab').forEach(function (b) {
        var on = b.dataset.folder === chosen || (!b.classList.contains('folder-tab-all') && p.indexOf(b.dataset.folder) !== -1);
        if (b.classList.contains('folder-tab-self')) on = b.dataset.folder === chosen;
        if (b.closest('.folder-side-list')) on = b.dataset.folder === chosen;  // (a list: just the one chosen)
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
        b.setAttribute('aria-expanded', on ? 'true' : 'false');
      });
      //the chosen folder's own buttons at the end of the last row (All's too: every level has them)
      //(on a phone the rows scroll sideways, so they'd be out of sight: a line of their own under them)
      var t = tools(chosen === 'none' ? null : base());
      //a card that picks from the list (data-tools-home: its filter bar) keeps them at the end of
      //that bar's line, the same in every such card (Assign's Quiz and Students, the quiz builder)
      var home = box.dataset.toolsHome ? document.querySelector(box.dataset.toolsHome) : null;
      if (home) { home.querySelectorAll('.folder-filter-tools-here').forEach(function (old) { old.remove(); }); }
      if (t.childNodes.length && home) {
        var spot = document.createElement('span');
        spot.className = 'folder-filter-tools-here';
        spot.appendChild(t);
        home.appendChild(spot);
      } else if (t.childNodes.length) {
        var where = box.dataset.style === 'list' ? tabsBox() : rows;
        var row = where.lastElementChild;
        //(a folder with no folders inside has no tabs of its own: no empty row for it; its buttons
        //go at the end of the row above, like every other folder's: the owner, 2026-10-14)
        if (row.classList.contains('folder-tabs-plain') && row.previousElementSibling) {
          row.style.display = 'none';
          row = row.previousElementSibling;
        }
        //a phone: the buttons on a line of their own under the tabs; otherwise at the row's end,
        //unless the row is too long for its width (fitTools, once the page is laid out)
        if (narrow && narrow.matches) {
          var line = document.createElement('div');
          line.className = 'folder-tools-line';
          line.appendChild(t);
          where.appendChild(line);
        } else {
          row.appendChild(t);
          toolsAt = { t: t, row: row, where: where };
          setTimeout(fitTools, 0);
        }
      }
      //the chosen tabs in view (a phone's strip may be scrolled past them)
      box.querySelectorAll('.folder-filter-rows .folder-tab[aria-pressed="true"]').forEach(function (b) {
        var strip = b.parentElement;
        if (strip.scrollWidth > strip.clientWidth) strip.scrollLeft = Math.max(0, b.offsetLeft - strip.offsetLeft - 24);
      });
    }

    //the folder's buttons at the end of its row of tabs; a row too long for its width (measured
    //once the page is laid out, and again when it changes size) has them on a line of their own
    //under it, so they're never scrolled out of sight
    var toolsAt = null;

    //tabs wrapped on to several lines: a line under each line of tabs but the last (it has the
    //open folder's top edge), so no line of tabs floats (the owner, 2026-10-15)
    function lineRules(row) {
      row.querySelectorAll(':scope > .tab-line-rule').forEach(function (r) { r.remove(); });
      if (!row.offsetParent) return;
      var tabs = Array.prototype.filter.call(row.children, function (c) { return c.classList.contains('folder-tab') && c.offsetParent; });
      var bottoms = {};
      tabs.forEach(function (t) { var top = t.offsetTop; bottoms[top] = Math.max(bottoms[top] || 0, top + t.offsetHeight); });
      var tops = Object.keys(bottoms).map(Number).sort(function (a, b) { return a - b; });
      tops.slice(0, -1).forEach(function (top) {
        var r = document.createElement('div');
        r.className = 'tab-line-rule';
        r.setAttribute('aria-hidden', 'true');
        r.style.top = (bottoms[top] - 1) + 'px';
        row.appendChild(r);
      });
    }
    //tabs wrapped on to several lines: the open tab goes to the bottom line, at its left, right
    //over its folder (the owner, 2026-10-15); a row that fits keeps its order
    function pickedLineLast(row) {
      if (!row) return;
      row.querySelectorAll(':scope > .tab-break').forEach(function (b) { b.remove(); });
      var tabs = Array.prototype.filter.call(row.children, function (c) { return c.classList.contains('folder-tab') && c.offsetParent; });
      var picked = tabs.filter(function (t) { return t.getAttribute('aria-pressed') === 'true'; })[0];
      if (!picked) return;
      var tops = tabs.map(function (t) { return t.offsetTop; });
      var lastTop = Math.max.apply(null, tops), firstTop = Math.min.apply(null, tops);
      if (lastTop - firstTop < 3) return;  // (one line: as it is)
      //the bottom line's tabs (without the open one), in order: a break, then the open tab, then them
      var bottom = tabs.filter(function (t) { return t !== picked && Math.abs(t.offsetTop - lastTop) < 3; });
      var brk = document.createElement('span');
      brk.className = 'tab-break';
      brk.setAttribute('aria-hidden', 'true');
      if (bottom.length) {
        row.insertBefore(brk, bottom[0]);
        row.insertBefore(picked, bottom[0]);
      } else {
        var after = tabs[tabs.length - 1].nextSibling;
        row.insertBefore(brk, after);
        row.insertBefore(picked, after);
      }
      //(the open tab taken from an upper line can let the bottom line's first tab move up: then it
      //starts the bottom line on its own, which is fine)
    }
    function fitTools() {
      if (!toolsAt || (narrow && narrow.matches) || !toolsAt.t.isConnected) return;
      var t = toolsAt.t, row = toolsAt.row, line = t.parentElement.classList.contains('folder-tools-line') ? t.parentElement : null;
      if (line) { row.appendChild(t); line.remove(); }
      box.querySelectorAll('.folder-filter-rows > .folder-tabs').forEach(pickedLineLast);
      box.querySelectorAll('.folder-filter-rows > .folder-tabs').forEach(lineRules);
      if (row.scrollWidth > row.clientWidth + 1) {
        line = document.createElement('div');
        line.className = 'folder-tools-line';
        line.appendChild(t);
        toolsAt.where.appendChild(line);
      }
    }
    window.addEventListener('load', function () { fitTools(); });
    //the open folder on a list page: as tall as the window has room for, scrolling inside, so
    //the page itself stays put (the owner, 2026-10-17; not on phones, nor in a picker card or
    //dialog, nor a folder list inside another's)
    var scrolls = !box.dataset.toolsHome && (box.dataset.style !== 'list' || 'tabs' in box.dataset) && !box.closest('dialog') &&
      !(box.parentElement && box.parentElement.closest('.folder-filter-list'));
    function fitHeight() {
      if (!scrolls) return;
      list.classList.remove('folder-scroll');
      list.style.maxHeight = '';
      if ((narrow && narrow.matches) || list.hidden) return;
      var top = list.getBoundingClientRect().top + window.scrollY;
      //(down to the page's own bottom margin, so the page itself doesn't scroll)
      var main = box.closest('main'), gap = main ? parseFloat(getComputedStyle(main).paddingBottom) || 16 : 16;
      list.style.maxHeight = Math.max(240, window.innerHeight - top - gap - 1) + 'px';
      list.classList.add('folder-scroll');
      //(room for what comes under it on the page, Grading's oldest waiting: the page itself
      //still doesn't scroll)
      var over = document.documentElement.scrollHeight - window.innerHeight;
      if (over > 0) list.style.maxHeight = Math.max(240, parseFloat(list.style.maxHeight) - over) + 'px';
    }
    window.addEventListener('load', fitHeight);
    window.addEventListener('resize', fitHeight);
    //(the box's width changing without the window's: a side panel opening, the page laying out)
    if (window.ResizeObserver) {
      var lastW = 0;
      new ResizeObserver(function () {
        var w = box.getBoundingClientRect().width;
        if (Math.abs(w - lastW) < 1) return;
        lastW = w;
        clearTimeout(fitTools._t);
        fitTools._t = setTimeout(fitTools, 30);
      }).observe(box);
    }
    window.addEventListener('resize', function () {
      clearTimeout(fitTools._r);
      fitTools._r = setTimeout(fitTools, 150);
    });
    var narrow = window.matchMedia ? window.matchMedia('(max-width: 640px)') : null;
    if (narrow && narrow.addEventListener) narrow.addEventListener('change', function () { draw(); });

    function apply() {
      box.dataset.shown = chosen;
      var sideCol = rows.querySelector('.folder-side-list');
      if (sideCol && sideCol.qgenFolds) sideCol.qgenFolds();  // (the folder picked stays in view)  // (what's shown, for scripts: takeout.js's "the folder shown")
      var keep = chosen === 'all' || chosen === 'none' ? null : chosen.indexOf('self:') === 0 ? own(byId[base()]) : byId[chosen].keySet;
      items().forEach(function (el) {
        var k = keyOf(el), hide = chosen === 'none' ? !!inSome[k] : keep ? !keep[k] : false;
        window.qgenHideRow ? window.qgenHideRow(el, 'folder', hide) : (el.hidden = hide);
      });
      //a folder with nothing in it says so (what the name filter hides still counts as in it)
      var shown = items().some(function (el) { return (el.dataset.hiddenBy || '').split(' ').indexOf('folder') === -1; });
      var note = box.querySelector('.folder-filter-empty');
      if (!note) {
        note = document.createElement('p');
        note.className = 'card empty small folder-filter-empty';
        list.parentElement.insertBefore(note, list.nextSibling);
      }
      //(a folder's own page with nothing in it, only empty folders: All says so too)
      var bare = chosen === 'all' && !items().length && box.dataset.name !== undefined;
      note.hidden = shown || (chosen === 'all' && !bare);
      folderEmpty = !shown && (chosen !== 'all' || bare);
      //(an empty folder: its open panel turns gray, not the open folder's blue: the owner, 2026-10-14)
      box.classList.toggle('folder-open-empty', !items().some(function (el) { return (el.dataset.hiddenBy || '').split(' ').indexOf('folder') === -1; }));
      list.hidden = folderEmpty;  // (no empty frame above the note)
      var nm = byId[base()] ? byId[base()].name : '';
      //(a tab can bring its own words for when it's empty: 'empty' in its data)
      note.textContent = bare ? 'Nothing in \u201c' + box.dataset.name + '\u201d yet.' : byId[chosen] && byId[chosen].empty ? byId[chosen].empty : chosen === 'none' ? 'Everything is in a folder.' : chosen.indexOf('self:') === 0 ? 'Everything in \u201c' + nm + '\u201d is in a folder inside it.' : 'Nothing in \u201c' + nm + '\u201d yet.';
      //(how to fill an empty folder, where the page says (My quizzes): the owner, 2026-10-16)
      if (box.dataset.emptyHint && (bare || /^\d+$/.test(chosen)) && /yet\.$/.test(note.textContent)) note.textContent += ' ' + box.dataset.emptyHint;
      tidy();
      setTimeout(fitHeight, 0);
      document.querySelectorAll('[data-filter-bar]').forEach(function (bar) { if (bar.qgenRun) bar.qgenRun(); });
      if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();
    }

    //a table whose rows are all hidden (by a tab or the name filter) goes, heading and all; while
    //a filter matches nothing here, the empty frame goes too (the filter bar says so)
    var folderEmpty = false, filtering = false;
    function tidy() {
      list.querySelectorAll('table').forEach(function (t) {
        var rowsIn = t.querySelectorAll('tbody tr[data-box], tbody tr[data-fkey]');
        if (rowsIn.length) t.hidden = Array.prototype.every.call(rowsIn, function (r) { return r.hidden; });
      });
      list.hidden = folderEmpty || (filtering && !items().some(function (el) { return !el.hidden; }));
      //what's shown changed (a folder chosen, a filter typed): e.g. Assign keeps its chosen quiz in sight
      box.dispatchEvent(new CustomEvent('qgen-shown', { bubbles: true }));
    }
    document.addEventListener('qgen-filtered', function (e) {
      //(only the filter over this list: Messages has another, for the message's students)
      var bar = e.target.closest && e.target.closest('[data-filter-bar]'), over = bar && document.querySelector(bar.dataset.filter);
      if (!over || !(over.contains(list) || box.contains(over))) return;
      filtering = !!(e.detail && e.detail.active);
      tidy();
    });

    //(the folder list down the side, and the tabs over the list: data-tabs)
    var lastClick = null;
    //a double-click told by the two presses (the first click redraws the tabs, so the second
    //click can be lost): the second press on the same spot within 600ms opens the tab pressed
    //first (the owner, 2026-10-16: All too)
    var lastDown = null, pendingPick = null, leaving = false;
    //a tab picked by a click shows as picked at once, but the tabs are redrawn (the open one moved
    //to the bottom line) only a moment later, after a double-click would have come: a double-click
    //then opens the folder's own page without the tabs jumping first (the owner, 2026-10-16)
    function pickSoon(id, tabEl) {
      clearTimeout(pendingPick);
      if (tabEl && tabEl.setAttribute) {
        box.querySelectorAll('.folder-filter-rows .folder-tab[aria-pressed="true"]').forEach(function (o) { if (o.closest('.folder-tabs') === tabEl.closest('.folder-tabs')) o.setAttribute('aria-pressed', 'false'); });
        tabEl.setAttribute('aria-pressed', 'true');
      }
      pendingPick = setTimeout(function () { pendingPick = null; if (!leaving) choose(id); }, 300);
    }
    box.addEventListener('pointerdown', function (e) {
      var rowsHit = e.target.closest('.folder-filter-rows');
      if (e.button || !rowsHit || rowsHit.parentElement !== box) { lastDown = null; return; }
      var t = e.target.closest('.folder-tab'), now = Date.now();
      if (lastDown && now - lastDown.t < 600 && Math.abs(e.clientX - lastDown.x) < 8 && Math.abs(e.clientY - lastDown.y) < 8) {
        var id0 = lastDown.id;
        lastDown = null;
        var url0 = byId[id0] && byId[id0].url ? byId[id0].url : id0 === 'none' ? box.dataset.mainUrl : id0 === 'all' ? (box.dataset.allOwnUrl || box.dataset.allUrl) : '';
        if (url0) { var to0 = new URL(url0, location.href); if (to0.pathname === location.pathname && to0.search === location.search) url0 = ''; }
        if (url0) { e.preventDefault(); clearTimeout(pendingPick); leaving = true; rememberBack(url0, id0); location.href = url0; }
        return;
      }
      lastDown = t && !t.disabled ? { id: t.dataset.folder, t: now, x: e.clientX, y: e.clientY } : null;
    });
    box.addEventListener('click', function (e) {
      var b = e.target.closest('.folder-tab');
      //(a double-click whose first click moved the tab away, to the bottom line: the second
      //lands beside it, and still opens the tab first clicked)
      var rowsHit = e.target.closest('.folder-filter-rows');
      //(a second click on the same spot within 600ms is a double-click, even when the first one
      //redrew the tabs and the browser started counting again)
      var again = lastClick && Date.now() - lastClick.t < 600 && Math.abs(e.clientX - lastClick.x) < 8 && Math.abs(e.clientY - lastClick.y) < 8;
      if (!b && rowsHit && rowsHit.parentElement === box && again) b = { dataset: { folder: lastClick.id }, classList: { contains: function () { return false; } }, closest: function () { return rowsHit; } };
      if (leaving) return;
      if (!b || b.disabled || !b.closest('.folder-filter-rows') || b.closest('.folder-filter-rows').parentElement !== box) return;
      var id = b.dataset.folder;
      //double-click a folder's tab: go into that folder (its own page, like "Open this folder");
      //Uncategorized's too (the owner, 2026-10-15). (Counted here, not by dblclick: the first
      //click can move the tab, to the bottom line, so the second lands on another one.)
      var now = Date.now(), first = again || (lastClick && e.detail >= 2 && now - lastClick.t < 600) ? lastClick.id : null;
      lastClick = first ? null : { id: id, t: now, x: e.clientX, y: e.clientY };
      if (first) {
        //(the automatic ones too, New and In progress on My quizzes, and All: each opens its own
        //page, the owner 2026-10-16; never the page that's open already)
        var url = byId[first] && byId[first].url ? byId[first].url : first === 'none' ? box.dataset.mainUrl : first === 'all' ? (box.dataset.allOwnUrl || box.dataset.allUrl) : '';
        if (url) { var to = new URL(url, location.href); if (to.pathname === location.pathname && to.search === location.search) url = ''; }
        if (url) { clearTimeout(pendingPick); leaving = true; rememberBack(url, first); location.href = url; return; }
      }
      if (b.closest('.folder-side-list')) { choose(id); return; }
      if (b.classList.contains('folder-tab-all') || b.classList.contains('folder-tab-self')) { pickSoon(id, b); return; }
      //pressing the open folder's tab again keeps it open (the owner, 2026-10-15: no going back
      //up a level by clicking it twice)
      if (id === chosen) return;
      pickSoon(id, b);
    });
    //the folder list down the side picks the same folders here, in place (no new page)
    function same(a, url) { if (!url) return false; var u = new URL(url, location.href); return a.pathname === u.pathname && a.search === u.search; }
    function sideFor(a) {
      if (same(a, box.dataset.allUrl)) return 'all';
      if (same(a, box.dataset.mainUrl)) return loose ? 'none' : null;
      for (var id in byId) if (byId[id].url && same(a, byId[id].url)) return id;  // (folders, and New / In progress)
      return null;
    }
    function markSide() {
      //(phones: the folded folder list's line names what's open)
      var now = document.querySelector('.folder-side-now');
      if (now && 'urlTab' in box.dataset) now.textContent = chosen === 'all' ? (box.dataset.allLabel || 'All') : chosen === 'none' ? (box.dataset.mainLabel || 'Uncategorized') : chosen.indexOf('self:') === 0 ? byId[base()].name + ': Unsorted' : byId[chosen] ? byId[chosen].name : now.textContent;
      document.querySelectorAll('.side-row a[href]').forEach(function (a) {
        var id = sideFor(a);
        if (id === null) return;
        var on = id === base();
        a.closest('.side-row').classList.toggle('current', on);
        if (on && window.qgenSideReveal) window.qgenSideReveal(id);
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
    //the page's heading names what's shown: the folder chosen (the All label to begin with)
    //(opened on another tab, e.g. My quizzes' New from Home: the server's heading is that tab's,
    //so All gets the All label)
    var heading = document.getElementById('folder-title'), startedOnAll = !box.dataset.start || box.dataset.start === 'all';
    var headingWas = heading && startedOnAll ? heading.innerHTML : '';
    //(the owner, 2026-10-14: the heading names the folder chosen, by its tab or the side list,
    //with its whole path from the top: "Science › physics"; "Uncategorized"; a folder's own
    //Unsorted: "Science › Unsorted"; All: the page's own name, "People" or "Quizzes". On a
    //folder's own page the path starts with its own (the server's heading).)
    var headingOwn = heading ? heading.innerHTML : '';
    function retitle() {
      if (!heading) return;
      var inner = box.dataset.allUrl === '';  // (a folder's own page: its inner tabs)
      //(the owner, 2026-10-15) the open folder's name with its path from the top: "Math › Fractions";
      //a folder's own things: "Math › Unsorted"; Uncategorized as is; All: the page's name. On a
      //folder's own page the path starts with that folder's own (the server's heading)
      function pageName() {
        if (heading.dataset.pageName) heading.textContent = heading.dataset.pageName;
        else if (headingWas) heading.innerHTML = headingWas;
        else heading.textContent = box.dataset.allLabel || 'All';
      }
      if (chosen === 'all') { if (inner) heading.innerHTML = headingOwn; else pageName(); return; }
      if (chosen === 'none' && !inner) { heading.textContent = box.dataset.mainLabel || 'Uncategorized'; return; }
      //(My quizzes' New and In progress aren't folders: opened on one, the server's heading says
      //what it shows, "New: quizzes you haven't started"; chosen afterward, the tab's name)
      if (chosen !== 'none' && !isFolder(base())) {
        if (chosen === box.dataset.start && headingOwn) heading.innerHTML = headingOwn;
        else heading.textContent = byId[chosen] ? byId[chosen].name : heading.textContent;
        return;
      }
      var names = chosen === 'none' ? [] : path().map(function (id) { return byId[id].name; });
      if (chosen === 'none' || chosen.indexOf('self:') === 0) names.push(box.dataset.mainLabel && inner ? box.dataset.mainLabel : 'Unsorted');
      var text = names.join(' \u203a ');
      if (inner) { heading.innerHTML = headingOwn; heading.appendChild(document.createTextNode(' \u203a ' + text)); return; }
      heading.innerHTML = window.qgenIcon ? window.qgenIcon('folder') + ' ' : '';
      heading.appendChild(document.createTextNode(text));
    }
    function choose(id) {
      chosen = id;
      try { sessionStorage.setItem(memKey, chosen); } catch (err) {}
      keepInAddress();
      draw();
      apply();
      markSide();
      retitle();
    }
    draw();
    apply();
    //what was just saved (?show=, lit up) is in another folder than the tab kept in the address:
    //open All, so it's in sight
    var saved = list.querySelector('[data-show]');
    if (saved && chosen !== 'all' && (saved.hidden || saved.closest('[hidden]'))) { choose('all'); saved.scrollIntoView({ block: 'center' }); }
    markSide();
    retitle();
  }
  function all() { document.querySelectorAll('[data-folder-filter]').forEach(setUp); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', all); else all();
})();

/* Folder options on a folder tab: the tab row scrolls sideways, which would cut its pop-up off at
 * the row's edge, so there it's placed against the window instead (just under its button), and
 * follows its button when the page or the row scrolls */
(function () {
  function place(d) {
    var box = d.querySelector('.folder-tools-box');
    if (!box) return;
    if (!d.open) { box.style.position = box.style.top = box.style.right = box.style.left = ''; return; }
    var r = d.querySelector('summary').getBoundingClientRect();
    box.style.position = 'fixed';
    box.style.top = (r.bottom + 6) + 'px';
    box.style.right = Math.max(16, window.innerWidth - r.right) + 'px';
    box.style.left = 'auto';
  }
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (d.matches && d.matches('details.folder-tools') && d.closest('.folder-tabs')) place(d);
  }, true);
  function again() { document.querySelectorAll('.folder-tabs details.folder-tools[open]').forEach(place); }
  window.addEventListener('scroll', again, { passive: true, capture: true });
  window.addEventListener('resize', again);
})();

/* the folder's heading (and its buttons) goes in the middle of the bar under it, between the
   filter and the checked bar, where there's room (the owner, 2026-10-15) */
(function () {
  var head = document.querySelector('.folder-main > .folder-title-row');
  var bar = document.querySelector('.folder-main .folder-tools-bar');
  if (!head || !bar) return;
  var filter = bar.querySelector('.filter-bar');
  head.classList.add('in-tools-bar');
  if (filter && filter.parentElement === bar) bar.insertBefore(head, filter.nextSibling);
  else bar.insertBefore(head, bar.firstChild);
})();

/* A folder's own page opened from a folder page (a tab double-clicked, an "Open this folder"
   icon): a Back icon beside its Up goes back to the page and tab it was opened from (the owner,
   2026-10-15). Kept for this browser tab (sessionStorage) while that folder's page is open. */
var BACK_KEY = 'qgen-folder-back';
function folderOf(url) { try { var u = new URL(url, location.href); return u.pathname + '?folder=' + (u.searchParams.get('folder') || ''); } catch (e) { return ''; } }
function rememberBack(url, id) {
  //(what was showing, as its heading said: "Math › Fractions", "Problems"; a tab's own name,
  //"All", said too little: the owner 2026-10-15)
  var heading = document.getElementById('folder-title');
  var name = heading ? heading.textContent.replace(/\s+/g, ' ').trim() : '';
  try { sessionStorage.setItem(BACK_KEY, JSON.stringify({ to: folderOf(url), from: location.pathname + location.search, name: name })); } catch (e) {}
}
(function () {
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a.btn-icon[href*="folder="]');
    if (a && /^Open this folder/.test(a.title || '')) rememberBack(a.getAttribute('href'));
  });
  var b = null;
  try { b = JSON.parse(sessionStorage.getItem(BACK_KEY) || 'null'); } catch (e) {}
  if (!b || b.to !== folderOf(location.href)) return;
  document.querySelectorAll('.folder-up').forEach(function (up) {
    if (!up.offsetParent) return;  // (only beside the Up that shows)
    var a = document.createElement('a');
    a.className = up.className.replace('folder-up', 'folder-back');
    a.href = b.from;
    var words = 'Back';
    a.innerHTML = (window.qgenIcon ? window.qgenIcon('lc-arrow-left') : '') + '<span class="sr-only">' + words + '</span>';
    a.title = 'Back: return to ' + (b.name ? '“' + b.name + '”' : 'where you were');
    a.addEventListener('click', function () { try { sessionStorage.removeItem(BACK_KEY); } catch (e) {} });
    //(the leftmost of its group: before Expand all / Collapse all and Up, the owner 2026-10-15)
    up.parentNode.insertBefore(a, up.parentNode.firstChild);
  });
})();
