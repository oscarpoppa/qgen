/* People (the owner, 2026-10-21): every name in the list as wide as the longest one shown, so the
 * Teacher badge sits just after the names and still lines up down the column (app.css,
 * .people-table .box-title). Measured again when the list is filtered or the window changes. */
(function () {
  function fit() {
    document.querySelectorAll('.people-table').forEach(function (t) {
      t.style.removeProperty('--name-w');
      var w = 0;
      t.querySelectorAll('.person .box-title').forEach(function (n) {
        if (n.offsetParent) w = Math.max(w, n.getBoundingClientRect().width);
      });
      if (w) t.style.setProperty('--name-w', Math.ceil(w) + 'px');
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fit); else fit();
  window.addEventListener('load', fit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  window.addEventListener('resize', function () { clearTimeout(fit._t); fit._t = setTimeout(fit, 150); });
  document.addEventListener('qgen-filtered', fit);
  document.addEventListener('toggle', function () { setTimeout(fit, 0); }, true);
})();
