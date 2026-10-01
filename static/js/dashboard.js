/* The Dashboard: refresh the counters and "Right now" every minute while the tab is
 * visible; buttons with data-open-pane open the Notices or Messages panel. */
(function () {
  var box = document.getElementById('dash-now');

  document.addEventListener('click', function (e) {
    var want = e.target.closest('[data-open-pane]');
    if (!want) return;
    var btn = document.querySelector('.dock-btn[data-pane="' + want.dataset.openPane + '"]');
    if (btn && btn.getAttribute('aria-expanded') !== 'true') btn.click();
  });

  if (!box) return;
  function refresh() {
    if (document.hidden) return;
    fetch(box.dataset.url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) { if (html) box.innerHTML = html; }, function () {});
  }
  setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
})();
