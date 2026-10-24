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
    f.submit();
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
