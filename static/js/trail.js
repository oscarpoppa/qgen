/* Back buttons go to the page that opened this one, whatever page that was.
 *
 * Each browser tab keeps its own trail of the pages visited (sessionStorage): the address,
 * and the page's name (its title). A page counts once however its address changes (a
 * folder picked, a form saved, a reload): only its latest address is kept. Coming back to
 * a page already on the trail (its Back button, the browser's Back, or straight back to
 * the page before) goes back along the trail instead of adding to it, so Back never loops.
 *
 * A Back button is <a data-back>: drawn by the server with a sensible place to go (it works
 * without this script), then pointed at the page before this one on the trail, named after
 * it. A form's <input data-back-next> (where to go after saving) follows it too. */
(function () {
  var KEY = 'qgen-trail', GOING = 'qgen-going-back', MAX = 30, LONGEST = 40;
  function read(key, fallback) {
    try { var v = JSON.parse(sessionStorage.getItem(key) || 'null'); return v === null ? fallback : v; } catch (e) { return fallback; }
  }
  function write(key, value) {
    try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  //signed out: a fresh trail next time
  var me = document.querySelector('script[src*="trail.js"]');
  if (!me || !me.hasAttribute('data-signed-in')) { write(KEY, null); return; }

  //the page's name: its title without the site's name after it
  var name = document.title.replace(/ · [^·]*$/, '').trim() || 'Back';
  var here = { k: location.pathname, p: location.pathname + location.search, t: name };
  var trail = read(KEY, []), going = read(GOING, null);
  write(GOING, null);
  var nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
  var historyMove = nav && nav.type === 'back_forward';
  var last = -1;
  trail.forEach(function (s, i) { if (s.k === here.k) last = i; });

  if (trail.length && trail[trail.length - 1].k === here.k) {
    trail[trail.length - 1] = here;                         // the same page again
  } else if (last !== -1 && (going === here.k || historyMove || last === trail.length - 2)) {
    trail = trail.slice(0, last).concat([here]);            // back to a page on the trail
  } else {
    trail.push(here);
  }
  if (trail.length > MAX) trail = trail.slice(trail.length - MAX);
  write(KEY, trail);

  var before = trail.length > 1 ? trail[trail.length - 2] : null;
  if (!before) return;  // opened on its own (a new tab): the server's choice stays
  var label = before.t.length > LONGEST ? before.t.slice(0, LONGEST - 1).trim() + '…' : before.t;
  document.querySelectorAll('a[data-back]').forEach(function (a) {
    a.href = before.p;
    a.textContent = '← ' + label;
    a.title = 'Go back to ' + before.t;
    a.addEventListener('click', function () { write(GOING, before.k); });
  });
  //a Cancel (its own words) goes to the same place
  document.querySelectorAll('a[data-back-href]').forEach(function (a) {
    a.href = before.p;
    if (!a.title) a.title = 'Leave without saving and go back to ' + before.t;
    a.addEventListener('click', function () { write(GOING, before.k); });
  });
  document.querySelectorAll('input[data-back-next]').forEach(function (i) { i.value = before.p; });
})();
