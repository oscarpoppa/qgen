/* People (the owner, 2026-10-21): every name in the list as wide as the longest one shown, so the
 * Teacher badge sits just after the names and still lines up down the column (app.css,
 * .people-table .box-title). Measured again when the list is filtered or the window changes. */
(function () {
  //(only when what's shown or the window has changed since the last time: the page's opening called this four or five
  //times, each laying out People's ten thousand elements again, most of a second in Firefox; the owner, 2026-10-24)
  function fit() {
    document.querySelectorAll('.people-table').forEach(function (t) {
      var names = Array.prototype.filter.call(t.querySelectorAll('.person .box-title'), function (n) { return !n.closest('[hidden]'); });
      var key = innerWidth + ':' + (document.fonts ? document.fonts.status : '') + ':' + names.length + ':' +
        names.map(function (n) { return n.textContent.length; }).join(',');
      if (t._nameKey === key) return;
      t._nameKey = key;
      t.style.removeProperty('--name-w');
      var w = 0;
      names.forEach(function (n) { w = Math.max(w, n.getBoundingClientRect().width); });
      if (w) t.style.setProperty('--name-w', Math.ceil(w) + 'px');
    });
  }
  //(every reason to look again gathered into one look, a moment later)
  function soon() { clearTimeout(soon._t); soon._t = setTimeout(fit, 0); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fit); else fit();
  window.addEventListener('load', soon);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(soon);
  window.addEventListener('resize', function () { clearTimeout(soon._t); soon._t = setTimeout(fit, 150); });
  document.addEventListener('qgen-filtered', soon);
  document.addEventListener('toggle', soon, true);
})();
