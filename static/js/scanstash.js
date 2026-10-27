/* The stash's folders on Scan workbook pages (the owner, 2026-10-23): a button with data-stash-dialog="<id>"
 * opens that dialog; its data-url becomes the form's address, data-name the folder's or scan's name in its
 * words (and the rename box), data-here the folder a scan is in now (its round button starts checked). Cancel closes. */
(function () {
  document.addEventListener('click', function (e) {
    var cancel = e.target.closest && e.target.closest('dialog.folder-dialog [data-cancel]');
    if (cancel) { cancel.closest('dialog').close(); return; }
    var b = e.target.closest && e.target.closest('[data-stash-dialog]');
    if (!b) return;
    var d = document.getElementById(b.dataset.stashDialog);
    if (!d) return;
    var menu = b.closest('details.folder-tools');  // (a choice in the Folder options menu closes the menu)
    if (menu) menu.removeAttribute('open');
    var form = d.querySelector('form');
    if (b.dataset.url) form.action = b.dataset.url;
    d.querySelectorAll('[data-stash-name]').forEach(function (el) { el.textContent = b.dataset.name || ''; });
    var text = d.querySelector('input[name="name"]');
    if (text && b.dataset.name !== undefined) text.value = b.dataset.name;
    //(a folder dialog's picker is drawn when it opens, from the folder it starts on: the scan's own, or Uncategorized)
    var holder = d.querySelector('[data-folder-pick]');
    if (holder && b.dataset.here !== undefined) { holder.dataset.checked = b.dataset.here || 'top'; var old = holder.querySelector('table'); if (old) old.remove(); }
    d.showModal();
    if (text) { text.focus(); text.select(); }
  });
})();

/* Dragging a stashed scan onto a folder (the owner, 2026-10-23), done with the mouse like the other folder pages
 * (static/js/folders.js): press on a scan's row, move a little, and a label follows the pointer; let go over a folder
 * in the list (or Uncategorized) and the scan moves there, as the Move icon does. A plain click still does what it did;
 * Esc cancels. Not on a touch screen: the Move icon does the job. */
(function () {
  var pending = null, dragging = null, ghost = null, over = null, swallow = false;
  function target(x, y) {
    var el = document.elementFromPoint(x, y), t = el && el.closest ? el.closest('[data-stash-drop]') : null;
    return t && t.dataset.stashDrop !== dragging.home && t.dataset.stashDrop !== 'all' ? t : null;
  }
  function light(t) {
    if (over === t) return;
    if (over) over.classList.remove('drop-over');
    over = t;
    if (over) over.classList.add('drop-over');
  }
  function stop() {
    light(null);
    if (dragging) dragging.row.classList.remove('dragging');
    document.body.classList.remove('folder-dragging');
    if (ghost) ghost.remove();
    pending = dragging = ghost = null;
  }
  //(the rows are found when pressed, not when the page loads: the card can be redrawn)
  document.addEventListener('mousedown', function (e) {
    var row = e.target.closest && e.target.closest('tr[data-stash-drag]');
    if (!row || e.button !== 0 || e.target.closest('button, input, select, textarea, label')) return;
    pending = { row: row, x: e.clientX, y: e.clientY, url: row.dataset.url, name: row.dataset.name, home: row.dataset.home || 'main' };
    //(no text selection and no browser drag of the picture or the name link: either one takes over the mouse, so nothing
    //followed the pointer until it was let go; a click still goes through, as on the other folder pages)
    e.preventDefault();
  });
  document.addEventListener('dragstart', function (e) { if (pending || dragging) e.preventDefault(); });
  document.addEventListener('mousemove', function (e) {
    if (pending && !dragging) {
      if (Math.abs(e.clientX - pending.x) + Math.abs(e.clientY - pending.y) < 6) return;
      dragging = pending;
      ghost = document.createElement('div');
      ghost.className = 'drag-ghost';
      ghost.textContent = dragging.name;
      document.body.appendChild(ghost);
      dragging.row.classList.add('dragging');
      document.body.classList.add('folder-dragging');
    }
    if (!dragging) return;
    e.preventDefault();
    ghost.style.left = (e.clientX + 12) + 'px';
    ghost.style.top = (e.clientY + 12) + 'px';
    light(target(e.clientX, e.clientY));
  });
  document.addEventListener('mouseup', function (e) {
    if (!dragging) { pending = null; return; }
    var d = dragging, t = target(e.clientX, e.clientY);
    swallow = true;  // (the click that follows a drag shouldn't open the scan)
    setTimeout(function () { swallow = false; }, 0);
    stop();
    if (!t) return;
    var dialog = document.getElementById('stash-move'), form = dialog && dialog.querySelector('form');
    if (!form) return;
    var f = document.createElement('form');
    f.method = 'post'; f.action = d.url; f.hidden = true;
    var csrf = form.querySelector('input[name="csrf_token"]');
    if (csrf) f.appendChild(csrf.cloneNode());
    var to = document.createElement('input');
    to.type = 'hidden'; to.name = 'to'; to.value = t.dataset.stashDrop === 'main' ? '' : t.dataset.stashDrop;
    f.appendChild(to);
    //(the folder open now stays open: drag the next one)
    var stay = document.createElement('input');
    stay.type = 'hidden'; stay.name = 'stay'; stay.value = new URLSearchParams(location.search).get('stash') || '';
    f.appendChild(stay);
    document.body.appendChild(f);
    f.dataset.inPlace = ''; (window.qgenSubmit || function (x) { x.submit(); })(f);  // (in place: static/js/inplace.js)
  });
  document.addEventListener('click', function (e) { if (swallow) { e.preventDefault(); e.stopPropagation(); } }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && (pending || dragging)) stop(); });
})();


/* The stash's folder list folds like every other folder list (static/js/folders.js): the arrow shows or hides the folders
 * inside a folder, it's remembered in this browser, the folders above the one open stay open, and Expand all / Collapse all
 * (beside "Folders") do all of them; grayed out, with why, when no folder in the list has folders inside it. */
function foldList() {
  var nav = document.querySelector('.stash-folders');
  if (!nav) return;
  var KEY = 'qgen-folded-stash', path = [], folded = {}, shows = [];
  try { path = JSON.parse(nav.dataset.path || '[]'); } catch (e) {}
  try { (JSON.parse(localStorage.getItem(KEY) || '[]') || []).forEach(function (id) { folded[id] = true; }); } catch (e) {}
  path.forEach(function (id) { delete folded[id]; });
  function save() { try { localStorage.setItem(KEY, JSON.stringify(Object.keys(folded))); } catch (e) {} }
  nav.querySelectorAll('.side-item').forEach(function (li) {
    var btn = li.querySelector(':scope > .side-row > .side-fold');
    if (!btn) return;
    function show(open) {
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      li.classList.toggle('side-folded', !open);
      if (open) delete folded[li.dataset.folder]; else folded[li.dataset.folder] = true;
    }
    shows.push({ id: li.dataset.folder, show: show });
    show(!folded[li.dataset.folder]);
    //(a folder above the one open can't be folded: the folder you're in always shows)
    if (path.slice(0, -1).map(String).indexOf(String(li.dataset.folder)) !== -1) {
      btn.disabled = true;
      btn.title = 'You\u2019re in a folder inside this one, so it stays open';
      return;
    }
    btn.addEventListener('click', function () { show(btn.getAttribute('aria-expanded') !== 'true'); save(); });
  });
  save();
  var levels = nav.querySelector('.side-levels');
  if (!levels) return;
  levels.qgenScope = nav;  // (static/js/boxes.js keeps the one-toggle in step with the arrows in this list: it looks in here, as it does for the other lists)
  //(one toggle, as on every folder list: only one of the two shows, Expand all while anything is folded, else Collapse all: static/js/boxes.js)
  function sync() {
    var open = levels.querySelector('[data-side-level="open"]'), close = levels.querySelector('[data-side-level="close"]');
    var all = nav.querySelectorAll('.side-fold');
    var anyShut = !all.length || Array.prototype.some.call(all, function (f) { return f.getAttribute('aria-expanded') === 'false'; });
    open.classList.toggle('lvl-off', !anyShut);
    close.classList.toggle('lvl-off', anyShut);
  }
  sync();
  nav.addEventListener('click', function () { setTimeout(sync, 0); });
  if (!shows.length) {
    levels.querySelectorAll('[data-side-level]').forEach(function (b) { b.disabled = true; b.title = 'No folder here has folders inside it'; });
    return;
  }
  levels.addEventListener('click', function (e) {
    var b = e.target.closest('[data-side-level]');
    if (!b) return;
    var open = b.dataset.sideLevel === 'open';
    shows.forEach(function (s) { s.show(open || path.slice(0, -1).map(String).indexOf(String(s.id)) !== -1); });
    save();
  });
}
foldList();
//(the page redraws its cards now and then, new rows each time: the arrows are hooked up again)
document.addEventListener('qgen-stash-redrawn', foldList);

/* The stash's check boxes (the owner, 2026-10-24, To do 10): what's checked is kept in this browser tab whatever folder is
 * open (each folder is its own page); the Checked folder lists them (?stash=checked&checked=4,7), its "Apply to checked"
 * moves them to a folder or discards them (asked first). Done, they're unchecked; canceled, they stay checked. */
(function () {
  var KEY = 'qgen-stash-checked';
  var kept = [];
  try { kept = JSON.parse(sessionStorage.getItem(KEY) || '[]') || []; } catch (e) { kept = []; }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(kept)); } catch (e) {} }
  function boxes() { return Array.prototype.slice.call(document.querySelectorAll('input.stash-pick')); }
  function show() {
    document.querySelectorAll('[data-stash-checked-count]').forEach(function (el) { el.textContent = kept.length; });
    var words = kept.length === 1 ? 'checked workbook' : kept.length + ' checked workbooks';
    document.querySelectorAll('[data-stash-checked-words]').forEach(function (el) { el.textContent = words; });
    var link = document.querySelector('[data-stash-checked-link]');
    if (link) link.href = link.getAttribute('href').split('?')[0].split('#')[0] + '?stash=checked&checked=' + kept.join(',') + '#scan-away';
    var row = link && link.closest('.side-row');
    //(green while anything is checked, as on every folder list: .has-checked)
    if (row) { row.classList.toggle('is-empty', !kept.length); row.classList.toggle('has-checked', !!kept.length); }
    var all = document.querySelector('[data-stash-all]'), b = boxes();
    if (all) { var on = b.filter(function (x) { return x.checked; }).length; all.checked = !!b.length && on === b.length; all.indeterminate = on > 0 && on < b.length; }
    var apply = document.querySelector('[data-stash-apply]');
    if (apply) apply.disabled = !kept.length;
  }
  function set(id, on) {
    var i = kept.indexOf(id);
    if (on && i === -1) kept.push(id);
    if (!on && i !== -1) kept.splice(i, 1);
  }
  function restore() { boxes().forEach(function (b) { if (kept.indexOf(b.value) !== -1) b.checked = true; }); show(); }
  //(the stash's card is drawn again from the server now and then, scan_start.html: its boxes checked again)
  document.addEventListener('qgen-stash-redrawn', restore);
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (t.matches && t.matches('input.stash-pick')) {
      set(t.value, t.checked); save(); show();
      //(in the Checked folder, one unchecked leaves it at once, not at the next reload: the critic, 2026-10-24)
      if (!t.checked && /[?&]stash=checked/.test(location.search)) { var tr = t.closest('tr'); if (tr) tr.hidden = true; }
    }
    if (t.matches && t.matches('[data-stash-all]')) { boxes().forEach(function (b) { b.checked = t.checked; set(b.value, t.checked); }); save(); show(); }
  });
  //(the Checked folder opened with an old address: what's checked now)
  if (/[?&]stash=checked/.test(location.search)) {
    var asked = (new URLSearchParams(location.search).get('checked') || '').split(',').filter(Boolean);
    if (asked.join(',') !== kept.join(',')) {
      location.replace(location.pathname + '?stash=checked&checked=' + kept.join(',') + '#scan-away');
      return;
    }
  }
  function fill(form) {
    var holder = form.querySelector('[data-stash-items]');
    holder.textContent = '';
    kept.forEach(function (id) { var i = document.createElement('input'); i.type = 'hidden'; i.name = 'items'; i.value = id; holder.appendChild(i); });
  }
  function done() {  // (sent: unchecked when the page comes back)
    kept = []; save();
    //(the Checked folder's address names what's checked, and the page is drawn again in place from that address: it
    //follows, or the moved ones stayed listed after a Move, unchecked, with the side's count at 0; the owner, 2026-10-27)
    if (/[?&]stash=checked/.test(location.search)) history.replaceState(history.state, '', location.pathname + '?stash=checked&checked=' + location.hash);
  }
  //(looked up each time: the card, with its dialogs, can be drawn again)
  function el(id) { return document.getElementById(id); }
  document.addEventListener('click', function (e) {
    var apply = el('stash-apply'), many = el('stash-move-many'), gone = el('stash-discard-many');
    if (e.target.closest('[data-stash-apply]')) { if (kept.length && apply) apply.showModal(); return; }
    if (e.target.closest('#stash-apply [data-cancel]')) { apply.close(); return; }
    if (e.target.closest('[data-stash-apply-move]')) {
      apply.close();
      fill(many.querySelector('form'));
      var holder = many.querySelector('[data-folder-pick]'); var old = holder.querySelector('table'); if (old) old.remove();
      many.showModal();
      return;
    }
    if (e.target.closest('[data-stash-apply-discard]')) {
      apply.close();
      var q = 'Move the ' + (kept.length === 1 ? 'checked workbook' : kept.length + ' checked workbooks') + ' to the Trash? You can restore ' + (kept.length === 1 ? 'it' : 'them') + ' there.';
      (window.qgenAsk ? window.qgenAsk(q, 'Move to Trash', true) : Promise.resolve(window.confirm(q))).then(function (yes) {
        if (!yes) return;
        fill(gone); done(); (window.qgenSubmit || function (x) { x.submit(); })(gone);
      });
    }
  });
  document.addEventListener('submit', function (e) {
    var many = e.target.closest('#stash-move-many');
    if (!many) return;
    if (!many.querySelector('input[name=to]:checked')) { e.preventDefault(); e.stopImmediatePropagation(); if (window.qgenPickError) window.qgenPickError(many.querySelector('[data-folder-pick]'), 'Choose a folder first.'); return; }
    done();
  //(first, before the in-place sending (static/js/inplace.js, loaded earlier) sends it with no folder, to Uncategorized:
  //the owner, 2026-10-27)
  }, true);
  restore();
})();
