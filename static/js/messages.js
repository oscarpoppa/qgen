/* Check for new messages every 30 seconds: update the menu badge, and on a
 * student's home page reload the messages box when something new arrives. */
(function () {
  var me = document.currentScript || document.querySelector('script[data-poll]');
  var url = me && me.dataset.poll;
  if (!url) return;
  var latest = null;

  function refreshPanel() {
    var panel = document.getElementById('messages');
    if (!panel || !panel.dataset.panelUrl) return;
    var typing = panel.querySelector('textarea');
    if (typing && typing.value.trim()) return;  // don't wipe a reply being written
    fetch(panel.dataset.panelUrl, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) { if (html) panel.outerHTML = html; });
  }

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

  check();
  setInterval(check, 30000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) check(); });
})();
