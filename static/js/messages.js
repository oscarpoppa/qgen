/* The side panels on every page: Notices (automatic: quiz assigned, handed in,
 * graded...) and Messages (the conversation). Each can be shown or hidden with
 * its button in the top bar; the choice is remembered in this browser.
 *
 * Every 30 seconds the page asks whether anything new has arrived: the buttons'
 * counts update, an open panel reloads, and a hidden one gets a pop-up and a
 * pulsing button. Opening a panel marks what it shows as seen. */
(function () {
  var me = document.currentScript || document.querySelector('script[data-poll]');
  var pollUrl = me && me.dataset.poll;
  var dock = document.getElementById('dock');
  if (!pollUrl || !dock) return;

  var root = document.documentElement;
  var PANES = ['notices', 'messages'];
  var latest = { messages: null, notices: null };
  var loaded = { messages: false, notices: false };
  var narrow = window.matchMedia('(max-width: 1000px)');

  function store(key, value) {
    try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch (e) {}
  }
  function stored(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function pane(p) { return document.getElementById('dock-' + p); }
  function isOpen(p) { return root.classList.contains('dock-' + p); }

  //the top bar's height, so the panels start right under it
  function measure() {
    var bar = document.querySelector('.topbar');
    if (bar) root.style.setProperty('--topbar-h', bar.offsetHeight + 'px');
  }

  function syncButtons() {
    PANES.forEach(function (p) {
      document.querySelectorAll('.dock-btn[data-pane="' + p + '"]').forEach(function (b) {
        b.setAttribute('aria-expanded', isOpen(p) ? 'true' : 'false');
        if (isOpen(p)) b.classList.remove('pulse');
      });
    });
    dock.hidden = !PANES.some(isOpen);
  }

  function setOpen(p, open) {
    //on phones and small windows one panel at a time, so the conversation has room
    if (open && narrow.matches) PANES.forEach(function (q) { if (q !== p) root.classList.remove('dock-' + q); });
    root.classList.toggle('dock-' + p, open);
    //remember wide-screen choices; on phones panels are opened as needed
    if (!narrow.matches) store('qgen-dock-' + p, open ? 'open' : 'closed');
    syncButtons();
    if (open) {
      //its pop-ups are answered
      document.querySelectorAll('.toast-' + p).forEach(function (t) { t.remove(); });
      load(p);
    }
    //the conversation's panel changed size: keep the newest message in view
    if (isOpen('messages')) requestAnimationFrame(showNewest);
  }

  /* ---------- loading a panel ---------- */

  function paneUrl(p) {
    var url = pane(p).dataset.url;
    var student = p === 'messages' && stored('qgen-dock-view');
    return student ? url + '?student=' + encodeURIComponent(student) : url;
  }

  function showNewest() {
    var box = pane('messages').querySelector('.thread-scroll');
    if (box) box.scrollTop = box.scrollHeight;
  }

  function load(p) {
    var body = pane(p).querySelector('.dock-body');
    return fetch(paneUrl(p), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (html === null) { body.innerHTML = '<p class="muted small">Couldn\'t load this. Please reload the page.</p>'; return; }
        body.innerHTML = html;
        loaded[p] = true;
        if (p === 'messages') showNewest();
        //opening it marked things seen: the counts change
        check();
      }, function () {});
  }

  function busyTyping() {
    var t = pane('messages').querySelector('textarea');
    return t && t.value.trim();
  }

  /* ---------- clicks ---------- */

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.dock-btn, .dock-close');
    if (btn) {
      var p = btn.dataset.pane;
      setOpen(p, btn.classList.contains('dock-close') ? false : !isOpen(p));
      if (isOpen(p)) pane(p).querySelector('.dock-head h2').focus();
      return;
    }
    var open = e.target.closest('.toast-open');
    if (open) {
      setOpen(open.dataset.pane, true);
      open.closest('.toast').remove();
      return;
    }
    var dismiss = e.target.closest('.toast-close');
    if (dismiss) dismiss.closest('.toast').remove();
  });

  document.addEventListener('keydown', function (e) {
    //Esc closes a panel that covers the page (phones)
    if (e.key !== 'Escape' || !narrow.matches) return;
    var inPane = e.target.closest && e.target.closest('.dock-pane');
    if (inPane) {
      var p = inPane.id.replace('dock-', '');
      setOpen(p, false);
      var b = document.querySelector('.dock-btn[data-pane="' + p + '"]');
      if (b) b.focus();
    }
  });

  //teacher: show everyone's messages ('all') or one student's conversation
  function showStudent(choice, focus) {
    store('qgen-dock-view', choice);
    return load('messages').then(function () {
      var el = focus === 'reply' ? pane('messages').querySelector('textarea') : document.getElementById('msg-student');
      if (el) el.focus();
    });
  }
  document.addEventListener('change', function (e) {
    if (e.target.id !== 'msg-student') return;
    if (busyTyping() && !confirm('Discard the message you were writing?')) {
      e.target.value = e.target.dataset.current;
      return;
    }
    showStudent(e.target.value);
  });
  //"Reply to …" on a message in the all-messages view, and "← All messages"
  document.addEventListener('click', function (e) {
    var b = e.target.closest('#dock-messages .show-student');
    if (!b) return;
    if (busyTyping() && !confirm('Discard the message you were writing?')) return;
    showStudent(b.dataset.student, b.dataset.student === 'all' ? null : 'reply');
  });

  //send from the panel without leaving the page
  document.addEventListener('submit', function (e) {
    var form = e.target.closest('#dock-messages form.reply-box');
    if (!form) return;
    e.preventDefault();
    var button = form.querySelector('button');
    var note = form.querySelector('.send-error') || form.appendChild(Object.assign(document.createElement('div'), { className: 'send-error small', role: 'alert' }));
    note.textContent = '';
    button.disabled = true;
    fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin',
                         headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: 'The page is out of date. Please reload it and try again.' }; }); })
      .then(function (res) {
        if (res.ok) {
          form.querySelector('textarea').value = '';
          load('messages').then(function () {
            var t = pane('messages').querySelector('textarea');
            if (t) t.focus();
          });
        } else {
          note.textContent = res.error || 'That didn\'t send. Please try again.';
        }
      }, function () { note.textContent = 'Couldn\'t reach the server. Please try again.'; })
      .then(function () { button.disabled = false; });
  });

  /* ---------- something new while a panel is hidden ---------- */

  function toast(p, info) {
    var box = document.getElementById('toasts');
    if (!box || !info) return;
    var t = document.createElement('div');
    t.className = 'toast toast-' + p;
    var title = document.createElement('strong');
    title.textContent = p === 'messages' ? 'New message' + (info.from ? ' from ' + info.from : '') : 'New notice';
    var text = document.createElement('div');
    text.className = 'toast-text';
    text.textContent = info.text;
    var row = document.createElement('div');
    row.className = 'btn-row';
    row.innerHTML = '<button type="button" class="btn btn-sm toast-open"></button>'
                  + '<button type="button" class="btn btn-secondary btn-sm toast-close">Dismiss</button>';
    row.querySelector('.toast-open').dataset.pane = p;
    row.querySelector('.toast-open').textContent = p === 'messages' ? 'Open messages' : 'Open notices';
    t.appendChild(title); t.appendChild(text); t.appendChild(row);
    box.appendChild(t);
    while (box.children.length > 3) box.removeChild(box.firstChild);
    setTimeout(function () { if (t.parentNode) t.remove(); }, 15000);
  }

  function pulse(p) {
    document.querySelectorAll('.dock-btn[data-pane="' + p + '"]').forEach(function (b) {
      b.classList.remove('pulse');
      void b.offsetWidth;  // restart the animation
      b.classList.add('pulse');
    });
  }

  var baseTitle = document.title;
  function check() {
    if (document.hidden) return;
    fetch(pollUrl, { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (res) {
      if (!res) return;
      [['.nav-unread', res.unread], ['.nav-notices', res.notices]].forEach(function (pair) {
        document.querySelectorAll(pair[0]).forEach(function (b) { b.textContent = pair[1]; b.hidden = !pair[1]; });
      });
      var waiting = (isOpen('messages') ? 0 : res.unread) + (isOpen('notices') ? 0 : res.notices);
      document.title = (waiting ? '(' + waiting + ') ' : '') + baseTitle;

      [['messages', res.latest, res.message_preview, res.unread], ['notices', res.latest_notice, res.notice_preview, res.notices]].forEach(function (x) {
        var p = x[0], id = x[1], info = x[2], count = x[3];
        var first = latest[p] === null;
        var changed = !first && id !== latest[p];
        latest[p] = id;
        if (isOpen(p)) {
          if (changed && !(p === 'messages' && busyTyping())) load(p);
        } else if (changed && count) {
          toast(p, info);
          pulse(p);
        } else if (first && count) {
          pulse(p);  // unread from before this page opened: a nudge, no pop-up
        }
      });
    }, function () {});
  }

  /* ---------- start ---------- */

  measure();
  window.addEventListener('resize', measure);
  syncButtons();
  PANES.forEach(function (p) { if (isOpen(p)) load(p); });
  if (!PANES.some(isOpen)) check();
  setInterval(check, 30000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) check(); });
})();
