/* Folders on top, what's in them below: wherever folder boxes sit side by side (the All
 * views, a folder's own folders, the student page's quiz folders), their headings become one
 * row of folder buttons, and the open folder's contents show under the whole row. So a
 * folder is never listed below another folder's problems, quizzes or people. One folder in a
 * row is open at a time; pressing the open one again closes it. Inside a folder its own
 * folders come first, the same way, then its own things.
 *
 * The boxes themselves stay (<details class="sub-box">, hidden heading), so everything that
 * works on them still does: remembering what was open (boxes.js, keep.js), dragging onto a
 * folder (the button takes its data-drop), "just moved" opening one. While a filter is
 * typed, the row steps aside and every folder with a match shows as a box with its heading,
 * as before; clearing it brings the row back. Without this script the boxes show as boxes. */
(function () {
  var TABBED = 'details.sub-box[data-sub], details.sub-box[data-folder-box]';
  var n = 0;

  function boxesIn(row) {
    return Array.prototype.filter.call(row.parentElement.children, function (el) {
      return el.matches && el.matches(TABBED) && el.qgenRow === row;
    });
  }
  function sync(row) {
    var searching = row.classList.contains('tabs-off');
    boxesIn(row).forEach(function (d) {
      var b = d.qgenTab;
      b.hidden = d.hidden;  // a folder the page hid (e.g. nothing in it for this search)
      //its Expand all / Collapse all: at the row's end while it's the open folder button; back on
      //its own heading while the folders show as boxes (searching, or after Expand all)
      var pair = d.qgenPair;
      if (pair) {
        var head = d.querySelector(':scope > summary');
        if (searching && pair.parentElement !== head) head.appendChild(pair);
        else if (!searching && pair.parentElement === head) pairsOf(row).appendChild(pair);
        pair.hidden = searching ? false : !(d.open && !d.hidden);
      }
      b.setAttribute('aria-expanded', d.open && !searching ? 'true' : 'false');
    });
  }
  //the row's right end: the open folder's Expand all / Collapse all
  function pairsOf(row) {
    if (!row.qgenPairs) {
      row.qgenPairs = document.createElement('span');
      row.qgenPairs.className = 'tab-pairs';
      row.appendChild(row.qgenPairs);
    }
    return row.qgenPairs;
  }
  //one open at a time: keep the given one (or the first open one), close the others
  function only(row, keep) {
    var open = boxesIn(row).filter(function (d) { return d.open; });
    keep = keep || open[0];
    open.forEach(function (d) { if (d !== keep) d.open = false; });
  }

  //where the folders end and this folder's own things begin: a heading over them ("Problems in
  //“Arithmetic”: Unsorted"), when there are any after the folders
  function itemsHead(row, group) {
    var last = group[group.length - 1], next = last.nextElementSibling;
    while (next && (next.hidden || next.matches('script, input[type=hidden]'))) next = next.nextElementSibling;
    if (!next || next.classList.contains('folder-items-head')) return;
    var units = (row.closest('[data-units]') || {}).dataset;
    units = units && units.units ? units.units : 'things';
    var owner = row.parentElement.closest('details.sub-box'), name = null;
    if (owner) {
      var t = owner.querySelector(':scope > summary .box-title');
      name = t && t.textContent.trim();
    } else {
      var title = document.getElementById('folder-title');
      name = title && title.textContent.trim();
    }
    var head = document.createElement('div'), h = document.createElement('h3');
    head.className = 'folder-items-head';
    h.className = 'folder-items-title';
    h.textContent = units.charAt(0).toUpperCase() + units.slice(1) + (name ? ' in \u201c' + name + '\u201d: Unsorted' : ' here');
    head.appendChild(h);
    //Expand all / Collapse all for just these things (not the folders above): boxes.js
    var what = h.textContent.charAt(0).toLowerCase() + h.textContent.slice(1);
    var pair = document.createElement('span');
    pair.className = 'level-buttons';
    [['open', 'Expand all', 'Open every one of the '], ['close', 'Collapse all', 'Fold every one of the ']].forEach(function (b) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-xs';
      btn.dataset.level = b[0];
      btn.dataset.levelItems = '';
      btn.textContent = b[1];
      btn.setAttribute('aria-label', b[1] + ' ' + what);
      btn.title = b[2] + what;
      pair.appendChild(btn);
    });
    head.appendChild(pair);
    last.parentElement.insertBefore(head, next);
  }

  //(the one-list folder tabs of folderfilter.js have the same class; they're not ours)
  function ours(row) { return !row.closest('.folder-filter-rows'); }
  function setUp(scope) {
    (scope || document).querySelectorAll(TABBED).forEach(function (d) {
      if (d.qgenRow) return;
      var parent = d.parentElement;
      var group = Array.prototype.filter.call(parent.children, function (el) { return el.matches && el.matches(TABBED); });
      var row = group[0].qgenRow;
      if (!row) {
        row = document.createElement('div');
        row.className = 'folder-tabs';
        row.setAttribute('role', 'group');
        row.setAttribute('aria-label', 'Folders');
        //a band of its own that says what it is, so a folder button never reads as a heading
        //for the things below it
        var label = document.createElement('span');
        label.className = 'folder-tabs-label';
        label.textContent = group.length === 1 ? 'Folder' : 'Folders';
        row.appendChild(label);
        parent.insertBefore(row, group[0]);
        parent.classList.add('has-folder-tabs');
        itemsHead(row, group);
      }
      group.forEach(function (box) {
        if (box.qgenRow) return;
        box.qgenRow = row;
        box.classList.add('tab-box');
        if (!box.id) box.id = 'folder-panel-' + (++n);
        var head = box.querySelector(':scope > summary');
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'folder-tab';
        b.setAttribute('aria-controls', box.id);
        //the heading's icon, name, count and badges (a heading can't go in a button: its text instead);
        //its Expand all / Collapse all (boxes.js) goes to the end of the row, shown while it's open
        Array.prototype.slice.call(head.childNodes).forEach(function (c) {
          if (c.nodeType === 1 && c.classList.contains('fold')) return;
          if (c.nodeType === 1 && c.classList.contains('head-pair')) {
            c.classList.add('tab-pair');
            c.hidden = !box.open;
            box.qgenPair = c;
            pairsOf(row).appendChild(c);
            return;
          }
          var copy = c.cloneNode(true);
          if (copy.nodeType === 1 && /^H\d$/.test(copy.tagName)) {
            var span = document.createElement('span');
            span.className = copy.className;
            span.textContent = copy.textContent;
            copy = span;
          }
          b.appendChild(copy);
        });
        var title = head.querySelector('.box-title');
        b.title = (title ? 'Show what’s in “' + title.textContent.trim() + '”' : 'Show this folder') + ' (press again to close it)';
        if (head.hasAttribute('data-drop')) b.setAttribute('data-drop', head.getAttribute('data-drop'));
        b.addEventListener('click', function () {
          if (row.classList.contains('tabs-off')) return;  // (hidden then anyway)
          var opening = !box.open;
          if (opening) only(row, box);
          box.open = opening;
        });
        box.qgenTab = b;
        row.insertBefore(b, row.qgenPairs || null);  // in the boxes' order, before the pairs
        box.addEventListener('toggle', function () {
          if (box.open && !row.classList.contains('tabs-off')) only(row, box);
          sync(row);
        });
      });
      //several remembered open (only Expand all does that): back as it was left, all shown
      if (boxesIn(row).filter(function (d) { return d.open; }).length > 1) { row.qgenExpanded = true; aside(row); }
      else { only(row); sync(row); }
    });
    //inside a folder shown expanded, a row whose folders are all open was expanded too (a row
    //of one folder can't tell by itself)
    document.querySelectorAll('.folder-tabs:not(.tabs-off)').forEach(function (row) {
      if (!ours(row)) return;
      var up = row.parentElement.closest('details.tab-box');
      var boxes = boxesIn(row);
      if (up && up.qgenRow && up.qgenRow.qgenExpanded && boxes.length && boxes.every(function (d) { return d.open; })) {
        row.qgenExpanded = true;
        aside(row);
      }
    });
    if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();  // Expand all / Collapse all: only where there's still something to open
  }

  //while a filter is typed: plain boxes (every folder with a match open), then the row again
  //(the row also steps aside after Expand all, below: either one keeps it aside)
  function aside(row) {
    var off = !!(row.qgenSearching || row.qgenExpanded);
    row.classList.toggle('tabs-off', off);
    row.parentElement.classList.toggle('tabs-searching', off);
    if (!off) only(row);
    sync(row);
  }
  document.addEventListener('qgen-filtered', function (e) {
    var on = !!(e.detail && e.detail.active);
    document.querySelectorAll('.folder-tabs').forEach(function (row) { if (ours(row)) { row.qgenSearching = on; aside(row); } });
    if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();
  });

  //Expand all: every folder open at once, as boxes with their headings (one button row can only
  //show one); Collapse all: all closed, and the row of buttons again. The rows step aside before
  //boxes.js opens or closes the boxes (this runs first), so it opens and remembers them too.
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-level]');
    if (!btn || 'levelItems' in btn.dataset) return;  // (a folder's own things only: no folder rows)
    var level = btn.dataset.levelOf ? document.querySelector(btn.dataset.levelOf) : btn.closest('.level');
    if (!level) return;
    var rows = Array.prototype.slice.call(level.querySelectorAll('.folder-tabs')).filter(ours);
    if (!rows.length) return;
    if (btn.dataset.level === 'open') {
      rows.forEach(function (row) { row.qgenExpanded = true; aside(row); });
    } else {
      rows.forEach(function (row) { row.qgenExpanded = true; aside(row); });  // so boxes.js closes them all...
      setTimeout(function () {  // ...then the buttons again
        rows.forEach(function (row) { row.qgenExpanded = false; aside(row); });
        if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();
      }, 0);
    }
  }, true);

  setUp(document);
  //parts drawn later
  if (window.MutationObserver) new MutationObserver(function () { clearTimeout(setUp._t); setUp._t = setTimeout(function () { setUp(document); }, 50); })
    .observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
  window.qgenFolderTabs = { refresh: function () { document.querySelectorAll('.folder-tabs').forEach(function (row) { if (ours(row)) sync(row); }); } };
})();
