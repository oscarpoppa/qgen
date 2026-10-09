/* The Dashboard:
 * - its boxes open, fold and are remembered like every box (static/js/boxes.js), also
 *   across the refresh
 * - everything below the title refreshes (every 30 seconds unless Technical settings
 *   say otherwise) while the tab is visible,
 *   and at once when the tab is shown again, without moving the page
 * - buttons with data-open-pane open the Notices or Messages panel */
(function () {
  var box = document.getElementById('dash-live');

  document.addEventListener('click', function (e) {
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
  //not while a question is being asked ("Unpin this message?"): its form is in the part
  //that refreshes, and a form that's been replaced can't be sent. It refreshes as soon as
  //the question is answered.
  function busy() { return !!document.querySelector('dialog[open]'); }
  var waiting = false;
  function refresh() {
    if (document.hidden) return;
    if (busy()) { waiting = true; return; }
    waiting = false;
    fetch(box.dataset.url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (!html) return;
        if (busy()) { waiting = true; return; }  // a question was asked while it loaded
        //"+N more" lists opened stay open across the refresh
        var more = {};
        box.querySelectorAll('details[data-more]').forEach(function (d) { if (d.open) more[d.dataset.more] = true; });
        //the page keeps its place: until the new boxes are laid out (static/js/masonry.js),
        //the page could be shorter for a moment and the browser would pull the reader up
        var y = window.scrollY, moved = false;
        function mine() { moved = true; }  // the reader scrolling meanwhile: theirs to keep
        ['wheel', 'touchmove', 'keydown', 'mousedown'].forEach(function (t) { window.addEventListener(t, mine, { passive: true }); });
        box.style.minHeight = box.offsetHeight + 'px';
        box.innerHTML = html;
        box.querySelectorAll('details[data-more]').forEach(function (d) { if (more[d.dataset.more]) d.open = true; });
        setTimeout(function () {
          ['wheel', 'touchmove', 'keydown', 'mousedown'].forEach(function (t) { window.removeEventListener(t, mine); });
          box.style.minHeight = '';
          if (!moved && Math.abs(window.scrollY - y) > 1) window.scrollTo(0, y);  // as far as the page now goes
        }, 400);
      }, function () {});
  }
  setInterval(refresh, Math.max(10000, +box.dataset.every || 30000));
  document.addEventListener('close', function () { if (waiting) setTimeout(refresh, 0); }, true);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
})();
