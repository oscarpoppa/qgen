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
  dialog.className = 'ask ask-many folder-dialog';
  dialog.id = 'folder-dialog';
  var head = document.createElement('p');
  head.id = 'folder-dialog-head';
  dialog.setAttribute('aria-labelledby', head.id);
  var strong = document.createElement('strong');
  head.appendChild(strong);
  dialog.appendChild(head);
  if (label) { label.classList.add('sr-only'); dialog.appendChild(label); }
  sel.setAttribute('form', form.id);
  dialog.appendChild(sel);
  var row = document.createElement('div');
  row.className = 'btn-row';
  var cancel = document.createElement('button');
  cancel.type = 'button'; cancel.className = 'btn btn-secondary'; cancel.textContent = 'Cancel';
  cancel.addEventListener('click', function () { dialog.close(); });
  var go = document.createElement('button');
  go.type = 'submit'; go.className = 'btn';
  go.setAttribute('form', form.id);
  row.appendChild(cancel); row.appendChild(go);
  dialog.appendChild(row);
  document.body.appendChild(dialog);
  //(sent: the dialog steps aside, so takeout.js's question, if any, shows alone)
  go.addEventListener('click', function () {
    if (sel.required !== false && sel.value === '') return;
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
      dialog.showModal();
      sel.focus();
    });
  });

  /* Take out of folder (the owner, 2026-10-15): no folder to choose; it's the folder open now
     (its tab, or its own page). The dialog says where each will go (up to the folder it's in,
     else Uncategorized, never deleted), and OK does it. */
  var confirmBox = document.createElement('dialog');
  confirmBox.className = 'ask ask-many takeout-dialog';
  confirmBox.innerHTML = '<p><strong data-head></strong></p><ul class="takeout-lines small" data-lines></ul>'
    + '<div class="btn-row"><button type="button" class="btn btn-secondary" data-no>Cancel</button><button type="button" class="btn" data-ok>OK</button></div>';
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
  putBox.className = 'ask ask-many assign-many put-dialog';
  putBox.innerHTML = '<p><strong data-head></strong><br><span class="muted small" data-sub></span></p>'
    + '<div class="assign-defaults small"><strong>What happens:</strong><ul><li data-stays></li><li data-several></li></ul>'
    + '<label class="put-copy"><input type="checkbox" data-copy> <span data-copy-words></span></label></div>'
    + '<div class="assign-many-tools"><span class="muted small" data-count></span></div>'
    + '<ul class="assign-many-people put-list" data-list></ul>'
    + '<p class="error small" data-err hidden></p>'
    + '<div class="btn-row"><button type="button" class="btn btn-secondary" data-no>Cancel</button><button type="button" class="btn" data-ok></button></div>';
  document.body.appendChild(putBox);
  var putList = putBox.querySelector('[data-list]'), copyBox = putBox.querySelector('[data-copy]');
  putBox.querySelector('[data-no]').addEventListener('click', function () { putBox.close(); });
  function putCount() {
    var n = putList.querySelectorAll('input:checked:not(:disabled)').length;
    putBox.querySelector('[data-count]').textContent = copyBox.checked ? n + ' checked' : '';
    if (n) putBox.querySelector('[data-err]').hidden = true;
  }
  putBox.addEventListener('change', function (e) { if (e.target !== copyBox) putCount(); });
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
    putList.innerHTML = '';
    var onlyIn = d.from || (n === 1 && d.already.length === 1 ? d.already[0] : null);
    Array.prototype.forEach.call(sel.options, function (o) {
      if (!o.value) return;
      var li = document.createElement('li'), lab = document.createElement('label'), box = document.createElement('input');
      box.type = copy ? 'checkbox' : 'radio'; box.name = 'put-to'; box.value = o.value;
      if (copy && d.already.indexOf(o.value) !== -1) { box.checked = true; box.disabled = true; lab.title = 'Already in it'; }
      if (!copy && o.value === onlyIn) { box.disabled = true; lab.title = 'Already in it'; }
      //(a folder inside another: the whole line indented, as in the folder list)
      var text = o.textContent, depth = (text.match(/^ +/) || [''])[0].length;
      li.style.paddingLeft = (depth * 6) + 'px';
      lab.appendChild(box);
      //(a folder icon between the box and the name, as in the folder lists: the owner, 2026-10-16)
      if (window.qgenIcon) lab.insertAdjacentHTML('beforeend', ' ' + window.qgenIcon('folder'));
      lab.appendChild(document.createTextNode(' ' + text.replace(/^ +/, '')));
      li.appendChild(lab);
      putList.appendChild(li);
    });
    putCount();
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

/* Check all / Uncheck all on every checked bar (the owner, 2026-10-15): Check all checks
 * everything the list shows now (the open folder tab, what the filter matches; folded boxes
 * count too), Uncheck all unchecks everything. Each is grayed when there's nothing for it to do. */
(function () {
  var form = document.getElementById('file-form');
  if (!form) return;
  var TICKS = '.folder-main input[name="items"], .folder-main input.pick-person';
  var unitEl = document.querySelector('[data-unit][data-units]');
  var units = unitEl ? unitEl.dataset.units : 'ones';
  function ticks() { return Array.prototype.slice.call(document.querySelectorAll(TICKS)); }
  function shown(t) { return !t.closest('[hidden], template') && !t.disabled; }
  function make(words, title) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'btn btn-secondary btn-sm bar-all';
    b.textContent = words; b.dataset.titleWas = title; b.title = title;
    return b;
  }
  var all = make('Check all', 'Check every one of the ' + units + ' shown below');
  var none = make('Uncheck all', 'Uncheck all the checked ' + units);
  var first = form.querySelector('button, [data-add-quiz]');
  form.insertBefore(all, first);
  form.insertBefore(none, first);
  //(the bar's buttons on one line: as many grid columns as it has buttons)
  form.style.setProperty('--bar-cols', form.querySelectorAll(':scope > .btn, :scope > button').length);
  function set(list, on) {
    list.forEach(function (t) {
      if (t.checked === on) return;
      t.checked = on;
      t.dispatchEvent(new Event('change', { bubbles: true }));
    });
  }
  all.addEventListener('click', function () { set(ticks().filter(shown), true); });
  none.addEventListener('click', function () {
    set(ticks(), false);
    //(and what's checked in other folders: static/js/checked.js)
    if (window.qgenCheckedClear) { window.qgenCheckedClear(); form.dispatchEvent(new Event('change')); }
  });
  //(after the bar's own update, which grays out every button while nothing is checked)
  function sync() {
    var list = ticks();
    all.disabled = !list.some(function (t) { return shown(t) && !t.checked; });
    none.disabled = !(window.qgenCheckedIds ? window.qgenCheckedIds().length : list.some(function (t) { return t.checked; }));
    all.title = all.disabled ? 'Everything shown is checked' : all.dataset.titleWas;
    none.title = none.disabled ? 'Nothing is checked' : none.dataset.titleWas;
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
    var form = document.getElementById('file-form');
    var ids = window.qgenCheckedIds ? window.qgenCheckedIds() : [];
    if (!ids.length) return;
    //(asks first: "Restore the 3 checked problems? They go back on the Problems page."; the
    //owner, 2026-10-19)
    var q = ids.length === 1 ? 'Restore the checked ' + b.dataset.one + '? ' + b.dataset.thenOne
                             : 'Restore the ' + ids.length + ' checked ' + b.dataset.noun + '? ' + b.dataset.then;
    (window.qgenAsk ? window.qgenAsk(q, 'Restore') : Promise.resolve(true)).then(function (yes) {
      if (yes) send(ids);
    });
  });
  function send(ids) {
    var form = document.getElementById('file-form');
    var f = document.createElement('form');
    f.method = 'post'; f.action = b.dataset.url; f.hidden = true;
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
