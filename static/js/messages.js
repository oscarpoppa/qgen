/* The side panels on every page: Notices (automatic: quiz assigned, handed in,
 * graded...) and Messages (the conversation). Each can be shown or hidden with
 * its button in the top bar; the choice is remembered in this browser.
 *
 * The page asks whether anything new has arrived the moment the server says something
 * changed (push.js), or every 30 seconds (Technical settings) when it can't: the buttons'
 * counts update, an open panel reloads, and a hidden one gets a pop-up and a
 * pulsing button. Opening a panel marks what it shows as seen.
 *
 * The same check-in keeps the page itself up to date: a page that names what it shows
 * (<body data-watch>, see app/live.py) reloads when that changes, keeping its place, or,
 * when someone is typing on it, offers a Refresh button instead. */
(function () {
  var me = document.currentScript || document.querySelector('script[data-poll]');
  var pollUrl = me && me.dataset.poll;
  //how often to check in (Technical settings), 30 seconds if not given
  var every = Math.max(10000, +(me && me.dataset.every) || 30000);
  var dock = document.getElementById('dock');
  if (!pollUrl || !dock) return;
  //just signed in: the first check-in says what arrived while away
  var welcome = me.hasAttribute('data-welcome');

  var root = document.documentElement;
  var PANES = ['notices', 'messages'];
  var latest = { messages: null, notices: null };
  //this page's contents, as drawn (app/live.py); changes are noticed at each check-in
  var watchKey = document.body.dataset.watch || '', watched = document.body.dataset.watchState || null;
  var edited = false;  // something typed or chosen on the page itself (not in the panels)
  //what each panel shows (pins, deletions...): an open panel reloads when it changes
  var shown = { messages: null, notices: null };
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
  //pinned: the panels sit beside the page and stay as left (wide screens; base.html sets it
  //before the page draws). Otherwise they slide over the page and start closed on each page.
  var justOpened = false;
  //(each panel has its own pin: Notices and Messages are pinned or not separately; the owner, 2026-10-23)
  function pinned(p) { return root.classList.contains('dock-pinned-' + p) && !narrow.matches; }
  function paneOf(btn) { var d = btn.closest('.dock-pane'); return d ? d.id.replace(/^dock-/, '') : null; }

  //the top bar's height, so the panels start right under it
  function measure() {
    var bar = document.querySelector('.topbar');
    if (bar) root.style.setProperty('--topbar-h', bar.offsetHeight + 'px');
    placeDock();
  }
  //(the panels start where the top bar ends on screen: below the sandbox's yellow line too, at
  //the top of the page, and right under the bar once it's scrolled away: the owner, 2026-10-15)
  function placeDock() {
    var bar = document.querySelector('.topbar');
    if (bar) root.style.setProperty('--dock-top', Math.max(0, Math.round(bar.getBoundingClientRect().bottom)) + 'px');
  }
  window.addEventListener('scroll', placeDock, { passive: true });

  function syncButtons() {
    PANES.forEach(function (p) {
      document.querySelectorAll('.dock-btn[data-pane="' + p + '"]').forEach(function (b) {
        b.setAttribute('aria-expanded', isOpen(p) ? 'true' : 'false');
        if (isOpen(p)) b.classList.remove('pulse');
      });
    });
    document.querySelectorAll('.dock-pin').forEach(function (b) {
      var on = root.classList.contains('dock-pinned-' + paneOf(b));
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      var say = on ? 'Let this panel slide over the page (it closes when you click the page)' : 'Keep this panel beside the page';
      b.title = say;
      b.setAttribute('aria-label', say);
    });
    dock.hidden = !PANES.some(isOpen);
  }

  function setOpen(p, open) {
    //on phones and small windows one panel at a time, so the conversation has room
    if (open && narrow.matches) PANES.forEach(function (q) { if (q !== p) root.classList.remove('dock-' + q); });
    root.classList.toggle('dock-' + p, open);
    //the click that opened it (from a button anywhere, e.g. the Dashboard's "Message students")
    //isn't a click on the page that closes it again
    if (open) { justOpened = true; setTimeout(function () { justOpened = false; }, 0); }
    //pinned panels are remembered; panels that slide over the page are opened as needed
    if (pinned(p)) store('qgen-dock-' + p, open ? 'open' : 'closed');
    syncButtons();
    if (open) {
      //its pop-ups are answered; opening Notices with its button (or a pop-up's) marks them seen
      document.querySelectorAll('.toast-' + p).forEach(function (t) { t.remove(); });
      load(p, true);
    }
    //the conversation's panel changed size: keep the newest message in view
    if (isOpen('messages')) requestAnimationFrame(showNewest);
  }

  /* ---------- loading a panel ---------- */

  function paneUrl(p, markSeen) {
    var url = pane(p).dataset.url;
    if (p === 'notices') return markSeen ? url + '?seen=1' : url;
    var student = p === 'messages' && stored('qgen-dock-view');
    return student ? url + '?student=' + encodeURIComponent(student) : url;
  }

  function showNewest() {
    var box = pane('messages').querySelector('.thread-scroll');
    if (box) box.scrollTop = box.scrollHeight;
  }

  //markSeen: the person opened the panel themselves (only Notices uses it: loading it
  //otherwise, e.g. because a notice arrived while it was open, leaves new ones new)
  //(a reply half-written in Messages is put back after loading, as long as it's still the
  //same conversation: switching to another one asks first, see showStudent's callers)
  var drawnView = null;
  function load(p, markSeen) {
    var body = pane(p).querySelector('.dock-body');
    var view = p === 'messages' ? stored('qgen-dock-view') : null;
    var typing = null;
    if (p === 'messages' && busyTyping()) {
      //the reply and its form's choices ("Send to" teachers, "Pin it")
      typing = { view: drawnView, text: pane(p).querySelector('textarea').value, checks: {} };
      body.querySelectorAll('input[type=checkbox][name], input[type=radio][name]').forEach(function (i) {
        typing.checks[i.name + '=' + i.value] = i.checked;
      });
    }
    return fetch(paneUrl(p, markSeen), { credentials: 'same-origin' })
      .then(function (r) {
        //(signed out meanwhile: the answer is the login page. The whole page goes there instead,
        //never the login page inside the panel, where signing in went wrong: the owner, 2026-10-22)
        if (r.redirected && /\/login(\?|$)/.test(new URL(r.url).pathname + new URL(r.url).search.slice(0, 1))) {
          window.location.reload();
          return null;
        }
        return r.ok ? r.text() : null;
      })
      .then(function (html) {
        if (html === null) { body.innerHTML = '<p class="muted small">Couldn\'t load this. Please reload the page.</p>'; return; }
        body.innerHTML = html;
        loaded[p] = true;
        if (p === 'messages') {
          if (typing && typing.view === view) {
            var t = body.querySelector('textarea');
            if (t) t.value = typing.text;
            body.querySelectorAll('input[type=checkbox][name], input[type=radio][name]').forEach(function (i) {
              var k = i.name + '=' + i.value;
              if (k in typing.checks) i.checked = typing.checks[k];
            });
          }
          drawnView = view;
        }
        if (p === 'messages') { splitFit(); showNewest(); }
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
    var pin = e.target.closest('.dock-pin');
    if (pin) {
      var which = paneOf(pin);
      var on = !root.classList.contains('dock-pinned-' + which);
      root.classList.toggle('dock-pinned-' + which, on);
      store('qgen-dock-pinned-' + which, on ? '1' : '0');  // (unpinned until pinned: base.html)
      //pinning keeps this panel as it is now
      store('qgen-dock-' + which, on && isOpen(which) ? 'open' : null);
      syncButtons();
      if (isOpen('messages')) requestAnimationFrame(showNewest);
      return;
    }
    var btn = e.target.closest('.dock-btn, .dock-close');
    if (btn) {
      var p = btn.dataset.pane;
      setOpen(p, btn.classList.contains('dock-close') ? false : !isOpen(p));
      if (isOpen(p)) pane(p).querySelector('.dock-head h2').focus();
      return;
    }
    var open = e.target.closest('.toast-open');
    if (open) {
      //a message from another teacher: open the panel on that conversation (a reply half-written
      //to someone else: asked first, as when switching students; kept if they say no)
      var toast = open.closest('.toast'), view = open.dataset.view, pane_ = open.dataset.pane;
      var go = function (switchTo) {
        if (switchTo) store('qgen-dock-view', view);
        setOpen(pane_, true);
        toast.remove();
      };
      if (!view || !busyTyping() || view === drawnView) { go(!!view); return; }
      ask('Discard the message you were writing?', 'Discard').then(function (yes) { go(yes); });
      return;
    }
    var dismiss = e.target.closest('.toast-close');
    if (dismiss) dismiss.closest('.toast').remove();
  });

  //a click on the page closes panels that slide over it (not pinned); a click on a pop-up,
  //a dialog, the menus, or Messages with a reply half-written leaves them be
  document.addEventListener('click', function (e) {
    if (justOpened || !PANES.some(function (q) { return isOpen(q) && !pinned(q); }) || !e.target.closest || !document.contains(e.target)) return;
    if (e.target.closest('.dock, .dock-buttons, .toasts, dialog, nav.nav, details.menu, .floating-menu, .nav-toggle')) return;
    PANES.forEach(function (q) { if (isOpen(q) && !pinned(q) && !(q === 'messages' && busyTyping())) setOpen(q, false); });
  });

  document.addEventListener('keydown', function (e) {
    //Esc closes a panel that covers the page (not pinned, or a phone)
    if (e.key !== 'Escape') return;
    var inPane = e.target.closest && e.target.closest('.dock-pane');
    //(a pinned panel stays; its ✕ closes it)
    if (inPane && !pinned(inPane.id.replace('dock-', ''))) {
      var p = inPane.id.replace('dock-', '');
      setOpen(p, false);
      var b = document.querySelector('.dock-btn[data-pane="' + p + '"]');
      if (b) b.focus();
    }
  });

  //a link to a student's messages (/messages/<id>: People's speech bubble, a student page, the
  //inbox...) opens this panel on that student, over the page you're on, instead of a page of its
  //own; so does ?msg=<id> in the address (the old page's address sends you back with it) (the
  //owner, 2026-10-19)
  function openStudent(id) {
    var go = function () { store('qgen-dock-view', String(id)); if (isOpen('messages')) load('messages'); else setOpen('messages', true);
      setTimeout(function () { var t = pane('messages').querySelector('textarea'); if (t) t.focus(); }, 400); };
    if (!busyTyping() || String(id) === String(drawnView)) { go(); return; }
    ask('Discard the message you were writing?', 'Discard').then(function (yes) { if (yes) go(); });
  }
  if (pane('messages')) {
    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a[href]');
      if (!a || e.ctrlKey || e.metaKey || e.shiftKey || a.target === '_blank') return;
      var m = /^\/messages\/(\d+)$/.exec(a.pathname || '');
      if (!m || a.origin !== location.origin) return;
      e.preventDefault();
      openStudent(m[1]);
    });
    var asked = new URLSearchParams(location.search).get('msg');
    if (asked && /^\d+$/.test(asked)) {
      var u = new URL(location.href); u.searchParams.delete('msg');
      history.replaceState(history.state, '', u.pathname + u.search + u.hash);
      openStudent(asked);
    }
  }

  //teacher: show everyone's messages ('all') or one student's conversation
  function showStudent(choice, focus) {
    store('qgen-dock-view', choice);
    return load('messages').then(function () {
      var el = focus === 'reply' ? pane('messages').querySelector('textarea') : document.getElementById('msg-student');
      if (el) el.focus();
    });
  }
  function ask(q, ok) { return window.qgenAsk ? window.qgenAsk(q, ok) : Promise.resolve(window.confirm(q)); }
  document.addEventListener('change', function (e) {
    if (e.target.id !== 'msg-student') return;
    var sel = e.target;
    if (!busyTyping()) { showStudent(sel.value); return; }
    ask('Discard the message you were writing?', 'Discard').then(function (yes) {
      if (yes) showStudent(sel.value); else sel.value = sel.dataset.current;
    });
  });
  //"Reply to …" on a message in the all-messages view, and "← All messages"
  document.addEventListener('click', function (e) {
    var b = e.target.closest('#dock-messages .show-student');
    if (!b) return;
    var go = function () { showStudent(b.dataset.student, b.dataset.student === 'all' ? null : 'reply'); };
    if (!busyTyping()) { go(); return; }
    ask('Discard the message you were writing?', 'Discard').then(function (yes) { if (yes) go(); });
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

  //clicking a new notice (or its Open link) marks that one seen; the panel then shows it as read
  document.addEventListener('click', function (e) {
    var li = e.target.closest('#dock-notices .notice[data-seen-url]');
    if (!li || e.target.closest('form')) return;
    var data = new FormData();
    var token = document.querySelector('meta[name=csrf-token]');
    if (token) data.append('csrf_token', token.content);
    var url = li.dataset.seenUrl;
    li.removeAttribute('data-seen-url');
    li.classList.remove('notice-new');
    //keepalive: the Open link may be leaving the page
    fetch(url, { method: 'POST', body: data, credentials: 'same-origin', keepalive: true,
                 headers: { 'X-Requested-With': 'fetch' } })
      .then(function () { if (document.contains(li)) load('notices'); }, function () {});
  });

  //deleting, clearing notices and pinning inside a panel: done without leaving the page,
  //then that panel reloads (confirm.js has already asked "are you sure?" where needed)
  document.addEventListener('submit', function (e) {
    var form = e.target;
    var inPane = form.matches('.dock-form') && form.closest('.dock-pane');
    if (!inPane) return;
    e.preventDefault();
    var p = inPane.id.replace('dock-', '');
    var button = form.querySelector('button');
    if (button) button.disabled = true;
    fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin',
                         headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: 'The page is out of date. Please reload it and try again.' }; }); })
      .then(function (res) {
        if (!res.ok) window.qgenSay(res.error || 'That didn\'t work. Please try again.', 'error');
        load(p);
      }, function () {
        window.qgenSay('Couldn\'t reach the server. Please try again.', 'error');
        if (button) button.disabled = false;
      });
  });

  //an announcement sent to several students: its ✕ asks once, with both choices and Cancel;
  //the answer sends the matching small form (the owner, 2026-10-19)
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-ann-del]');
    if (!b || !window.qgenChoose) return;
    e.preventDefault();
    var wrap = b.parentNode, who = b.dataset.who, n = b.dataset.n;
    window.qgenChoose('Delete this announcement? This can\u2019t be undone.', [
      { value: 'one', label: 'Only from ' + who, title: 'Delete it from ' + who + '\u2019s messages; the others keep it' },
      { value: 'all', label: 'From all ' + n + ' students', danger: true, title: 'Delete every copy of this announcement' }
    ]).then(function (v) {
      if (!v) return;
      var f = wrap.querySelector(v === 'all' ? 'form[data-ann-all]' : 'form[data-ann-one]');
      if (f.requestSubmit) f.requestSubmit(); else f.submit();
    });
  });
  //an announcement's ✕ opens a small menu: keep it in view, one at a time, and close it
  //when clicking elsewhere
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (!d.matches || !d.matches('details.msg-x-wrap') || !d.open) return;
    document.querySelectorAll('details.msg-x-wrap[open]').forEach(function (o) { if (o !== d) o.open = false; });
    var menu = d.querySelector('.msg-del-choices');
    if (menu) menu.scrollIntoView({ block: 'nearest' });
  }, true);
  document.addEventListener('click', function (e) {
    document.querySelectorAll('details.msg-x-wrap[open]').forEach(function (d) { if (!d.contains(e.target)) d.open = false; });
  });

  /* ---------- something new while a panel is hidden ---------- */

  var recentToasts = [];  // shown in the last few seconds: carried over if the page reloads itself
  //a student's quiz page (data-quiet): nothing pops up or pulses; the buttons' counts still go up
  var quiet = root.hasAttribute('data-quiet');
  function toast(p, info) {
    var box = document.getElementById('toasts');
    if (!box || !info || quiet) return;
    recentToasts.push({ p: p, info: info, at: Date.now() });
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
                  + '<button type="button" class="btn btn-secondary btn-sm toast-close" title="Hide this pop-up">Dismiss</button>';
    row.querySelector('.toast-open').dataset.pane = p;
    if (info.view) row.querySelector('.toast-open').dataset.view = info.view;
    row.querySelector('.toast-open').textContent = p === 'messages' ? 'Open messages' : 'Open notices';
    row.querySelector('.toast-open').title = p === 'messages' ? 'Show the messages panel to read it' : 'Show the notices panel to read it';
    t.appendChild(title); t.appendChild(text); t.appendChild(row);
    box.appendChild(t);
    while (box.children.length > 3) box.removeChild(box.firstChild);
    setTimeout(function () { if (t.parentNode) t.remove(); }, 15000);
  }

  //"Welcome back": what's waiting, with a button for each panel that has something
  function welcomeBack(unread, notices) {
    var box = document.getElementById('toasts');
    if (!box || !(unread || notices) || quiet) return;
    var t = document.createElement('div');
    t.className = 'toast toast-notices';
    var title = document.createElement('strong');
    title.textContent = 'Welcome back';
    var parts = [];
    if (notices) parts.push(notices + ' new notice' + (notices === 1 ? '' : 's'));
    if (unread) parts.push(unread + ' new message' + (unread === 1 ? '' : 's'));
    var text = document.createElement('div');
    text.className = 'toast-text';
    text.textContent = 'While you were away: ' + parts.join(' and ') + '.';
    var row = document.createElement('div');
    row.className = 'btn-row';
    [['notices', notices, 'Open notices'], ['messages', unread, 'Open messages']].forEach(function (x) {
      if (!x[1]) return;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-sm toast-open';
      b.dataset.pane = x[0];
      b.textContent = x[2];
      b.title = x[0] === 'messages' ? 'Show the messages panel to read your new messages' : 'Show the notices panel to read your new notices';
      row.appendChild(b);
    });
    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn btn-secondary btn-sm toast-close';
    close.textContent = 'Dismiss';
    close.title = 'Hide this pop-up';
    row.appendChild(close);
    t.appendChild(title); t.appendChild(text); t.appendChild(row);
    box.appendChild(t);
    //(gone after 30 seconds if it isn't dismissed or opened first: the owner, 2026-10-28; it stayed until then)
    setTimeout(function () { if (t.parentNode) t.remove(); }, 30000);
  }

  function pulse(p) {
    if (quiet) return;
    document.querySelectorAll('.dock-btn[data-pane="' + p + '"]').forEach(function (b) {
      b.classList.remove('pulse');
      void b.offsetWidth;  // restart the animation
      b.classList.add('pulse');
    });
  }

  /* ---------- keeping the page itself up to date ---------- */

  var SCROLL = 'qgen-live-scroll', TOASTS = 'qgen-live-toasts';
  document.addEventListener('input', noteEdit, true);
  document.addEventListener('change', noteEdit, true);
  function noteEdit(e) {
    if (e.target.closest && !e.target.closest('.dock')) edited = true;
  }
  //reloading now would lose something: typing on the page or in Messages, or a question open
  function busy() {
    return edited || busyTyping() || !!document.querySelector('dialog[open]');
  }
  function reloadHere() {
    //(a folder page swaps its list in place, nothing blanks out: static/js/folders.js; the owner, 2026-10-25)
    //(any page made of lists, and the Dashboard, the same way: static/js/inplace.js; the owner, 2026-10-27)
    if (!document.body.hasAttribute('data-watch-post') && window.qgenRedraw && window.qgenRedraw()) {
      var bar = document.getElementById('live-bar');
      if (bar) bar.remove();
      return;
    }
    try { sessionStorage.setItem(SCROLL, location.pathname + location.search + '|' + Math.round(window.scrollY)); } catch (e) {}
    //a pop-up that just arrived (often what changed the page) is shown again after the reload
    var keep = recentToasts.filter(function (t) { return Date.now() - t.at < 15000; });
    try { if (keep.length) sessionStorage.setItem(TOASTS, JSON.stringify(keep)); } catch (e) {}
    //a page drawn after sending a form is fetched afresh (reloading would send the form again)
    if (document.body.hasAttribute('data-watch-post')) window.location.replace(window.location.href);
    else window.location.reload();
  }
  function offerRefresh() {
    if (document.getElementById('live-bar')) return;
    var box = document.getElementById('toasts');
    if (!box) return;
    var t = document.createElement('div');
    t.className = 'toast toast-live';
    t.id = 'live-bar';
    var text = document.createElement('div');
    text.className = 'toast-text';
    text.textContent = document.body.dataset.watchNote || 'This page has changed since you opened it.';
    var row = document.createElement('div');
    row.className = 'btn-row';
    var go = document.createElement('button');
    go.type = 'button';
    go.className = 'btn btn-sm';
    go.textContent = document.body.dataset.watchButton || 'Refresh';
    go.title = 'Load the page again to see what changed';
    go.addEventListener('click', reloadHere);
    var later = document.createElement('button');
    later.type = 'button';
    later.className = 'btn btn-secondary btn-sm';
    later.textContent = 'Not now';
    later.title = 'Keep this page as it is; hide this pop-up';
    later.addEventListener('click', function () { t.remove(); });
    row.appendChild(go); row.appendChild(later);
    t.appendChild(text); t.appendChild(row);
    box.appendChild(t);
  }
  function pageChanged() {
    if (document.body.hasAttribute('data-watch-ask') || busy()) offerRefresh();
    else reloadHere();
  }
  //back where it was after a reload of its own
  window.addEventListener('load', function () {
    var carried = null;
    try { carried = JSON.parse(sessionStorage.getItem(TOASTS) || 'null'); sessionStorage.removeItem(TOASTS); } catch (e) {}
    (carried || []).forEach(function (t) { toast(t.p, t.info); pulse(t.p); });
    var saved = null;
    try { saved = sessionStorage.getItem(SCROLL); sessionStorage.removeItem(SCROLL); } catch (e) {}
    if (!saved) return;
    var cut = saved.lastIndexOf('|');
    if (saved.slice(0, cut) === location.pathname + location.search) window.scrollTo(0, +saved.slice(cut + 1));
  });

  //the tab's dots (static/js/tabdots.js)
  function tabDots(fresh, started) { if (window.qgenTabDots) window.qgenTabDots(fresh, started); }

  function check() {
    if (document.hidden) return;
    lastCheck = Date.now();
    fetch(pollUrl + (watchKey ? (pollUrl.indexOf('?') < 0 ? '?' : '&') + 'watch=' + encodeURIComponent(watchKey) : ''), { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (res) {
      if (!res) return;
      var counts = [['.nav-unread', res.unread], ['.nav-notices', res.notices]];
      if (typeof res.review === 'number') counts.push(['.nav-review', res.review]);  // teachers: Grading
      if (typeof res.online === 'number') {  // teachers: who's online (always shown, never hidden)
        document.querySelectorAll('.nav-online').forEach(function (b) { b.textContent = res.online; });
      }
      counts.forEach(function (pair) {
        document.querySelectorAll(pair[0]).forEach(function (b) {
          b.textContent = pair[1];
          b.hidden = !pair[1];
          if (pair[0] === '.nav-review') b.setAttribute('aria-label', pair[1] + ' waiting for grading');
        });
      });
      if (welcome) {
        welcome = false;
        welcomeBack(isOpen('messages') ? 0 : res.unread, isOpen('notices') ? 0 : res.notices);
      }
      if (res.tab) tabDots(res.tab[0], res.tab[1]);
      //the small circles by the name: new (gold), in progress (blue), due soon (red), each only above 0
      if (res.dots) {
        document.querySelectorAll('.nav-dots').forEach(function (box) {
          box.setAttribute('aria-label', res.dots[0] + ' new, ' + res.dots[1] + ' in progress, ' + res.dots[2] + ' due soon');
          box.querySelectorAll('[data-dot]').forEach(function (d) {
            var n = res.dots[+d.dataset.dot];
            d.textContent = n; d.hidden = !n;
            d.title = n + [' new', ' in progress', ' due soon'][+d.dataset.dot];
          });
        });
      }

      [['messages', res.latest, res.message_preview, res.unread, res.messages_state],
       ['notices', res.latest_notice, res.notice_preview, res.notices, res.notices_state]].forEach(function (x) {
        var p = x[0], id = x[1], info = x[2], count = x[3], state = x[4];
        var first = latest[p] === null;
        var changed = !first && id !== latest[p];  // something new arrived
        var restyled = shown[p] !== null && state !== undefined && state !== shown[p];  // pinned, deleted...
        latest[p] = id;
        if (state !== undefined) shown[p] = state;
        if (isOpen(p)) {
          if ((changed || restyled) && !(p === 'messages' && busyTyping())) load(p);
          //a new notice stays new in an open panel, so it's announced like anywhere else
          if (p === 'notices' && changed && count) { toast(p, info); pulse(p); }
        } else if (changed && count) {
          toast(p, info);
          pulse(p);
        } else if (first && count) {
          pulse(p);  // unread from before this page opened: a nudge, no pop-up
        }
      });
      //what this page shows has changed (assigned, handed in, graded, deleted, opened...)
      if (watchKey && typeof res.watch === 'string' && watched !== null && res.watch !== watched) {
        watched = res.watch;
        pageChanged();
      }
    }, function () {});
  }

  /* ---------- the divider between the two panels ---------- */

  //drag it (or focus it and use the arrow keys) to share the height between Notices and
  //Messages; double-click puts it back. Remembered in this browser (base.html applies it early).
  var SPLIT_DEFAULT = 34;
  function setupSplit() {
    var bar = document.getElementById('dock-split');
    if (!bar) return;
    //each panel keeps its heading and a little of its content (squeezed, Messages scrolls)
    function limits() {
      var h = dock.clientHeight || 1;
      var lo = Math.min(45, 110 / h * 100), hi = Math.max(55, 100 - 200 / h * 100);
      return [lo, hi];
    }
    function current() {
      return pane('notices').getBoundingClientRect().height / (dock.clientHeight || 1) * 100;
    }
    function apply(pct, keep) {
      var l = limits();
      pct = Math.round(Math.min(l[1], Math.max(l[0], pct)) * 10) / 10;
      root.style.setProperty('--dock-split', pct + '%');
      bar.setAttribute('aria-valuenow', Math.round(pct));
      if (keep) store('qgen-dock-split', String(pct));
      if (isOpen('messages')) requestAnimationFrame(showNewest);
    }
    bar.setAttribute('aria-valuemin', '10');
    bar.setAttribute('aria-valuemax', '90');
    bar.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      bar.setPointerCapture(e.pointerId);
      bar.classList.add('dragging');
      root.classList.add('dock-resizing');
      var top = dock.getBoundingClientRect().top, h = dock.clientHeight || 1;
      function move(ev) { apply((ev.clientY - top) / h * 100, false); }
      function up() {
        bar.removeEventListener('pointermove', move);
        bar.removeEventListener('pointerup', up);
        bar.removeEventListener('pointercancel', up);
        bar.classList.remove('dragging');
        root.classList.remove('dock-resizing');
        apply(current(), true);
      }
      bar.addEventListener('pointermove', move);
      bar.addEventListener('pointerup', up);
      bar.addEventListener('pointercancel', up);
    });
    bar.addEventListener('dblclick', function () {
      apply(SPLIT_DEFAULT, false);
      store('qgen-dock-split', null);
    });
    bar.addEventListener('keydown', function (e) {
      var step = { ArrowUp: -5, ArrowDown: 5, PageUp: -15, PageDown: 15 }[e.key];
      if (step) apply(current() + step, true);
      else if (e.key === 'Home') apply(0, true);
      else if (e.key === 'End') apply(100, true);
      else return;
      e.preventDefault();
    });
    //a smaller window, or the conversation's panel just loaded: keep both panels usable
    function fit() {
      if (isOpen('notices') && isOpen('messages') && stored('qgen-dock-split')) apply(current(), false);
    }
    window.addEventListener('resize', fit);
    splitFit = fit;
  }
  var splitFit = function () {};

  /* ---------- what the retired Messages page did (the owner, 2026-10-17) ---------- */

  //"Write to…" and "Pinned": a copy of the panel's box opens over the page (the panel itself
  //reloads as messages arrive, which would close a box inside it)
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-panel-dialog]');
    //(a box on the page itself, Write to…: opened as it is, its folders already set up)
    var onPage = b && document.querySelector('body > dialog#' + b.dataset.panelDialog);
    if (onPage) { onPage.showModal(); countChecked(onPage); return; }
    if (b) {
      var src = pane('messages').querySelector('#' + b.dataset.panelDialog);
      if (!src) return;
      var d = src.cloneNode(true);
      d.removeAttribute('id');
      d.querySelectorAll('[id]').forEach(function (el) { el.id = 'open-' + el.id; });
      d.querySelectorAll('label[for]').forEach(function (l) { l.htmlFor = 'open-' + l.htmlFor; });
      d.querySelectorAll('[aria-labelledby]').forEach(function (el) { el.setAttribute('aria-labelledby', 'open-' + el.getAttribute('aria-labelledby')); });
      if (d.getAttribute('aria-labelledby')) d.setAttribute('aria-labelledby', 'open-' + d.getAttribute('aria-labelledby'));
      document.body.appendChild(d);
      //(its filter bar points at the copy's own list, its ids renamed above: Pinned's, the standard
      //dialog for listed things, the owner 2026-10-21)
      d.querySelectorAll('[data-filter-bar]').forEach(function (bar) {
        if (bar.dataset.filter) bar.dataset.filter = bar.dataset.filter.replace(/#(?!open-)/g, '#open-');
        if (window.qgenFilterBar) window.qgenFilterBar(bar);
      });
      //(its folder list, Showing…'s, set up on the copy: the owner, 2026-10-22)
      d.querySelectorAll('[data-folder-filter]').forEach(function (box) {
        if (window.qgenFolderFilterSetUp) window.qgenFolderFilterSetUp(box);
      });
      //(Showing…: the choice picked is shown when "Show" is pressed, never the moment it is picked: the panel
      //switches to it through its drop-down and the box closes; the owner, 2026-10-23)
      function pickShown() {
        var r = d.querySelector('input[name="show-pick"]:checked'), sel = document.getElementById('msg-student');
        if (r && sel && r.value !== sel.value) {
          sel.value = r.value;
          sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
        d.close();
      }
      d.addEventListener('click', function (ev) { if (ev.target.closest && ev.target.closest('[data-show-pick]')) pickShown(); });
      d.addEventListener('close', function () { d.remove(); b.focus(); });
      d.showModal();
      return;
    }
    var x = e.target.closest('dialog.panel-dialog [data-close]');
    if (x) { x.closest('dialog').close(); return; }
    var f = e.target.closest('dialog.panel-dialog [data-check-ids]');
    if (f) {
      var ids = JSON.parse(f.dataset.checkIds).map(String);
      f.closest('dialog').querySelectorAll('input[name=students]').forEach(function (c) { if (ids.indexOf(c.value) !== -1) c.checked = true; });
    }
  });
  document.addEventListener('change', function (e) {
    if (e.target.name !== 'students') return;
    var d = e.target.closest('dialog.panel-dialog');
    var said = d && d.querySelector('[data-none-checked]');
    if (said) said.hidden = true;
  });
  //nobody checked: say so in the dialog itself, above its buttons (never the browser's alert()
  //pop-up: the code critic, 2026-10-20)
  document.addEventListener('submit', function (e) {
    var d = e.target.closest('dialog.panel-dialog');
    if (!d || !d.querySelector('input[name=students]')) return;
    if (!d.querySelector('input[name=students]:checked')) {
      e.preventDefault();
      //(under the students' filter, the list outlined in red: static/js/fielderror.js, the owner 2026-10-24)
      var pick = d.querySelector('.pick-people');
      if (pick) { window.qgenPickError(pick, 'Check at least one student first.'); return; }
      var said = d.querySelector('[data-none-checked]');
      if (!said) {
        said = document.createElement('p');
        said.className = 'error small';
        said.setAttribute('data-none-checked', '');
        said.setAttribute('role', 'alert');
        said.textContent = 'Check at least one student.';
        var rows = d.querySelectorAll('.btn-row');
        var last = rows[rows.length - 1];
        if (last) last.parentNode.insertBefore(said, last); else d.appendChild(said);
      }
      said.hidden = false;
    }
  });

  /* ---------- start ---------- */

  //the old Messages page's address (and its links) open this panel instead
  if (location.hash === '#messages-panel') {
    if (window.history && history.replaceState) history.replaceState(null, '', location.pathname + location.search);
    if (!isOpen('messages')) setOpen('messages', true);
  }

  measure();
  window.addEventListener('resize', measure);
  //(and whenever the top bar changes height, e.g. its Menu opened on a phone: the panel stayed where the bar had ended
  //and covered the menu, so Menu seemed to do nothing; the owner, 2026-10-27)
  if (window.ResizeObserver && document.querySelector('.topbar')) new ResizeObserver(measure).observe(document.querySelector('.topbar'));
  setupSplit();
  syncButtons();
  PANES.forEach(function (p) { if (isOpen(p)) load(p); });
  if (!PANES.some(isOpen)) check();
  //with instant updates (push.js) the server says when to check; the regular check-in is
  //then only a backup, every few minutes. Without them, every check-in time as before.
  var lastCheck = Date.now(), soonTimer = null, BACKUP = Math.max(every, 300000), GAP = 1500;
  setInterval(function () { if (!window.qgenLive || Date.now() - lastCheck >= BACKUP - 1000) check(); }, every);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) check(); });
  //"something changed": check now, or, right after a check, once the moment has passed
  //(a burst of changes makes one or two check-ins, not one each)
  document.addEventListener('qgen-changed', function () {
    if (soonTimer) return;
    var wait = Math.max(0, lastCheck + GAP - Date.now());
    soonTimer = setTimeout(function () { soonTimer = null; check(); }, wait);
  });
})();
