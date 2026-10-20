/* A scan being read shows how long it has been at it, counting up each second (the "Current
 * scans" table and the Dashboard's scan pop-over: the owner, 2026-10-20). Each .scan-elapsed
 * carries the seconds so far when the page drew it; pages that redraw the pop-over get new ones. */
(function () {
  var start = Date.now();
  function mmss(s) { return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2); }
  function tick() {
    document.querySelectorAll('.scan-elapsed').forEach(function (el) {
      if (!el.dataset.t0) el.dataset.t0 = Date.now();
      var s = (+el.dataset.elapsed || 0) + Math.floor((Date.now() - el.dataset.t0) / 1000);
      el.textContent = ' · ' + mmss(s);
    });
  }
  tick();
  setInterval(tick, 1000);
})();
