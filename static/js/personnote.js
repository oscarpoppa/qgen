/* Teachers' notes: a person's on People (the owner, 2026-10-27), and a problem's, quiz's, picture's or file's, or workbook's
 * (2026-10-28); Student History's Note to the Student. Each is an icon with the row's icons (the owner, 2026-10-29, To do 77),
 * a gold sticky note with a star when there's a note, opening the note in a dialog with Save and Cancel (the small mark by the name is gone: the owner, 2026-10-29).
 * Teachers only (the routes check); every teacher sees the same notes. A Trash message's card (trash_note_mark) still saves
 * itself a moment after typing stops. */
(function () {
  var timers = new WeakMap();
  function csrf() { var m = document.querySelector('meta[name="csrf-token"]'); return m ? m.content : ''; }
  function save(box) {
    var status = box.parentElement.querySelector('.person-note-status');
    var text = box.value.trim();
    status.textContent = 'Saving…';
    fetch(box.dataset.noteUrl, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify({ note: box.value }) })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .then(function (res) {
        if (!res.ok) { status.textContent = res.error || 'Not saved. Please try again.'; status.classList.add('error'); return; }
        status.classList.remove('error');
        status.textContent = 'Saved · ' + res.changed;
      }, function () { status.textContent = 'Not saved: no connection. Please try again.'; status.classList.add('error'); });
  }
  document.addEventListener('input', function (e) {
    var box = e.target;
    if (!box.matches || !box.matches('textarea.person-note-text')) return;
    clearTimeout(timers.get(box));
    timers.set(box, setTimeout(function () { save(box); }, 800));
  });
  //(leaving the box saves at once what's still waiting)
  document.addEventListener('focusout', function (e) {
    var box = e.target;
    if (!box.matches || !box.matches('textarea.person-note-text') || !timers.get(box)) return;
    clearTimeout(timers.get(box)); timers.delete(box);
    save(box);
  });

  /* the note's dialog: its heading, the note, when it was last changed, Save and Cancel (the answer first, Cancel last, as in
   * every dialog); Save closes it once the note is kept, and says so in the dialog when it isn't */
  var dlg = null, opener = null;
  function build() {
    dlg = document.createElement('dialog');
    dlg.className = 'ask note-dialog';
    dlg.setAttribute('aria-labelledby', 'note-dialog-head');
    dlg.innerHTML = '<p id="note-dialog-head" class="note-dialog-head"></p>'
      + '<textarea class="note-dialog-text" rows="6" aria-labelledby="note-dialog-head"></textarea>'
      + '<p class="small muted note-dialog-status" aria-live="polite"></p><div class="btn-row">'
      + '<button type="button" class="btn note-save">Save</button>'
      + '<button type="button" class="btn btn-secondary note-cancel" title="Don\'t do it; nothing changes">Cancel</button></div>';
    document.body.appendChild(dlg);
    dlg.querySelector('.note-cancel').addEventListener('click', function () { dlg.close(); });
    dlg.querySelector('.note-save').addEventListener('click', keep);
    dlg.addEventListener('close', function () { if (opener && opener.isConnected) opener.focus(); opener = null; });
  }
  function open(btn) {
    if (!dlg) build();
    opener = btn;
    var text = dlg.querySelector('textarea'), status = dlg.querySelector('.note-dialog-status');
    dlg.querySelector('.note-dialog-head').textContent = btn.dataset.noteHeading;
    text.value = btn.dataset.noteText || '';
    text.placeholder = btn.dataset.notePlaceholder || '';
    text.maxLength = +btn.dataset.noteMax || 4000;
    status.textContent = btn.dataset.noteStatus || '';
    status.classList.remove('error');
    dlg.querySelector('.note-save').disabled = false;
    dlg.showModal();
    text.focus();
    text.setSelectionRange(text.value.length, text.value.length);
  }
  function keep() {
    var btn = opener, text = dlg.querySelector('textarea'), status = dlg.querySelector('.note-dialog-status');
    var save = dlg.querySelector('.note-save');
    if (!btn) return;
    save.disabled = true;
    status.classList.remove('error');
    status.textContent = 'Saving…';
    function fail(why) { status.textContent = why; status.classList.add('error'); save.disabled = false; }
    fetch(btn.dataset.noteUrl, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() }, body: JSON.stringify({ note: text.value }) })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); })
      .then(function (res) {
        if (!res.ok) { fail(res.error || 'Not saved. Please try again.'); return; }
        var kept = text.value.trim();
        btn.dataset.noteText = kept;
        btn.dataset.noteStatus = res.changed || '';
        btn.classList.toggle('has-note', !!kept);
        dlg.close();
      }, function () { fail('Not saved: no connection. Please try again.'); });
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('button.note-open');
    if (!btn) return;
    e.preventDefault();
    open(btn);
  });
})();
