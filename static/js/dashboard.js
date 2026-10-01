/* The Dashboard:
 * - each box (details[data-box]) opens and closes; the closed ones are remembered in
 *   this browser, also across the every-minute refresh; "Open all" / "Close all"
 * - the counters and "Right now" refresh every minute while the tab is visible
 * - buttons with data-open-pane open the Notices or Messages panel */
(function () {
  var KEY = 'qgen-dash-closed';
  var box = document.getElementById('dash-now');

  function closed() {
    try { return JSON.parse(localStorage.getItem(KEY) || '[]') || []; } catch (e) { return []; }
  }
  function remember() {
    var shut = [];
    document.querySelectorAll('details[data-box]').forEach(function (d) { if (!d.open) shut.push(d.dataset.box); });
    try { localStorage.setItem(KEY, JSON.stringify(shut)); } catch (e) { /* private window: not remembered */ }
  }
  function apply() {
    //saving again afterwards (the toggle events) writes back the same state
    var shut = closed();
    document.querySelectorAll('details[data-box]').forEach(function (d) { d.open = shut.indexOf(d.dataset.box) === -1; });
  }
  apply();
  document.addEventListener('toggle', function (e) { if (e.target.matches && e.target.matches('details[data-box]')) remember(); }, true);

  document.addEventListener('click', function (e) {
    var all = e.target.closest('[data-dash-boxes]');
    if (all) {
      var open = all.dataset.dashBoxes === 'open';
      document.querySelectorAll('details[data-box]').forEach(function (d) { d.open = open; });
      setTimeout(remember, 0);
      return;
    }
    //a link to a box on this page (e.g. the "due within 2 days" tile) opens it
    var jump = e.target.closest('a[href^="#"]');
    if (jump) {
      var target = document.getElementById(jump.getAttribute('href').slice(1));
      if (target && target.matches('details[data-box]') && !target.open) target.open = true;
    }
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
      .then(function (html) { if (html) { box.innerHTML = html; apply(); } }, function () {});
  }
  setInterval(refresh, 60000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
})();
