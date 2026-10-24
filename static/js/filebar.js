/* The checked bar's folder buttons (Put in folder, Take out of folder; the Archive's Move)
 * each open a small dialog to choose the folder, like Add to a quiz (the owner, 2026-10-15):
 * the bar's folder list moves into the dialog (still part of the bar's form), and the dialog's
 * own button sends the form as the bar's button did (so static/js/takeout.js still asks
 * first when something would leave its last folder). */
(function () {
  var form = document.getElementById('file-form');
  var sel = form && form.querySelector('select');
  if (!sel) return;
  var buttons = Array.prototype.filter.call(form.querySelectorAll('button'), function (b) { return b.type === 'submit'; });
  if (!buttons.length) return;
  var label = form.querySelector('label[for="' + sel.id + '"]');
  var unitEl = document.querySelector('[data-unit][data-units]');
  var unit = unitEl ? unitEl.dataset.unit : 'one', units = unitEl ? unitEl.dataset.units : 'ones';

  var dialog = document.createElement('dialog');
  //(it looks and works like a row's Move dialog: the folders as a list to choose from, never a
  //drop-down: the owner, 2026-10-20; the bar's list stays hidden in it, only to be sent)
  //(laid out like the Assign dialogs, 820px wide, the standard picker with its side folder list:
  //the owner, 2026-10-22; static/js/dialogfilter.js)
  dialog.className = 'ask ask-many assign-many pick-dialog put-dialog move-dialog';
  dialog.id = 'folder-dialog';
  //(a short line under the title; what moving does is in the amber "What happens:" box, as in the
  //Assign dialogs: the owner, 2026-10-22, it was a gray line under the title)
  dialog.innerHTML = '<p id="folder-dialog-head" data-pick-head><strong data-head></strong><br><span class="muted small" data-sub></span></p>'
    + '<div class="assign-defaults small"><strong>' + (window.qgenIcon ? window.qgenIcon('lc-alert') : '') + 'What happens:</strong><ul data-happens></ul></div>';
  dialog.setAttribute('aria-labelledby', 'folder-dialog-head');
  var strong = dialog.querySelector('[data-head]'), sub = dialog.querySelector('[data-sub]'), happens = dialog.querySelector('[data-happens]');
  if (label) { label.classList.add('sr-only'); dialog.appendChild(label); }
  sel.setAttribute('form', form.id);
  dialog.appendChild(sel);
  sel.hidden = true;
  dialog.insertAdjacentHTML('beforeend', window.qgenFolderPick.html());
  var holder = dialog.querySelector('[data-folder-pick]');
  var err = document.createElement('p');
  err.className = 'error small'; err.hidden = true; err.textContent = 'Choose a folder first.';
  dialog.appendChild(err);
  holder.addEventListener('change', function () { err.hidden = true; });
  //the bar's folders as round buttons, indented as in the folder list; "out of every folder"
  //(Uncategorized) first
  function fillList() {
    var got = window.qgenFolderPick.fromSelect(sel);
    window.qgenFolderPick.fill(holder, got.folders, { type: 'radio', name: 'bar-move-to', top: got.top,
      each: function (f, r) { r.disabled = !!f.disabled; } });
  }
  var row = document.createElement('div');
  row.className = 'btn-row';
  var cancel = document.createElement('button');
  cancel.type = 'button'; cancel.className = 'btn btn-secondary'; cancel.textContent = 'Cancel';
  cancel.addEventListener('click', function () { dialog.close(); });
  var go = document.createElement('button');
  go.type = 'submit'; go.className = 'btn';
  go.setAttribute('form', form.id);
  row.appendChild(go); row.appendChild(cancel);
  dialog.appendChild(row);
  document.body.appendChild(dialog);
  //(sent: the dialog steps aside, so takeout.js's question, if any, shows alone)
  go.addEventListener('click', function (e) {
    var r = holder.querySelector('input:checked');
    if (!r) { e.preventDefault(); err.hidden = false; return; }
    sel.value = r.value;
    //(what's checked in other folders goes too: static/js/checked.js)
    form.querySelectorAll('input[data-kept]').forEach(function (i) { i.remove(); });
    if (window.qgenCheckedIds) {
      var here = {};
      document.querySelectorAll('.folder-main input[name="items"]:checked').forEach(function (t) { here[t.value] = 1; });
      window.qgenCheckedIds().forEach(function (id) {
        if (here[id]) return;
        var i = document.createElement('input'); i.type = 'hidden'; i.name = 'items'; i.value = id; i.dataset.kept = '';
        form.appendChild(i);
      });
    }
    setTimeout(function () { dialog.close(); }, 0);
  });
  if (sel.querySelector('option[value=""]')) sel.required = true;

  function checked() {
    if (window.qgenCheckedIds) return window.qgenCheckedIds().length;
    var ids = {};
    document.querySelectorAll('.folder-main input[name="items"]:checked, .folder-main input.pick-person:checked').forEach(function (t) { ids[t.value] = 1; });
    return Object.keys(ids).length;
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function (e) {
      e.preventDefault();
      var n = checked();
      if (!n) return;
      if (b.value === 'remove') { takeOut(checkedIds()); return; }
      if (b.value === 'add') { putIn(checkedIds(), '', []); return; }
      var what = n === 1 ? 'the checked ' + unit : 'the ' + n + ' checked ' + units;
      var words = b.textContent.trim();
      //"Put in folder" → "Put the 2 checked problems in a folder"; "Take out of folder" →
      //"Take … out of a folder"; the Archive's "Move" → "Move … to a folder"
      strong.textContent = b.value === 'add' ? 'Put ' + what + ' in a folder'
        : b.value === 'remove' ? 'Take ' + what + ' out of a folder'
        : words + ' ' + what + ' to a folder';
      go.textContent = words;
      go.title = b.dataset.titleWas || b.title || '';
      if (b.name) { go.name = b.name; go.value = b.value; } else { go.removeAttribute('name'); go.removeAttribute('value'); }
      //(the bar grays its list out while nothing is checked: here something is)
      sel.disabled = false; sel.removeAttribute('title');
      sub.textContent = 'Choose the folder to move ' + (n === 1 ? 'it' : 'them') + ' to.';
      //(the same words as a row's Move: the Archive's attempts)
      window.qgenFolderPick.happens(happens, [n === 1 ? 'It leaves the folder it\u2019s in now' : 'They leave the folders they\u2019re in now',
        units === 'attempts' ? 'An attempt is in one folder at a time' : '']);
      fillList(); err.hidden = true;
      dialog.showModal();
    });
  });

  /* Take out of folder (the owner, 2026-10-15): no folder to choose; it's the folder open now
     (its tab, or its own page). The dialog says where each will go (up to the folder it's in,
     else Uncategorized, never deleted), and OK does it. */
  var confirmBox = document.createElement('dialog');
  confirmBox.className = 'ask ask-many takeout-dialog';
  confirmBox.innerHTML = '<p><strong data-head></strong></p><ul class="takeout-lines small" data-lines></ul>'
    + '<div class="btn-row"><button type="button" class="btn" data-ok>Take out</button><button type="button" class="btn btn-secondary" data-no>Cancel</button></div>';
  document.body.appendChild(confirmBox);
  confirmBox.querySelector('[data-no]').addEventListener('click', function () { confirmBox.close(); });
  function openFolder() {
    var pressed = document.querySelectorAll('.folder-filter-rows .folder-tab[aria-pressed="true"]');
    var id = pressed.length ? pressed[pressed.length - 1].dataset.folder || '' : '';
    if (id.indexOf('self:') === 0) id = id.slice(5);
    if (/^\d+$/.test(id)) return id;
    var page = new URLSearchParams(location.search).get('folder') || '';
    return /^\d+$/.test(page) ? page : null;
  }
  function folderName(id) {
    var el = document.querySelector('.folder-side .side-row[data-drop="' + id + '"] .side-link');
    return el ? el.textContent.trim() : 'this folder';
  }
  function checkedIds() {
    if (window.qgenCheckedIds) return window.qgenCheckedIds();
    var ids = {};
    document.querySelectorAll('.folder-main input[name="items"]:checked, .folder-main input.pick-person:checked').forEach(function (t) { ids[t.value] = 1; });
    return Object.keys(ids);
  }
  function takeOut(ids, label) {
    var n = ids.length;
    var head = confirmBox.querySelector('[data-head]'), lines = confirmBox.querySelector('[data-lines]'), ok = confirmBox.querySelector('[data-ok]');
    var what = label || (n === 1 ? 'the checked ' + unit : 'the ' + n + ' checked ' + units);
    var id = openFolder();
    lines.innerHTML = '';
    //(no folder open, e.g. All: each comes out of the folder it's in, the owner 2026-10-15)
    if (!id) id = 'own';
    confirmBox.querySelector('[data-no]').hidden = false;
    var name = id === 'own' ? '' : folderName(id);
    head.textContent = id === 'own' ? 'Take ' + what + ' out of ' + (n === 1 ? (unit === 'person' ? 'his/her folder' : 'its folder') : 'their folders') + '?' : 'Take ' + what + ' out of “' + name + '”?';
    var data = new FormData(form);
    data.delete('items');
    ids.forEach(function (i) { data.append('items', i); });
    data.set(sel.name, id);
    data.set('action', 'remove');
    data.set('check', '1');
    ok.disabled = true;
    lines.innerHTML = '<li class="muted">Checking…</li>';
    confirmBox.showModal();
    fetch(form.getAttribute('action'), { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        lines.innerHTML = '';
        var said = res.ok ? (res.preview && res.preview.length ? res.preview : ['None of them is in “' + (name || 'a folder') + '”.']) : [res.error || 'That didn\'t work. Please reload the page and try again.'];
        said.forEach(function (t) { var li = document.createElement('li'); li.textContent = t; lines.appendChild(li); });
        ok.disabled = !(res.ok && res.preview && res.preview.some(function (t) { return !/ isn’t in any folder\.$/.test(t); }));
        ok.onclick = function () {
          //(a form of its own with just these, so nothing else checked goes along; sent straight,
          //past static/js/takeout.js's question: nothing is deleted from here)
          var f = document.createElement('form');
          f.method = 'post'; f.action = form.getAttribute('action'); f.hidden = true;
          function hidden(k, v) { var i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = v; f.appendChild(i); }
          hidden('csrf_token', form.querySelector('input[name=csrf_token]').value);
          var view = form.querySelector('input[name=view]');
          if (view) hidden('view', view.value);
          ids.forEach(function (i) { hidden('items', i); });
          hidden(sel.name, id);
          hidden('action', 'remove');
          hidden('confirm', 'uncategorized');
          document.body.appendChild(f);
          if (window.qgenCheckedClear) window.qgenCheckedClear();
          f.submit();
        };
      }, function () { lines.innerHTML = '<li>That didn\'t work. Please reload the page and try again.</li>'; });
  }
  /* Put in folder (the owner, 2026-10-15): laid out like the Assign dialogs: what happens, then
     the folders (indented as in the folder list). The checked bar's button (the checked ones)
     and each row's folder-with-plus icon (just that one).
     Moving is the usual way (the owner, 2026-10-16): choose one folder, and they leave the
     folders they're in now. "Copy instead" keeps them where they are too, and then several
     folders can be checked (folders they're in already shown checked and grayed). */
  var putBox = document.createElement('dialog');
  //(laid out like the Assign dialogs, 820px wide, the standard picker with its side folder list:
  //static/js/dialogfilter.js; "Copy instead" on its own line under the amber box, which keeps only
  //its lines: the owner, 2026-10-22)
  putBox.className = 'ask ask-many assign-many pick-dialog put-dialog';
  putBox.innerHTML = '<p data-pick-head><strong data-head></strong><br><span class="muted small" data-sub></span></p>'
    + '<div class="assign-defaults small"><strong>' + (window.qgenIcon ? window.qgenIcon('lc-alert') : '') + 'What happens:</strong><ul><li data-stays></li><li data-several></li></ul></div>'
    + '<label class="put-copy"><input type="checkbox" data-copy> <span data-copy-words></span></label>'
    + window.qgenFolderPick.html()
    + '<p class="error small" data-err hidden></p>'
    + '<div class="btn-row"><button type="button" class="btn" data-ok></button><button type="button" class="btn btn-secondary" data-no>Cancel</button></div>';
  document.body.appendChild(putBox);
  var putList = putBox.querySelector('[data-folder-pick]'), copyBox = putBox.querySelector('[data-copy]');
  putBox.querySelector('[data-no]').addEventListener('click', function () { putBox.close(); });
  putBox.addEventListener('change', function (e) {
    if (e.target !== copyBox && putList.querySelector('input:checked:not(:disabled)')) putBox.querySelector('[data-err]').hidden = true;
  });
  var putState = null;
  function putDraw() {
    var d = putState, n = d.ids.length, copy = copyBox.checked;
    var it = n === 1 ? (unit === 'person' ? 'him/her' : 'it') : 'them';
    var stays = n === 1 ? (unit === 'person' ? 'he' : 'it') : 'they';
    var inNow = n === 1 ? (unit === 'person' ? 'he/she is' : 'it’s') : 'they’re';
    putBox.querySelector('[data-head]').textContent = copy ? 'Put ' + d.what + ' in folders' : 'Move ' + d.what + ' to a folder';
    putBox.querySelector('[data-sub]').textContent = copy ? 'Check the folders to put ' + it + ' in.' : 'Choose the folder to move ' + it + ' to.';
    putBox.querySelector('[data-stays]').textContent = copy ? (stays === 'it' ? 'It will still be available in its original folders' : stays === 'he' ? 'He/she will still be available in his/her original folders' : 'They will still be available in their original folders')
      : (stays === 'it' ? 'It moves' : stays === 'he' ? 'He/she moves' : 'They move') + ' to a new folder';
    putBox.querySelector('[data-several]').textContent = 'You can check several folders';
    putBox.querySelector('[data-several]').hidden = !copy;
    putBox.querySelector('[data-copy-words]').textContent = 'Copy instead: keep ' + it + ' in the folders ' + inNow + ' in now too';
    putBox.querySelector('[data-ok]').textContent = copy ? 'Put in folder' : 'Move';
    putBox.querySelector('[data-err]').textContent = copy ? 'Check at least one folder first.' : 'Choose a folder first.';
    putBox.querySelector('[data-err]').hidden = true;
    var onlyIn = d.from || (n === 1 && d.already.length === 1 ? d.already[0] : null);
    //(a folder inside another indented as in the folder list; a folder icon between the box and the
    //name: the owner, 2026-10-16; no "out of every folder" here, so no Uncategorized)
    window.qgenFolderPick.fill(putList, window.qgenFolderPick.fromSelect(sel).folders, { type: copy ? 'checkbox' : 'radio', name: 'put-to',
      each: function (f, box, lab) {
        if (copy && d.already.indexOf(f.id) !== -1) { box.checked = true; box.disabled = true; lab.title = 'Already in it'; }
        if (!copy && f.id === onlyIn) { box.disabled = true; lab.title = 'Already in it'; }
      } });
  }
  copyBox.addEventListener('change', putDraw);
  putBox.querySelector('[data-ok]').addEventListener('click', function () {
    var d = putState, copy = copyBox.checked;
    var picked = Array.prototype.map.call(putList.querySelectorAll('input:checked:not(:disabled)'), function (b) { return b.value; });
    if (!picked.length) { putBox.querySelector('[data-err]').hidden = false; return; }
    var f = document.createElement('form');
    f.method = 'post'; f.action = form.getAttribute('action'); f.hidden = true;
    function hidden(k, v) { var i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = v; f.appendChild(i); }
    hidden('csrf_token', form.querySelector('input[name=csrf_token]').value);
    var view = form.querySelector('input[name=view]');
    if (view) hidden('view', view.value);
    d.ids.forEach(function (i) { hidden('items', i); });
    picked.forEach(function (g) { hidden(sel.name, g); });
    hidden('action', copy ? 'add' : 'move');
    //("Move from “X”", from Remove: out of that folder only, static/js/takeout.js)
    if (!copy && d.from) hidden('from', d.from);
    document.body.appendChild(f);
    if (window.qgenCheckedClear) window.qgenCheckedClear();
    f.submit();
  });
  function putIn(ids, label, already, from) {
    if (!ids.length) return;
    var n = ids.length;
    putState = { ids: ids, already: already, from: from || null, what: label || (n === 1 ? 'the checked ' + unit : 'the ' + n + ' checked ' + units) };
    copyBox.checked = false;
    putDraw();
    putBox.showModal();
  }
  window.qgenPutIn = putIn;
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-put-in]');
    if (!b || b.disabled) return;
    e.preventDefault();
    putIn([b.dataset.putIn], b.dataset.label || '', (b.dataset.in || '').split(' ').filter(Boolean));
  });
  //a row's or card's own Take out of folder icon (beside its folder-with-plus): just that one
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-take-out]');
    if (!b || b.disabled) return;
    e.preventDefault();
    takeOut([b.dataset.takeOut], b.dataset.label || '');
  });
})();

/* The checked bar, uncluttered (the owner, 2026-10-21; it was "Check …, then pick an action:" over a
 * row of five small buttons): checking all is a check box at the top of the check column, and the
 * bar's actions sit behind one button, "With checked (3)", that opens a small dialog listing them
 * (each then opens its own dialog as before). Grayed, with why, while nothing is checked. The
 * actions stay part of the bar's form (form="file-form"), so everything they did still works. */
(function () {
  var form = document.getElementById('file-form');
  if (!form) return;
  var TICKS = '.folder-main input[name="items"], .folder-main input.pick-person';
  var unitEl = document.querySelector('[data-unit][data-units]');
  var units = unitEl ? unitEl.dataset.units : 'ones', unit = unitEl ? unitEl.dataset.unit : 'one';
  function ticks() { return Array.prototype.slice.call(document.querySelectorAll(TICKS)); }
  function shown(t) { return !t.closest('[hidden], template') && !t.disabled; }
  function count() {
    if (window.qgenCheckedIds) return window.qgenCheckedIds().length;
    var ids = {};
    ticks().forEach(function (t) { if (t.checked) ids[t.value] = 1; });
    return Object.keys(ids).length;
  }
  function set(list, on) {
    list.forEach(function (t) {
      if (t.checked === on) return;
      t.checked = on;
      t.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }

  //the dialog of actions: the bar's buttons (and its no-folders note), moved in
  var dlg = document.createElement('dialog');
  dlg.className = 'ask ask-many with-checked-dialog';
  dlg.id = 'with-checked-dialog';
  dlg.setAttribute('aria-labelledby', 'with-checked-head');
  dlg.innerHTML = '<p><strong id="with-checked-head"></strong></p><div class="with-checked-actions"></div>'
    + '<div class="btn-row"><button type="button" class="btn btn-secondary" data-cancel>Cancel</button></div>';
  var actions = dlg.querySelector('.with-checked-actions');
  Array.prototype.slice.call(form.children).forEach(function (el) {
    if (el.matches('input[type=hidden], select, label')) return;
    if (el.classList.contains('file-count')) { el.hidden = true; return; }
    if (el.matches('button, a, .btn')) el.setAttribute('form', form.id);
    actions.appendChild(el);
  });
  document.body.appendChild(dlg);
  dlg.querySelector('[data-cancel]').addEventListener('click', function () { dlg.close(); });
  //(an action picked: this dialog steps aside first, so the action's own dialog shows alone)
  actions.addEventListener('click', function (e) {
    var b = e.target.closest('button, a');
    if (b && !b.disabled) dlg.close();
  }, true);

  var open = document.createElement('button');
  open.type = 'button'; open.className = 'btn btn-sm with-checked';
  //(it sits in the Checked folder's header, beside its tab, not in the bar: folderfilter.js puts it
  //there; the owner, 2026-10-21)
  window.qgenApplyChecked = open;
  //(the folder list may have drawn its Checked header before this script ran, e.g. a reload with
  //Checked open: it's drawn again now, with the button; the code critic, 2026-10-22)
  document.dispatchEvent(new CustomEvent('qgen-apply-ready'));
  open.addEventListener('click', function () {
    var n = count();
    if (!n) return;
    dlg.querySelector('#with-checked-head').textContent = 'Apply to the ' + (n === 1 ? 'checked ' + unit : n + ' checked ' + units);
    dlg.showModal();
    var first = actions.querySelector('button:not(:disabled), a');
    if (first) first.focus();
  });

  //Check all / Uncheck all: a check box at the top of each check column
  var heads = Array.prototype.slice.call(document.querySelectorAll('.folder-main th.tick-col'));
  heads.forEach(function (th) {
    var c = document.createElement('input');
    c.type = 'checkbox'; c.className = 'check-all';
    //(only its hidden words go: the list's Expand all / Collapse all may be in this cell already)
    th.querySelectorAll(':scope > .sr-only').forEach(function (el) { el.remove(); });
    th.insertBefore(c, th.firstChild);
    c.addEventListener('change', function () {
      var list = ticks().filter(shown);
      var every = list.length && list.every(function (t) { return t.checked; });
      //(only what shows, both ways: what's checked in other folders stays; the owner, 2026-10-23)
      set(list, !every);
      setTimeout(sync, 0);
    });
  });

  function sync() {
    var n = count(), list = ticks().filter(shown);
    var on = list.filter(function (t) { return t.checked; }).length;
    open.textContent = 'Apply to checked (' + n + ')';  // (the owner's words, 2026-10-21)
    open.disabled = !n;
    open.title = n ? 'Move, take out or more, for the ' + (n === 1 ? 'checked ' + unit : n + ' checked ' + units) : 'Check some ' + units + ' first';
    document.querySelectorAll('.folder-main th.tick-col input.check-all').forEach(function (c) {
      c.checked = !!list.length && on === list.length;
      c.indeterminate = on > 0 && on < list.length;
      c.disabled = !list.length;
      var words = c.checked ? 'Uncheck all shown' : 'Check all shown';
      c.title = words; c.setAttribute('aria-label', words);
    });
  }
  document.addEventListener('change', function () { setTimeout(sync, 0); });
  document.addEventListener('click', function (e) { if (e.target.closest('.folder-tab, .side-row, [data-level]')) setTimeout(sync, 50); });
  document.addEventListener('input', function () { setTimeout(sync, 50); });  // (the filter)
  document.addEventListener('qgen-checked', function () { setTimeout(sync, 0); });
  sync();
})();

/* The Archive's Problems, Quizzes and People: the checked bar's Restore puts every checked one
 * back (the owner, 2026-10-16) */
(function () {
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-restore-many]');
    if (!b || b.disabled) return;
    var ids = window.qgenCheckedIds ? window.qgenCheckedIds() : [];
    if (!ids.length) return;
    //(asks first: "Restore the 3 checked problems? They go back on the Problems page."; the
    //owner, 2026-10-19)
    var q = ids.length === 1 ? 'Restore the checked ' + b.dataset.one + '? ' + b.dataset.thenOne
                             : 'Restore the ' + ids.length + ' checked ' + b.dataset.noun + '? ' + b.dataset.then;
    (window.qgenAsk ? window.qgenAsk(q, 'Restore') : Promise.resolve(true)).then(function (yes) {
      if (yes) send(b.dataset.url, ids);
    });
  });
  //(the button's address passed in: it was read from a name not in reach here, so Restore never
  //sent; found by the code critic, 2026-10-20)
  function send(url, ids) {
    var form = document.getElementById('file-form');
    var f = document.createElement('form');
    f.method = 'post'; f.action = url; f.hidden = true;
    function hidden(k, v) { var i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = v; f.appendChild(i); }
    hidden('csrf_token', form.querySelector('input[name=csrf_token]').value);
    var view = form.querySelector('input[name=view]');
    if (view) hidden('view', view.value);
    ids.forEach(function (i) { hidden('items', i); });
    document.body.appendChild(f);
    if (window.qgenCheckedClear) window.qgenCheckedClear();
    f.submit();
  }
})();
