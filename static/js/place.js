/* Keeping your place: a button that does something and comes back to the same page (Move
 * to, Put in folder, Archive, Restore, Save...) reloads it, which would start at the top.
 * The scroll position is noted when such a form is sent (POST) and, if the page that comes
 * back is the same one, put back. The message saying what happened ("Moved ... to ...")
 * is at the top of the page, so it floats at the top of the window for a few seconds.
 * The same for a link to another view of the same page (a folder, a filter: ?folder=3).
 * Not after a page that scrolled somewhere itself (to what was just moved or saved), and
 * not for forms or links marked data-fresh-page (handing in a quiz opens its results at the top). */
(function () {
  var KEY = 'qgen-place';
  function note() {
    try { sessionStorage.setItem(KEY, JSON.stringify({ path: location.pathname, y: window.scrollY, at: Date.now() })); } catch (err) {}
  }
  window.qgenNotePlace = note;  // for a page script that reloads by itself (a folder drop)
  //a message shown over the page for a few seconds, then gone: never dropped back into the
  //page, which would push everything down under the reader
  window.qgenFloat = function (alerts) {
    alerts.classList.add('alerts-float');
    //(side to side across the page's content, as the message strip in the page is: the owner, 2026-10-27; it was a short
    //560px strip in the middle)
    var main = document.querySelector('main');
    if (main) {
      var r = main.getBoundingClientRect(), cs = getComputedStyle(main);
      var l = r.left + parseFloat(cs.paddingLeft), w = r.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      alerts.style.left = Math.round(l) + 'px'; alerts.style.width = Math.round(w) + 'px'; alerts.style.transform = 'none';
    }
    var gone = false;
    function hide() {
      if (gone) return;
      gone = true;
      alerts.classList.add('alerts-leaving');
      setTimeout(function () { alerts.remove(); }, 300);
    }
    setTimeout(hide, 6000);
    alerts.addEventListener('click', hide);
  };
  document.addEventListener('submit', function (e) {
    var f = e.target;
    if ((f.method || '').toLowerCase() !== 'post' || f.hasAttribute('data-fresh-page')) return;
    note();
  }, true);
  //a link to another view of the same page (a folder, a filter: ?folder=3) keeps the place too
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.target || a.hasAttribute('download') || a.hasAttribute('data-fresh-page')) return;
    var to;
    try { to = new URL(a.href, location.href); } catch (err) { return; }
    if (to.origin !== location.origin || to.pathname !== location.pathname || to.hash) return;
    note();
  });

  var place = null;
  try { place = JSON.parse(sessionStorage.getItem(KEY) || 'null'); sessionStorage.removeItem(KEY); } catch (err) {}
  if (!place || place.path !== location.pathname || Date.now() - place.at > 20000 || !place.y) return;
  if (window.scrollY > 0) return;  // the page already went somewhere itself
  var y = place.y;
  function go() { if (window.scrollY === 0 || Math.abs(window.scrollY - y) > 2) window.scrollTo(0, y); }
  go();
  window.addEventListener('load', function () { setTimeout(go, 0); });
  //what happened, where it can be seen
  var alerts = document.querySelector('main .alerts');
  if (alerts && y > 60) window.qgenFloat(alerts);
})();
