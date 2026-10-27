/* A folder list (static/js/folderfilter.js): everything in one list, each thing once, narrowed to
 * one folder (with the folders inside it) at a time. Folder pages (data-onetab, _folders.html) pick
 * the folder in the page's own folder list beside it; pickers in cards and dialogs (data-style="list")
 * draw their own folder list down the side. Either way one tab over the list names the folder that's
 * open ("7th Grade › AT"), with its buttons after it; the rows' Expand all / Collapse all sits in the
 * list's heading row. The choice is kept in the address (?tab=, data-url-tab) or for the tab. Works
 * with the name filter: each hides with its own flag (filter.js). (The single folder model: the
 * owner, 2026-10-22; the rows of folder tabs and their code went 2026-10-23.) */
(function () {
  var uid = 0;
  function setUp(box, early) {
    if (box.qgenFolderFilter) { if (!early && box.qgenAfterRows) box.qgenAfterRows(); return; }
    box.qgenFolderFilter = true;
    //(its listeners on the whole page, kept so they go when the box is swapped for a new one: folders.js calls
    //box.qgenTearDown first; they piled up, one set for each drop, the code critic 2026-10-25)
    var offs = [];
    function onDoc(type, fn) { document.addEventListener(type, fn); offs.push([type, fn]); }
    box.qgenTearDown = function () { offs.forEach(function (o) { document.removeEventListener(o[0], o[1]); }); offs = []; };
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
    //the Checked folder: an automatic one, first after All, holding whatever is checked in this list
    //right now, kept up to date as boxes are checked and unchecked (the owner, 2026-10-21); on every
    //list with check boxes, a folder page's or a picker's
    var checkedNode = byId.checked = { id: 'checked', name: 'Checked', children: [], keys: [], keySet: {}, count: 0, icon: 'lc-folder-check' };
    parentOf.checked = null;
    //(a list of round buttons can have its Checked folder too, showing the one picked, when it asks for
    //it with data-checked-radios: the Assign page's Quiz card, the owner 2026-10-22)
    var TICK = '.tick-col input[type="checkbox"]' + ('checkedRadios' in box.dataset ? ', .tick-col input[type="radio"]' : '');
    function tickOf(el) { return (el.closest('tr') || el).querySelector(TICK); }
    function hasChecks() { return !!list.querySelector(TICK); }

    function items() {
      return Array.prototype.filter.call(list.querySelectorAll('[' + sel + '^="' + prefix + '"]'), function (el) {
        return el.parentElement.closest('[' + sel + '^="' + prefix + '"]') === null;  // the things themselves, not parts of them
      });
    }
    var inSome = {};
    tree.forEach(function (n) { if (typeof n.id === 'number') n.keys.forEach(function (k) { inSome[k] = 1; }); });  // (New, In progress: not folders)
    //(drawn early, as soon as the list starts arriving: the counts the rows would give come from the
    //server, data-total and data-loose, so the tabs show at once instead of after a long list has
    //all arrived, a second on Problems; the owner, 2026-10-21)
    var known = early && box.dataset.total !== undefined;
    //(a list shown a page at a time has only its page's rows: the counts come from the server then too, data-total and data-loose)
    var serverCounts = 'paged' in box.dataset && box.dataset.total !== undefined && box.dataset.loose !== undefined;
    function allCount() { return known || serverCounts ? +box.dataset.total : weigh(items()); }
    var loose = known || serverCounts ? +box.dataset.loose : weigh(items().filter(function (el) { return !inSome[keyOf(el)]; }));
    //(what the counts count: the things, or e.g. Grading's attempts waiting, data-count-unit, each
    //thing then weighing its data-weight: the owner, 2026-10-19)
    var cUnit = box.dataset.countUnit || unit, cUnits = box.dataset.countUnits || units;
    function count(n) { return n + ' ' + (n === 1 ? cUnit : cUnits); }
    function weigh(els) { return els.reduce(function (t, el) { return t + (el.dataset.weight ? +el.dataset.weight : 1); }, 0); }

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
      //(no "(double-click: open this folder)" any more: double-click to open went site-wide on
      //2026-10-21, "Open this folder" is the icon at the open tab's row's end; the owner, 2026-10-22)
      //(nothing in it: grayed, and it still opens, saying it's empty, from a tab as from the folder
      //list, on every page: the owner, 2026-10-21; it didn't open from a tab, 2026-10-14)
      if (!n && id !== 'all') {
        b.classList.add('is-empty');
        var kids = byId[id] && byId[id].children;
        if (!(kids && kids.length)) b.title = 'Nothing in “' + label + '” yet';
      }
      if ('droppable' in box.dataset && id !== 'all' && (id === 'none' || /^\d+$/.test(id))) b.dataset.drop = id === 'none' ? 'top' : id;
      return b;
    }

    //the page starts on All; only coming back to it from itself (a button here that reloads it,
    //e.g. a move or a drop) keeps the folder that was chosen
    //(data-start: the tab an address asks for, e.g. My quizzes?folder=new from Home)
    var chosen = box.dataset.start || 'all';
    //(the folder last open here, however the page is reached, the menu too: every page keeps its
    //state, the owner 2026-10-21; it used to be only when coming from this same page)
    try { if (!box.dataset.start) chosen = sessionStorage.getItem(memKey) || 'all'; } catch (e) {}
    //a folder page's own list (data-url-tab) keeps its chosen tab in the address (?tab=), so
    //coming back to it (Save in an editor, a Move, a Delete, the browser's Back) opens the same
    //folder, whatever was open last
    var urlTab = 'urlTab' in box.dataset ? new URLSearchParams(location.search).get('tab') : null;
    if (urlTab) chosen = urlTab;
    //a list shown a page at a time (data-paged, app/paging.py; the owner, 2026-10-23): the server sent just the
    //folder shown (the side list's folders are links to their own pages), so there's nothing to narrow
    //here, and only the Checked folder (?checked=, data-start) is ever "chosen"
    var paged = 'paged' in box.dataset;
    if (paged) chosen = box.dataset.serverView || (box.dataset.start === 'checked' ? 'checked' : 'all');
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
    //(an old "Unsorted in …" choice, from before the single folder model: All)
    if (chosen.indexOf('self:') === 0) chosen = 'all';
    //(Uncategorized opens whenever something is in it, folders or not: the owner, 2026-10-20)
    if (chosen === 'none' && (!loose || 'noMain' in box.dataset)) chosen = 'all';
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
      //(only where the rows open and close: a picker's rows never do, so it would do nothing; the
      //owner, 2026-10-21, and 2026-10-23: the quiz editor's Problems card had one)
      if (list.querySelector('details.box')) span.appendChild(pair);
      //(the Checked folder's header: "Apply to checked (N)", on the page's own list)
      if (id === 'checked' && ownList() && window.qgenApplyChecked) span.appendChild(window.qgenApplyChecked);
      var t = box.querySelector('template.folder-filter-tools[data-for="' + id + '"]');
      if (t) span.appendChild(t.content.cloneNode(true));
      return span;
    }

    //a list whose things carry a score (data-score: a quiz's history, each student's score that counts):
    //each folder tab shows the average of the scores in it, beside its count (the owner, 2026-10-21)
    function averages() {
      var scored = items().filter(function (el) { return el.dataset.score !== undefined && el.dataset.score !== ''; });
      if (!scored.length) return;
      box.querySelectorAll('.folder-tab').forEach(function (t) {
        var id = t.dataset.folder;
        if (id === undefined) return;
        var keep = id === 'all' ? null : id === 'none' ? 'none' : id.indexOf('self:') === 0 ? own(byId[id.slice(5)]) : byId[id] ? byId[id].keySet : null;
        if (keep === null && id !== 'all') return;
        var vals = scored.filter(function (el) { var k = keyOf(el); return keep === null ? true : keep === 'none' ? !inSome[k] : !!keep[k]; })
          .map(function (el) { return +el.dataset.score; });
        var old = t.querySelector('.tab-average');
        if (old) old.remove();
        if (!vals.length) return;
        var avg = vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
        var b = document.createElement('span');
        //(green, amber or red as the Score colors say, like every score badge: app/tuning.py score_class)
        var cut = scored[0].closest('[data-score-green]'), green = cut ? +cut.dataset.scoreGreen : 0, amber = cut ? +cut.dataset.scoreAmber : 0;
        b.className = 'badge tab-average ' + (avg >= green ? 'badge-ok' : avg >= amber ? 'badge-warn' : 'badge-bad');
        b.textContent = 'Average ' + Math.round(avg) + '%';
        b.title = 'The average of the scores that count, for the ' + vals.length + ' ' + (vals.length === 1 ? 'student' : 'students') + ' here with one';
        var c = t.querySelector('.box-count');
        if (c) c.after(b); else t.appendChild(b);
      });
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
        //(a heading over the folder list, "Folders", with its Expand all / Collapse all beside it, level
        //with the tab over the list: the same on every folder list, the owner 2026-10-22; it was beside
        //the card's heading, then on the filter line)
        if (box.qgenSideLevels && box.qgenSideLevels.isConnected) box.qgenSideLevels.remove();
        var sideHead = box.querySelector(':scope > .side-list-head');
        if (!sideHead) {
          sideHead = document.createElement('div');
          sideHead.className = 'side-list-head';
          var shl = document.createElement('span');
          shl.className = 'side-list-title';
          shl.textContent = 'Folders';
          sideHead.appendChild(shl);
          box.insertBefore(sideHead, rows);
        }
        levels.qgenScope = col;
        levels.classList.add('title-levels');
        sideHead.appendChild(levels);
        box.qgenSideLevels = levels;
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
        var allBtn = button('all', box.dataset.allLabel || 'All', allCount(), 'folders');
        allBtn.classList.add('folder-tab-all');
        sideRow(allBtn, 1, null).classList.add('side-auto');
        //(the automatic folders a page brings in its tree (a student's New and In progress: ids that aren't a folder's
        //number) go right after All, pinned above the line with the others, never among the folders: the owner, 2026-10-26)
        var autoNodes = tree.filter(function (n) { return !/^\d+$/.test(String(n.id)); });
        autoNodes.forEach(function (n) { sideRow(button(String(n.id), n.name, n.count, n.icon || 'folder'), 1, n).classList.add('side-auto'); });
        if (hasChecks()) sideRow(button('checked', checkedNode.name, checkedNode.count, checkedNode.icon), 1, null).classList.add('side-auto');
        //(the automatic folders pinned at the top, in one order: All, Checked, Uncategorized; the folders
        //scroll under them: the owner, 2026-10-21)
        //(grayed only when nothing is in it: with no folders yet it holds everything, and opens, the
        //owner 2026-10-20; it was grayed then, 2026-10-19)
        //(left out when empty on a page that hides empty folders: a history, the owner 2026-10-22)
        if ((loose || !('hideEmpty' in box.dataset)) && !('noSideMain' in box.dataset)) {
          var noneBtn = button('none', box.dataset.mainLabel || 'Uncategorized', loose, 'tray');
          if (!loose) { noneBtn.disabled = true; noneBtn.title = 'Everything is in a folder'; }
          sideRow(noneBtn, 1, null).classList.add('side-auto');
        }
        (function walk(nodes, depth) {
          nodes.forEach(function (n) {
            sideRow(button(String(n.id), n.name, n.count, n.icon || 'folder'), depth, n);
            walk(n.children, depth + 1);
            //(no "Unsorted" line under a folder: every folder list looks like the side list on the
            //Problems page, the owner 2026-10-13; Unsorted is the tab inside an open folder)
          });
        })(tree.filter(function (n) { return autoNodes.indexOf(n) === -1; }), 1);
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
        if (!folds.length) levels.querySelectorAll('button').forEach(function (lb) { lb.disabled = true; var w = lb.textContent.trim() || ((lb.querySelector('svg[aria-label]') || {}).getAttribute ? lb.querySelector('svg[aria-label]').getAttribute('aria-label') : ''); lb.title = w + ': No folder here has folders inside it'; /* (an icon's words are on its drawing) */ });
        else levels.addEventListener('click', function (e) {
          var lb = e.target.closest('[data-side-level]');
          if (!lb) return;
          folds.forEach(function (fo) { if (lb.dataset.sideLevel === 'open') delete folded[fo.id]; else folded[fo.id] = true; });
          saveFold(); drawFolds();
        });
        col.qgenFolds = drawFolds;
        rows.appendChild(col);
        setTimeout(function () { window.qgenPinAuto(col); }, 0);
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
      //(its Expand all / Collapse all right after the open tab, beside the folder's name; the other
      //buttons stay at the row's end: the owner, 2026-10-19)
      //(the one tab's row: last time's buttons and lines out, the tab stays)
      if ('onetab' in box.dataset) {
        var ow = oneWrap();
        Array.prototype.slice.call(ow.querySelectorAll(':scope > .folder-tabs > :not(.folder-tab-name), :scope > .folder-tools-line')).forEach(function (el) { el.remove(); });
      }
      box.qgenTabPair = null;
      {
        var lp = t.querySelector('.level-buttons');
        if (lp) { lp.remove(); lp.classList.add('tab-level-pair'); box.qgenTabPair = lp; placeTabPair(); }
      }
      //a card that picks from the list (data-tools-home: its filter bar) keeps them at the end of
      //that bar's line, the same in every such card (Assign's Quiz and Students, the quiz builder)
      var home = box.dataset.toolsHome ? document.querySelector(box.dataset.toolsHome) : null;
      if (home) { home.querySelectorAll('.folder-filter-tools-here').forEach(function (old) { old.remove(); }); }
      //(a card whose buttons go on its filter bar makes no row for them: a side list's empty row
      //would take the list's place beside it)
      var where = home ? null : oneWrap();
      var row = where && where.lastElementChild;
      toolsAt = null;
      if (t.childNodes.length && home) {
        var spot = document.createElement('span');
        spot.className = 'folder-filter-tools-here';
        spot.appendChild(t);
        home.appendChild(spot);
      } else if (t.childNodes.length && row) {
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
        }
      }
      //(the open tab to the bottom line, its pair beside it, and the lines under wrapped rows, once laid out)
      if (!home) setTimeout(fitTools, 0);
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
    function placeTabPair() {
      var lp = box.qgenTabPair;
      if (!lp) return;
      //(a side list's one tab over the list: the pair right after the tab, on every list, with check boxes or
      //without (the owner, 2026-10-24; from 2026-10-22 a list with check boxes had it in its heading row)
      var one = box.querySelector(':scope > .folder-filter-onetab > .folder-tabs');
      if (one) {
        var to = one;
        //(last time's pair out: the cell outlives the redraws)
        box.querySelectorAll('.tab-level-pair').forEach(function (old) { if (old !== lp) old.remove(); });
        if (lp.parentNode !== to) to.appendChild(lp);
        return;
      }
    }

    function fitTools() {
      if (narrow && narrow.matches) return;
      var here = toolsAt && toolsAt.t.isConnected;
      var t = here && toolsAt.t, row = here && toolsAt.row, line = here && t.parentElement.classList.contains('folder-tools-line') ? t.parentElement : null;
      if (line) { row.appendChild(t); line.remove(); }
      placeTabPair();
      //(too long for the row, or wrapped on to a line of its own under the tabs: that line would sit
      //between the open tab and its folder, breaking their edge, so it's the line under the row,
      //part of the open folder: the owner, 2026-10-21)
      var openTab = here && row.querySelector(':scope > .folder-tab[aria-pressed="true"]');
      var wrapped = here && openTab && t.offsetTop > openTab.offsetTop + openTab.offsetHeight - 4;
      //(the Checked folder's, "Apply to checked", always on that line inside the folder, at its top
      //right, whatever the width: the owner, 2026-10-22, it moved between the tab row and here)
      if (here && (row.scrollWidth > row.clientWidth + 1 || wrapped || chosen === 'checked')) {
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
      box.dataset.chosen = chosen;  // (for the styles: the Checked folder's rows not indented, the owner 2026-10-22)
      recount();
      box.dataset.shown = chosen;
      var sideCol = rows.querySelector('.folder-side-list');
      if (sideCol && sideCol.qgenFolds) sideCol.qgenFolds();  // (the folder picked stays in view)  // (what's shown, for scripts: takeout.js's "the folder shown")
      var keep = paged || chosen === 'all' || chosen === 'none' ? null : chosen.indexOf('self:') === 0 ? own(byId[base()]) : byId[chosen].keySet;
      //(a list a page at a time shows the Checked folder the server sent, ?checked=: a row unchecked there leaves it at
      //once, and the address forgets it, so a reload doesn't bring it back; the owner, 2026-10-24)
      var unchecked = paged && chosen === 'checked' ? function (el) {
        var t = el.querySelector('input[name="items"], input.pick-person');
        return !!t && !t.checked;
      } : null;
      items().forEach(function (el) {
        var k = keyOf(el), hide = unchecked ? unchecked(el) : paged ? false : chosen === 'none' ? !!inSome[k] : keep ? !keep[k] : false;
        window.qgenHideRow ? window.qgenHideRow(el, 'folder', hide) : (el.hidden = hide);
      });
      if (unchecked && window.qgenCheckedIds) {
        var addr = new URL(location.href), ids = window.qgenCheckedIds().join(',');
        if ((addr.searchParams.get('checked') || '') !== ids) {
          addr.searchParams.set('checked', ids);
          try { history.replaceState(history.state, '', addr.pathname + addr.search.replace(/%2C/g, ',') + addr.hash); } catch (err) {}
        }
      }
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
      //(a folder with nothing loose in it but things in the folders inside it says so, not "Nothing in it yet": a folder
      //shows only its own things since 2026-10-25; the code critic, 2026-10-26)
      var holdsInside = function (n) { return !!n && n.children.some(function (c) { return Object.keys(c.keySet).length || holdsInside(c); }); };
      note.textContent = bare ? 'Nothing in \u201c' + box.dataset.name + '\u201d yet.' : byId[chosen] && byId[chosen].empty ? byId[chosen].empty : chosen === 'none' ? 'Everything is in a folder.' : (chosen.indexOf('self:') === 0 || holdsInside(byId[chosen])) ? 'Everything in \u201c' + nm + '\u201d is in a folder inside it.' : 'Nothing in \u201c' + nm + '\u201d yet.';
      //(how to fill an empty folder, where the page says (My quizzes): the owner, 2026-10-16)
      if (box.dataset.emptyHint && (bare || /^\d+$/.test(chosen)) && /yet\.$/.test(note.textContent)) note.textContent += ' ' + box.dataset.emptyHint;
      oneTab();
      averages();
      tidy();
      setTimeout(fitHeight, 0);
      document.querySelectorAll('[data-filter-bar]').forEach(function (bar) { if (bar.qgenRun) bar.qgenRun(); });
      if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();
    }

    //a folder list down the side (and no row of tabs over the list): one tab over the list naming
    //the folder it shows, joined to it, like the open tab on every folder page (the owner,
    //2026-10-19). A label, not a button: the folder is picked in the list beside it.
    function oneWrap() {
      var wrap = box.querySelector(':scope > .folder-filter-onetab');
      if (!wrap) {
        wrap = document.createElement('div');
        wrap.className = 'folder-filter-rows folder-filter-onetab';
        wrap.appendChild(document.createElement('div')).className = 'folder-tabs';
        box.insertBefore(wrap, list);
        box.classList.add('has-onetab');
      }
      return wrap;
    }
    function oneTab() {
      if ((box.dataset.style !== 'list' && !('onetab' in box.dataset)) || 'tabs' in box.dataset) return;
      var wrap = oneWrap();
      var n = byId[base()], self = chosen.indexOf('self:') === 0;
      //(a folder's own page: its All is the folder itself, named)
      var own = box.dataset.allUrl === '' && (box.dataset.tabName || box.dataset.name);
      var label = chosen === 'all' ? (own || box.dataset.allLabel || 'All') : chosen === 'none' ? (box.dataset.mainLabel || 'Uncategorized')
        : self ? 'Unsorted in \u201c' + (n ? n.name : '') + '\u201d'
        //(a folder inside others: its whole path, "7th Grade › AT", so the same name in two places
        //can't be mixed up: the owner, 2026-10-22)
        : n ? path().filter(function (id) { return isFolder(id); }).map(function (id) { return byId[id].name; }).join(' \u203a ') || n.name : chosen;
      var parts = label.split(' \u203a ');
      var icon = chosen === 'all' ? (own ? (box.dataset.tabIcon || 'folder') : 'folders') : chosen === 'none' || self ? 'tray' : (n && n.icon) || 'folder';
      //(what shows: a name typed in the filter counts too, "All people 2": the owner, 2026-10-22)
      //(the Checked folder of a list a page at a time: what's still checked, not the server's count from when it was sent)
      var shown = paged && chosen === 'checked' && window.qgenCheckedIds ? window.qgenCheckedIds().length
        : paged && box.dataset.shownTotal !== undefined ? +box.dataset.shownTotal : weigh(items().filter(function (el) { return !el.hidden; }));
      var tab = document.createElement('span');
      tab.className = 'folder-tab folder-tab-name';
      tab.setAttribute('aria-pressed', 'true');
      tab.dataset.folder = chosen;  // (which folder it names: e.g. the quiz builder counts what's checked in it)
      if (window.qgenIcon) tab.insertAdjacentHTML('beforeend', window.qgenIcon(icon));
      var nm = document.createElement('span'); nm.className = 'box-title'; nm.textContent = label; tab.appendChild(nm);
      var c = document.createElement('span'); c.className = 'badge box-count'; c.textContent = shown; c.title = count(shown); tab.appendChild(c);
      tab.title = label;
      var row = wrap.firstElementChild;
      //(a paged list's page controls, at the right end of this row)
      var pagerTop = box.querySelector(':scope > .pager-top');
      if (pagerTop && pagerTop.parentNode !== row) row.appendChild(pagerTop);
      //("Check all 57": every match on every page, where the list has check boxes; again to uncheck them)
      var allBtn = box.querySelector('[data-check-all-folder]');
      if (allBtn) {
        allBtn.closest('label').hidden = !hasChecks() || !window.qgenCheckMany;
        if (!allBtn.qgenWired) {
          allBtn.qgenWired = true;
          var pairs = [];
          try { pairs = JSON.parse(allBtn.dataset.keys || '[]'); } catch (err) {}
          //(checked when every one is checked, half-checked when some are, like the heading row's box)
          var sync = function () {
            var some = window.qgenCheckedIds ? pairs.filter(function (p) { return window.qgenCheckedIds().indexOf(String(p[0])) !== -1; }).length : 0;
            allBtn.checked = pairs.length > 0 && some === pairs.length;
            allBtn.indeterminate = some > 0 && some < pairs.length;
            var words = allBtn.closest('label').querySelector('[data-check-words]');
            if (words) words.textContent = (allBtn.checked ? 'Uncheck all ' : 'Check all ') + pairs.length;
            allBtn.setAttribute('aria-label', (allBtn.checked ? 'Uncheck all ' : 'Check all ') + pairs.length + ' in this folder');
          };
          allBtn.addEventListener('change', function () { window.qgenCheckMany(pairs, allBtn.checked); });
          onDoc('qgen-checked', sync);
          sync();
        }
      }
      //(only the tab itself replaced: the open folder's buttons after it stay)
      var old = row.querySelector(':scope > .folder-tab-name');
      if (old) row.replaceChild(tab, old); else row.insertBefore(tab, row.firstChild);
      if (box.qgenTabPair) placeTabPair();
      fitName(nm, parts);
      oneTab.fit = function () { fitName(nm, parts); };
    }
    //(a name too long for its tab loses its start, never its end: "… › Dans Workbook1 1", the folder
    //that's open always in sight; the owner, 2026-10-22)
    function fitName(nm, parts) {
      nm.textContent = parts.join(' \u203a ');
      if (!nm.offsetParent || nm.scrollWidth <= nm.clientWidth + 1) return;
      for (var k = 1; k < parts.length; k++) {
        nm.textContent = '\u2026 \u203a ' + parts.slice(k).join(' \u203a ');
        if (nm.scrollWidth <= nm.clientWidth + 1) return;
      }
      //(the open folder's own name still too long: its end kept)
      //(one "…" only, at the start: "…Workbook1 1")
      var last = parts[parts.length - 1];
      for (var c = parts.length > 1 ? 0 : 1; c < last.length; c++) {
        nm.textContent = '\u2026' + last.slice(c);
        if (nm.scrollWidth <= nm.clientWidth + 1) return;
      }
    }
    window.addEventListener('resize', function () { if (oneTab.fit) oneTab.fit(); });

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
    onDoc('qgen-filtered', function (e) {
      //(only the filter over this list: Messages has another, for the message's students)
      var bar = e.target.closest && e.target.closest('[data-filter-bar]'), over = bar && document.querySelector(bar.dataset.filter);
      if (!over || !(over.contains(list) || box.contains(over))) return;
      filtering = !!(e.detail && e.detail.active);
      tidy();
      oneTab();
    });

    //(the folder list down the side, and the tabs over the list: data-tabs)
    //(a click on a folder in the side list picks it, in place; the one tab over the list is only a
    //label. No rows of tabs, no double-click any more: the owner, 2026-10-23)
    box.addEventListener('click', function (e) {
      var b = e.target.closest('.folder-tab');
      if (!b || b.disabled || !b.closest('.folder-side-list') || b.closest('.folder-filter') !== box) return;
      //(a paged list's folders are other pages: the server sends the folder asked for, from its first page)
      if (paged) {
        var u = new URL(location.href), f = b.dataset.folder;
        u.searchParams.set('folder', f === 'none' ? 'main' : f);
        ['page', 'q', 'tab', 'show', 'moved'].forEach(function (k) { u.searchParams.delete(k); });
        location.assign(u.pathname + u.search + u.hash);
        return;
      }
      choose(b.dataset.folder);
    });
    //the folder list down the side picks the same folders here, in place (no new page)
    function same(a, url) { if (!url) return false; var u = new URL(url, location.href); return a.pathname === u.pathname && a.search === u.search; }
    function sideFor(a) {
      if (a.dataset.sideTab) return a.dataset.sideTab;  // (the Checked folder's row)
      if (same(a, box.dataset.allUrl)) return 'all';
      if (same(a, box.dataset.mainUrl)) return loose ? 'none' : null;
      for (var id in byId) if (byId[id].url && same(a, byId[id].url)) return id;  // (folders, and New / In progress)
      return null;
    }
    function markSide() {
      //(only the page's own list, the one in the address: never a picker's in a dialog or a card)
      if (!ownList()) return;
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
        if (on) centerSide(a.closest('.side-row'));
      });
      //(a list shown a page at a time, or a folder's own named box, has no tree to match the side list against: the
      //server marked the folder open, so the folders above it unfold and it's brought into the middle of the list;
      //the owner, 2026-10-25: the tab said one folder and the list showed another place)
      if (paged || !Object.keys(byId).length) {
        var cur = document.querySelector('.folder-side .side-row.current');
        var li = cur && cur.closest('.side-item');
        if (li && window.qgenSideReveal) window.qgenSideReveal(li.dataset.folder);
        if (cur) centerSide(cur);
      }
    }
    //the folder open now sits in the middle of the folder list, by its tab or the list (the owner,
    //2026-10-20); only the list scrolls, never the page
    function centerSide(row) {
      var sc = row.closest('.side-scroll');
      if (!sc || sc.scrollHeight <= sc.clientHeight + 1) return;
      var r = row.getBoundingClientRect(), c = sc.getBoundingClientRect();
      sc.scrollTop += (r.top + r.height / 2) - (c.top + sc.clientHeight / 2);
    }
    onDoc('click', function (e) {
      var a = e.target.closest && e.target.closest('.side-row a[href]');
      if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var id = sideFor(a);
      if (id === null) return;
      e.preventDefault();
      //(a paged list asks the server for what's checked, in every folder and on every page)
      if (paged && id === 'checked') {
        var u = new URLSearchParams(location.search), keep = new URLSearchParams();
        if (u.get('section')) keep.set('section', u.get('section'));
        keep.set('checked', (window.qgenCheckedIds ? window.qgenCheckedIds() : []).join(','));
        location.assign(location.pathname + '?' + keep.toString().replace(/%2C/g, ','));
        return;
      }
      if (paged) return;
      choose(id);
    });
    //the page's heading names what's shown: the folder chosen (the All label to begin with)
    //(opened on another tab, e.g. My quizzes' New from Home: the server's heading is that tab's,
    //so All gets the All label)
    //(only the page's own list names the heading over it; never a picker's, in a dialog or a card)
    var heading = box.closest('.folder-main') ? document.getElementById('folder-title') : null, startedOnAll = !box.dataset.start || box.dataset.start === 'all';
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
      //(All: its own name, "All quizzes", like every other folder; not the page's name, which is over
      //the folder list already: the owner, 2026-10-21)
      function pageName() {
        if (box.dataset.allLabel) heading.textContent = box.dataset.allLabel;
        else if (heading.dataset.pageName) heading.textContent = heading.dataset.pageName;
        else if (headingWas) heading.innerHTML = headingWas;
        else heading.textContent = 'All';
      }
      if (chosen === 'all') { if (inner) heading.innerHTML = headingOwn; else pageName(); return; }
      //(the Checked folder, also when the page opens on it: "Checked", never the server's "All quizzes"; the owner, 2026-10-24)
      if (chosen === 'checked') { heading.textContent = byId.checked ? byId.checked.name : 'Checked'; return; }
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
    //what's checked now: the Checked folder's things and its count, wherever it's shown
    function recount() {
      var ks = {}, n = 0, before = Object.keys(checkedNode.keySet).join(' ');
      items().forEach(function (el) { var t = tickOf(el); if (t && t.checked && !t.disabled) {  // (a grayed check box, e.g. a folder it's already in, isn't a pick)
        ks[keyOf(el)] = 1; n += el.dataset.weight ? +el.dataset.weight : 1; } });
      //(a paged list: everything checked, on every page and in every folder, is what the Checked folder holds)
      if (paged && window.qgenCheckedIds) n = window.qgenCheckedIds().length;
      checkedNode.keySet = ks; checkedNode.count = n;
      box.querySelectorAll('.folder-tab[data-folder="checked"]').forEach(function (b) {
        var c = b.querySelector('.box-count');
        if (c) { c.textContent = n; c.title = count(n); c.dataset.n = n; }
        b.classList.toggle('is-empty', !n);
        b.title = n ? 'Show what’s in “Checked”' : 'Nothing in “Checked” yet';
        //(green while anything is checked, to catch the eye: the owner, 2026-10-23)
        var r = b.closest('.side-row'); if (r) { r.classList.toggle('is-empty', !n); r.classList.toggle('has-checked', !!n); }
      });
      if (sideLink) {
        sideLink.closest('.side-row').classList.toggle('is-empty', !n);
        sideLink.closest('.side-row').classList.toggle('has-checked', !!n);
        sideLink.parentNode.querySelector('.side-count').textContent = n;
      }
      //(and small, beside the folder list's Expand all / Collapse all by the page's title: the owner, 2026-10-21)
      if (ownList() && hasChecks()) {
        //(beside the page's title, where the folder list's pair used to be: 2026-10-23)
        var pair = document.querySelector('main .page-head > h1');
        //(the list swapped in after a drop finds the one already beside the title, not a second one: the owner, 2026-10-26)
        if (pair && !titleCount && pair.parentNode.querySelector(':scope > .title-checked')) {
          titleCount = pair.parentNode.querySelector(':scope > .title-checked');
          titleCount.replaceWith(titleCount = titleCount.cloneNode(false));
          titleCount.addEventListener('click', function () { if (chosen !== 'checked') choose('checked'); });
        }
        if (pair && !titleCount) {
          //(a button: it opens the Checked folder, the owner 2026-10-21)
          titleCount = document.createElement('button');
          titleCount.type = 'button';
          titleCount.className = 'badge box-count title-checked';
          titleCount.addEventListener('click', function () { if (chosen !== 'checked') choose('checked'); });
          pair.parentNode.insertBefore(titleCount, pair.nextSibling);
        }
        if (titleCount) {
          //(a check mark before the number, like a tab's icon before its count: the owner, 2026-10-21)
          titleCount.innerHTML = window.qgenIcon ? window.qgenIcon('lc-check') : '\u2713';
          titleCount.appendChild(document.createTextNode(String(n)));
          titleCount.title = n + ' checked';
          titleCount.classList.toggle('is-empty', !n);
        }
      }
      return Object.keys(ks).join(' ') !== before;
    }
    //(a folder page's own folder list: the Checked folder's row right under All)
    var sideLink = null, titleCount = null;
    //(the page's own list: in the address, or the one list of a page with no folders yet, Other files)
    function ownList() { return 'urlTab' in box.dataset || !!(box.closest('.folder-main') && !box.closest('dialog')); }
    function sideChecked() {
      if (sideLink || !ownList() || !hasChecks()) return;
      var top = document.querySelector('.folder-side .side-top > li');
      if (!top) return;
      //(the side list stays when the list is swapped in after a drop: its Checked row is there already, so it's used
      //again, not added twice; the owner, 2026-10-26)
      var had = top.parentNode.querySelector(':scope > li.side-auto a[data-side-tab="checked"]');
      if (had) { sideLink = had; return; }
      var li = document.createElement('li');
      li.className = 'side-auto';
      li.innerHTML = '<div class="side-row"><span class="side-fold-space" aria-hidden="true"></span><a class="side-link" data-side-tab="checked"></a><span class="side-count muted small"></span></div>';
      sideLink = li.querySelector('a');
      sideLink.href = location.pathname + '?tab=checked';
      sideLink.title = 'See what’s checked';
      sideLink.innerHTML = (window.qgenIcon ? window.qgenIcon(checkedNode.icon) : '') + ' ';
      sideLink.appendChild(document.createTextNode(checkedNode.name));
      //(the automatic folders' order, pinned at the top: All, New, In progress, Checked, Uncategorized)
      var unc = top.parentNode.querySelector(':scope > li[data-auto="none"]');
      top.parentNode.insertBefore(li, unc || top.nextSibling);
      if (window.qgenPinAuto) window.qgenPinAuto(top.parentNode);
    }
    function soon() {
      clearTimeout(soon.t);
      soon.t = setTimeout(function () { if (recount() && chosen === 'checked') apply(); }, 0);
    }
    //(checking a box, Check all, a chip's ✕, a dialog's Check all shown: all end in a click or a change)
    box.addEventListener('change', soon);
    onDoc('click', soon);
    onDoc('qgen-checked', soon);
    //("Apply to checked" made after the Checked folder was first drawn: drawn again with it)
    onDoc('qgen-apply-ready', function () { if (chosen === 'checked') apply(); });
    function choose(id) {
      chosen = id;
      try { sessionStorage.setItem(memKey, chosen); } catch (err) {}
      keepInAddress();
      draw();
      apply();
      markSide();
      retitle();
    }
    //(for a list whose rows a script changes in place: a folder dialog's round buttons turned into
    //check boxes by "Copy instead" (the Checked folder comes and goes with them), and opening it
    //again on All; static/js/dialogfilter.js, the owner 2026-10-22)
    box.qgenRedraw = function () { draw(); apply(); };
    box.qgenChoose = choose;
    draw();
    //(drawn early: what's shown is sorted out once every row has arrived, the list kept out of
    //sight meanwhile unless everything shows anyway)
    function afterRows() {
      box.qgenAfterRows = null;
      known = false;
      sideChecked();
      if (hasChecks() && !box.querySelector('.folder-tab[data-folder="checked"]')) draw();
      apply();
      list.style.visibility = '';
      //what was just saved (?show=, lit up) is in another folder than the tab kept in the address:
      //open All, so it's in sight
      var saved = list.querySelector('[data-show]');
      if (saved && chosen !== 'all' && (saved.hidden || saved.closest('[hidden]'))) { choose('all'); saved.scrollIntoView({ block: 'center' }); }
      markSide();
      retitle();
    }
    if (early) {
      if (chosen !== 'all') list.style.visibility = 'hidden';
      markSide();
      retitle();
      box.qgenAfterRows = afterRows;
    } else afterRows();
  }
  //(called from the page as soon as a list starts arriving: _folders.html)
  //(only where the server gave the counts, data-total: elsewhere, e.g. Grading's attempts, the tabs
  //wait for the rows as before)
  window.qgenFolderFilterEarly = function (box) { if (box && box.dataset.total !== undefined) setUp(box, true); };
  //(a list a script builds later: the folder dialogs' pickers, static/js/dialogfilter.js; the owner, 2026-10-22)
  window.qgenFolderFilterSetUp = function (box) { setUp(box); };
  //(setUp(box), never forEach(setUp): forEach's index would come in as `early` and leave every list
  //after the first waiting for rows that are already there)
  function all() { document.querySelectorAll('[data-folder-filter]').forEach(function (box) { setUp(box); }); }
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


/* The automatic folders (All, My quizzes' New and In progress, Checked, Uncategorized) stay pinned
   at the top of every folder list, a page's and a picker's; the folders scroll under them (the
   owner, 2026-10-21). Each pinned row sticks at its own place, measured from the first. */
window.qgenPinAuto = function (list) {
  if (!list) return;
  //(measured again whenever the list's size changes: a dialog's list is drawn while the dialog is
  //closed, and measures nothing until it opens; a folder folding open or shut moves nothing pinned)
  if (!list.qgenPinWatch && window.ResizeObserver) {
    list.qgenPinWatch = new ResizeObserver(function () { window.qgenPinAuto(list); });
    list.qgenPinWatch.observe(list);
  }
  var pinned = Array.prototype.filter.call(list.children, function (el) { return el.classList.contains('side-auto') && !el.hidden; });
  list.querySelectorAll(':scope > .side-auto-last, :scope > .side-auto-first').forEach(function (el) { el.classList.remove('side-auto-last', 'side-auto-first'); });
  if (!pinned.length || !pinned[0].offsetParent) return;
  //(the first marked here, not by CSS's first-of-type: a picker's side list has other things before it,
  //and the cover over its top was missing there, the folders showing through: the owner, 2026-10-22)
  pinned[0].classList.add('side-auto-first');
  var first = pinned[0].offsetTop;
  pinned.forEach(function (el) { el.style.top = (el.offsetTop - first) + 'px'; });
  pinned[pinned.length - 1].classList.add('side-auto-last');
};
(function () {
  function all() { document.querySelectorAll('.folder-side .side-top').forEach(window.qgenPinAuto); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', all); else all();
  window.addEventListener('load', all);
  window.addEventListener('resize', function () { clearTimeout(all.t); all.t = setTimeout(function () { all(); document.querySelectorAll('.folder-side-list').forEach(window.qgenPinAuto); }, 100); });
})();
