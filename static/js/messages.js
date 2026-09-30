/* Check for new messages every 30 seconds: update the menu badge, and on the
 * home page reload the messages box when something new arrives. On a teacher's
 * home page the box shows one conversation; the menu above it switches student. */
(function () {
  var me = document.currentScript || document.querySelector('script[data-poll]');
  var url = me && me.dataset.poll;
  if (!url) return;
  var latest = null;

  //newest messages are at the bottom of the box
  function showNewest() {
    document.querySelectorAll('#messages .thread-scroll').forEach(function (box) { box.scrollTop = box.scrollHeight; });
  }

  function loadPanel(panelUrl) {
    var panel = document.getElementById('messages');
    if (!panel) return Promise.resolve();
    return fetch(panelUrl, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) return;
        panel.outerHTML = html;
        showNewest();
      });
  }

  function refreshPanel() {
    var panel = document.getElementById('messages');
    if (!panel || !panel.dataset.panelUrl) return;
    var typing = panel.querySelector('textarea');
    if (typing && typing.value.trim()) return;  // don't wipe a reply being written
    loadPanel(panel.dataset.panelUrl);
  }

  //teacher: choose whose conversation to show
  document.addEventListener('change', function (e) {
    if (e.target.id !== 'msg-student') return;
    var panel = document.getElementById('messages');
    var typing = panel && panel.querySelector('textarea');
    if (typing && typing.value.trim() && !confirm('Discard the message you were writing?')) {
      e.target.value = new URLSearchParams(panel.dataset.panelUrl.split('?')[1] || '').get('student');
      return;
    }
    var id = e.target.value;
    loadPanel(e.target.dataset.panel + '?student=' + encodeURIComponent(id)).then(function () {
      //a reload keeps this conversation open
      var u = new URL(window.location.href);
      u.searchParams.set('student', id);
      history.replaceState(null, '', u.pathname + u.search + u.hash);
      var sel = document.getElementById('msg-student');
      if (sel) sel.focus();
    });
  });

  function check() {
    if (document.hidden) return;
    fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (res) {
      if (!res) return;
      document.querySelectorAll('.nav-unread').forEach(function (b) {
        b.textContent = res.unread;
        b.hidden = !res.unread;
      });
      if (res.latest !== undefined) {
        if (latest !== null && res.latest !== latest) refreshPanel();
        latest = res.latest;
      }
    }, function () {});
  }

  showNewest();
  check();
  setInterval(check, 30000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) check(); });
})();
