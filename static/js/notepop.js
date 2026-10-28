/* A note in a card by its icon (the Dashboard's Student notes, Home's Waiting for you; the owner, 2026-10-28): the browser's
 * own pop-over, above a list that scrolls, closed by a click outside it or Esc; placed under the icon, kept inside the window. */
(function () {
  document.addEventListener('toggle', function (e) {
    var pop = e.target;
    if (!pop.matches || !pop.matches('.note-pop') || e.newState !== 'open') return;
    var btn = document.querySelector('[popovertarget="' + pop.id + '"]');
    if (!btn) return;
    var b = btn.getBoundingClientRect(), r = pop.getBoundingClientRect();
    var left = Math.min(Math.max(8, b.right - r.width), innerWidth - r.width - 8);
    var top = b.bottom + 4;
    if (top + r.height > innerHeight - 8 && b.top - r.height - 4 > 8) top = b.top - r.height - 4;
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
  }, true);
})();
