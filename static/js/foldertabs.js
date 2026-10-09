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
      b.setAttribute('aria-expanded', d.open && !searching ? 'true' : 'false');
    });
  }
  //one open at a time: keep the given one (or the first open one), close the others
  function only(row, keep) {
    var open = boxesIn(row).filter(function (d) { return d.open; });
    keep = keep || open[0];
    open.forEach(function (d) { if (d !== keep) d.open = false; });
  }

  //where the folders end and this folder's own things begin: a heading over them ("Problems in
  //“Arithmetic” itself"), when there are any after the folders
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
    var head = document.createElement('h3');
    head.className = 'folder-items-head';
    head.textContent = units.charAt(0).toUpperCase() + units.slice(1) + (name ? ' in \u201c' + name + '\u201d itself' : ' here');
    last.parentElement.insertBefore(head, next);
  }

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
        //the heading's icon, name, count and badges (a heading can't go in a button: its text instead)
        Array.prototype.forEach.call(head.childNodes, function (c) {
          if (c.nodeType === 1 && c.classList.contains('fold')) return;
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
          if (row.classList.contains('tabs-off')) return;
          var opening = !box.open;
          if (opening) only(row, box);
          box.open = opening;
        });
        box.qgenTab = b;
        row.appendChild(b);  // in the boxes' order
        box.addEventListener('toggle', function () {
          if (box.open && !row.classList.contains('tabs-off')) only(row, box);
          sync(row);
        });
      });
      only(row);
      sync(row);
    });
    if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();  // Expand all / Collapse all: only where there's still something to open
  }

  //while a filter is typed: plain boxes (every folder with a match open), then the row again
  document.addEventListener('qgen-filtered', function (e) {
    var on = !!(e.detail && e.detail.active);
    document.querySelectorAll('.folder-tabs').forEach(function (row) {
      row.classList.toggle('tabs-off', on);
      row.parentElement.classList.toggle('tabs-searching', on);
      if (!on) only(row);
      sync(row);
    });
    if (window.qgenBoxes && window.qgenBoxes.levels) window.qgenBoxes.levels();
  });

  setUp(document);
  //parts drawn later
  if (window.MutationObserver) new MutationObserver(function () { clearTimeout(setUp._t); setUp._t = setTimeout(function () { setUp(document); }, 50); })
    .observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
  window.qgenFolderTabs = { refresh: function () { document.querySelectorAll('.folder-tabs').forEach(sync); } };
})();
