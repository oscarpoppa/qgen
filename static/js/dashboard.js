/* The Dashboard:
 * - its boxes open, fold and are remembered like every box (static/js/boxes.js), also
 *   across the refresh
 * - everything below the title refreshes the moment something on it changes (push.js),
 *   or every 30 seconds (Technical settings) when that can't be known, while the tab is visible,
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
  //(or a note's card is up, Student notes: it would be replaced and close; the owner, 2026-10-28)
  function busy() {
    if (document.querySelector('dialog[open]')) return true;
    try { return !!document.querySelector('.note-pop:popover-open'); } catch (e) { return false; }
  }
  //"Assigned, Still Open"'s two tabs, In Progress and New (the owner, 2026-10-28): the one picked last is
  //remembered in this browser and shown again after every redraw; In Progress when nothing was picked
  function outTab(pick) {
    var want = pick;
    if (!want) { try { want = localStorage.getItem('qgen-dash-out-tab'); } catch (e) { want = null; } }
    if (want !== 'new') want = 'started';
    box.querySelectorAll('[data-out-tab]').forEach(function (a) {
      if (a.dataset.outTab === want) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    box.querySelectorAll('[data-out-list]').forEach(function (l) { l.hidden = l.dataset.outList !== want; });
  }
  box.addEventListener('click', function (e) {
    var a = e.target.closest('[data-out-tab]');
    if (!a) return;
    e.preventDefault();
    try { localStorage.setItem('qgen-dash-out-tab', a.dataset.outTab); } catch (err) { /* not kept: still switches */ }
    outTab(a.dataset.outTab);
  });
  outTab();
  var waiting = false, lastHtml = null, lastRefresh = Date.now(), soonTimer = null;
  //(after an action done in place on the Dashboard, e.g. Unpin: redrawn now, static/js/inplace.js; the owner, 2026-10-27)
  window.qgenDashRefresh = function () { lastHtml = null; refresh(); };
  function refresh() {
    if (document.hidden) return;
    if (busy()) { waiting = true; return; }
    waiting = false;
    lastRefresh = Date.now();
    fetch(box.dataset.url, { credentials: 'same-origin' })
      .then(function (r) {
        //(signed out meanwhile: the answer is the login page; the whole page reloads to it, never the login form inside
        //the Dashboard, where signing in landed on this bare piece: the owner, 2026-10-26; as messages.js does)
        if (r.redirected && /\/login(\?|$)/.test(new URL(r.url).pathname + new URL(r.url).search.slice(0, 1))) {
          window.location.reload();
          return null;
        }
        return r.ok ? r.text() : null;
      })
      .then(function (html) {
        if (!html || html === lastHtml) return;  // nothing new: leave the page alone
        lastHtml = html;
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
        //each box keeps its place while it's redrawn (the owner, 2026-10-18): the new boxes come in
        //where the old ones were (their row spans, folded or open, the row of folded boxes), instead
        //of first in plain grid order and then jumping into place; only a box whose size changed moves
        var oldGrid = box.querySelector('.dash-grid'), keep = {};
        var key = function (d) { return d.dataset.box || d.id; };
        if (oldGrid) Array.prototype.forEach.call(oldGrid.children, function (d) {
          //(its whole place, column and row, not only its height: with the height alone each new box came in
          //at the grid's next free spot, in plain order, overlapping, then jumped back a moment later; seen on
          //every reload, when the live connection's first redraw comes; the owner, 2026-10-26)
          if (key(d)) keep[key(d)] = { col: d.style.gridColumn, row: d.style.gridRow, open: d.open };
        });
        box.innerHTML = html;
        outTab();
        var newGrid = box.querySelector('.dash-grid');
        if (oldGrid && newGrid) {
          if (oldGrid.classList.contains('masonry-on')) { newGrid.classList.add('masonry-on'); newGrid.dataset.gap = oldGrid.dataset.gap; }
          Array.prototype.forEach.call(newGrid.children, function (d) {
            var k = keep[key(d)];
            if (!k) return;
            if (k.col) d.style.gridColumn = k.col;
            if (k.row) d.style.gridRow = k.row;
            if (d.tagName === 'DETAILS') d.open = k.open;
          });
        }
        //and the sizes kept by hand (a list pulled longer, a card pulled taller) straight away, not
        //a moment later, so a card doesn't shrink and grow again
        if (window.qgenGripScan) window.qgenGripScan();
        if (window.qgenElasticScan) window.qgenElasticScan();
        box.querySelectorAll('details[data-more]').forEach(function (d) { if (more[d.dataset.more]) d.open = true; });
        //laid out now, before the page is drawn again (a box that changed size, or a new one, is never shown in a
        //wrong spot first)
        if (newGrid && window.qgenLayNow) window.qgenLayNow(newGrid);
        setTimeout(function () {
          ['wheel', 'touchmove', 'keydown', 'mousedown'].forEach(function (t) { window.removeEventListener(t, mine); });
          box.style.minHeight = '';
          if (!moved && Math.abs(window.scrollY - y) > 1) window.scrollTo(0, y);  // as far as the page now goes
        }, 400);
      }, function () {});
  }
  //with instant updates (push.js) it redraws when the server says something changed, and
  //every few minutes as a backup (times like "5 min ago" move on); without them, as set
  var every = Math.max(10000, +box.dataset.every || 30000), BACKUP = Math.max(every, 300000);
  setInterval(function () { if (!window.qgenLive || Date.now() - lastRefresh >= BACKUP - 1000) refresh(); }, every);
  document.addEventListener('qgen-changed', function () {
    if (soonTimer) return;
    soonTimer = setTimeout(function () { soonTimer = null; refresh(); }, Math.max(0, lastRefresh + 1500 - Date.now()));
  });
  document.addEventListener('close', function () { if (waiting) setTimeout(refresh, 0); }, true);
  //(a note's card closed: the refresh it held back now; the card itself, static/js/notepop.js)
  document.addEventListener('toggle', function (e) {
    if (e.target.matches && e.target.matches('.note-pop') && e.newState !== 'open' && waiting) setTimeout(refresh, 0);
  }, true);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
})();
