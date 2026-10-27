/* A person's notes on People (the owner, 2026-10-27): the open row's Notes card saves itself a moment after typing stops,
 * no button and no reload, and says so under the box. The small note mark by the name follows. Teachers only (the route
 * checks); every teacher sees the same notes. */
(function () {
  var timers = new WeakMap();
  function csrf() { var m = document.querySelector('meta[name="csrf-token"]'); return m ? m.content : ''; }
  function mark(box, text) {
    var row = box.closest('details.row-fold'), line = row && row.querySelector(':scope > summary .person-line');
    if (!line) return;
    //(its place is always there, empty when there's no note, so the marks line up down the column)
    var m = line.querySelector('.person-note-mark');
    if (!m) { m = document.createElement('span'); line.appendChild(m); }
    if (!text) {
      m.className = 'person-note-mark person-slot'; m.innerHTML = ''; m.removeAttribute('title'); m.removeAttribute('role');
      m.removeAttribute('aria-label'); m.setAttribute('aria-hidden', 'true');
      return;
    }
    m.className = 'person-note-mark'; m.removeAttribute('aria-hidden'); m.setAttribute('role', 'img'); m.setAttribute('aria-label', 'Has a note');
    if (!m.innerHTML) m.innerHTML = window.qgenIcon ? window.qgenIcon('lc-sticky-note') : '';
    m.title = 'Note: ' + text.split('\n')[0].slice(0, 120);
  }
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
        mark(box, text);
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
})();
