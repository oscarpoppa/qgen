/* A page's one long list as a panel (the owner, 2026-10-17): an element with data-fit-window
 * is no taller than the window has room for below its top, then scrolls inside itself, so the
 * page around it stays put. Short lists keep their own height. Not on phones (the page scrolls). */
(function () {
  function fit() {
    document.querySelectorAll('[data-fit-window]').forEach(function (el) {
      el.style.maxHeight = '';
      el.classList.remove('fit-scroll');
      if (window.innerWidth <= 760) return;
      var top = el.getBoundingClientRect().top + window.scrollY;
      var main = el.closest('main'), gap = main ? parseFloat(getComputedStyle(main).paddingBottom) || 16 : 16;
      el.style.maxHeight = Math.max(240, window.innerHeight - top - gap - 1) + 'px';
      el.classList.add('fit-scroll');
      //(what's below it in its box, a card's padding and border: taken off too, so the page
      //itself doesn't scroll)
      var over = document.documentElement.scrollHeight - window.innerHeight;
      if (over > 0) el.style.maxHeight = Math.max(240, parseFloat(el.style.maxHeight) - over) + 'px';
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fit); else fit();
  window.addEventListener('load', fit);
  window.addEventListener('resize', fit);
})();
