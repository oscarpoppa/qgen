/* A card that pops over the page from its button (the owner, 2026-10-17): a button with
 * data-popcard="#card" opens that card beside the folder list; its ✕, Esc or a click elsewhere
 * closes it. (A student page's Awards.) */
(function () {
  document.querySelectorAll('[data-popcard]').forEach(function (btn) {
    var card = document.querySelector(btn.dataset.popcard);
    if (!card) return;
    document.body.appendChild(card);
    function place() {
      var side = btn.closest('.folder-side') || (btn.closest('.folder-filter') && btn.closest('.folder-filter').querySelector('.folder-filter-side'));
      var r = btn.getBoundingClientRect(), left = (side ? side.getBoundingClientRect().right : r.right) + 8;
      if (window.innerWidth <= 760) left = 8;
      card.style.left = left + 'px';
      card.style.width = Math.min(900, window.innerWidth - left - 16) + 'px';
      card.style.top = Math.max(8, Math.min(r.top, window.innerHeight - card.offsetHeight - 8)) + 'px';
    }
    function show(open) {
      card.hidden = !open;
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) place();
    }
    btn.addEventListener('click', function () { show(card.hidden); });
    var x = card.querySelector('.pop-card-close');
    if (x) x.addEventListener('click', function () { show(false); btn.focus(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !card.hidden) { show(false); btn.focus(); } });
    document.addEventListener('mousedown', function (e) {
      if (!card.hidden && !card.contains(e.target) && !btn.contains(e.target)) show(false);
    });
    window.addEventListener('resize', function () { if (!card.hidden) place(); });
  });
})();
