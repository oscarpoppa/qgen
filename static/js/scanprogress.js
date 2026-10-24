/* The Dashboard's Scanner card (templates _scan_progress.html, in _dashboard_live.html): while a page is
 * being read, ask every few seconds how far it has got and redraw the card's rows and count (the card itself,
 * open or folded, stays as it is); when nothing is being read, ask now and then. The Dashboard's own
 * refresh redraws the whole card too. */
(function () {
  function card() { return document.getElementById('scan-card'); }
  if (!card()) return;
  function poll() {
    var c = card();
    if (!c) { later(false); return; }
    fetch(c.dataset.url, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (s) {
      c = card();
      if (!c) { later(false); return; }
      var body = c.querySelector('#scan-card-body'), count = c.querySelector('summary .box-count');
      if (body) body.innerHTML = s.html;
      if (count) count.textContent = s.count;
      if (s.reading) c.dataset.reading = '1'; else delete c.dataset.reading;
      //(the card's height changed: the Dashboard lays its cards out again)
      window.dispatchEvent(new Event('resize'));
      //(every few seconds while a page is being read; otherwise now and then, so a scan
      //started in another tab shows up)
      later(s.reading);
    }).catch(function () { later(false); });
  }
  //with instant updates (static/js/push.js) the server says when a page starts, is read or
  //fails, so it asks then; asking now and then stays only as a backup (the owner, 2026-10-20)
  var timer = null;
  function later(reading) {
    clearTimeout(timer);
    timer = setTimeout(poll, window.qgenLive ? 300000 : reading ? 4000 : 30000);
  }
  document.addEventListener('qgen-changed', function () { clearTimeout(timer); timer = setTimeout(poll, 300); });
  later(!!card().dataset.reading);
})();
