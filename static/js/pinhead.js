/* The page's title line pinned under the top bar (app.css, main > .page-head): its height as --head-h, so what else
 * sticks (the folder list, the editors' Helper...) sits under it, not behind it (the owner, 2026-10-30). 0 when it isn't
 * pinned (a phone) or there is none. */
(function () {
  var root = document.documentElement, head = document.querySelector('main > .page-head');
  function measure() {
    var on = head && getComputedStyle(head).position === 'sticky';
    root.style.setProperty('--head-h', on ? Math.round(head.getBoundingClientRect().height) + 'px' : '0px');
  }
  measure();
  window.addEventListener('resize', measure);
  window.addEventListener('load', measure);
  if (head && window.ResizeObserver) new ResizeObserver(measure).observe(head);
})();
