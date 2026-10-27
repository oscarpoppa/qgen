/* Scroll areas inside scroll areas (the owner, 2026-10-21): the wheel scrolls the innermost area
 * under the mouse (a Dashboard card's list, a folder's list...); once that one is as far as it goes
 * that way, the next one out takes over at once, out to the page itself, so the bottom of the page
 * can always be reached. (A browser hands over only after the wheel pauses, so it felt stuck.)
 * In a dialog, panel or pop-over the same, out to the dialog's own scrolling, never the page
 * behind it (the owner, 2026-10-21). Not in a box being typed in, nor with Ctrl (zoom) or a
 * sideways scroll. */
(function () {
  var FLOATING = '[id^="dock-"], .dock, dialog, [role="dialog"], .pop, .popover, .scan-pop, .menu, .dropdown, [data-popcard]';
  //the areas that scroll, from the one under the mouse out to the page (or out to the dialog or
  //panel it's in, which keeps the page behind it still); null in a box being typed in
  function chain(el) {
    var out = [];
    if (el && el.closest && el.closest('textarea, select, input')) return null;
    for (; el && el !== document.body && el !== document.documentElement; el = el.parentElement) {
      var cs = getComputedStyle(el);
      if (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1) out.push(el);
      if ((el.matches && el.matches(FLOATING)) || cs.position === 'fixed') return out.length ? out : null;
    }
    out.push(document.scrollingElement || document.documentElement);
    return out;
  }
  function room(el, down) {
    var page = el === (document.scrollingElement || document.documentElement);
    var top = page ? window.scrollY : el.scrollTop, height = page ? window.innerHeight : el.clientHeight;
    return down ? el.scrollHeight - height - top : top;
  }
  document.addEventListener('wheel', function (e) {
    if (e.ctrlKey || e.defaultPrevented || Math.abs(e.deltaX) > Math.abs(e.deltaY) || !e.deltaY) return;
    var areas = chain(e.target);
    if (!areas || !areas.length) return;
    var page = document.scrollingElement || document.documentElement;
    if (areas.length === 1 && areas[0] === page) return;  // only the page: the browser scrolls it as usual
    var down = e.deltaY > 0, to = null;
    for (var i = 0; i < areas.length; i++) if (room(areas[i], down) >= 1) { to = areas[i]; break; }
    //(everything in a dialog as far as it goes: nothing moves, not the page behind it)
    if (!to) { if (areas[areas.length - 1] !== page) e.preventDefault(); return; }
    //(the area under the mouse can still go that way: the browser scrolls it, smoothly, as usual; set by hand it
    //moved a row at a time, the owner 2026-10-27)
    if (to === areas[0]) return;
    //(handing over to an area further out: smoothly too)
    var dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? window.innerHeight : 1);
    e.preventDefault();
    (to === page ? window : to).scrollBy({ top: dy, behavior: 'smooth' });
  }, { passive: false });
})();
