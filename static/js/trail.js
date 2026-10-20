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
  var KEY = 'qgen-trail', GOING = 'qgen-going-back', AHEAD = 'qgen-ahead', MAX = 30, LONGEST = 40;
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
  //(and without the sandbox's "SANDBOX · " in front)
  var name = document.title.replace(/(?: [\u{1F7E1}\u{1F535}]\d+)+$/u, '').trim() || 'Back';
  //a page with two views at two addresses (People: Accounts and Results) counts as one page
  var here = { k: document.documentElement.dataset.trailKey || location.pathname, p: location.pathname + location.search, t: name };
  //"New examples" / "Roll another": the same page drawn again, in place of this one in the
  //browser's history too, so its Back goes to the page before, not the last roll (the owner, 2026-10-19)
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-reroll]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;
    e.preventDefault();
    location.replace(a.href);
  });
  var trail = read(KEY, []), going = read(GOING, null);
  //an error page ("Page not found"): never on the trail; ← goes back to the page before it
  var skip = document.documentElement.hasAttribute('data-no-trail');
  //the pages gone back from, nearest first: where Forward goes (the owner, 2026-10-19)
  var ahead = read(AHEAD, []);
  write(GOING, null);
  var nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
  var historyMove = nav && nav.type === 'back_forward';
  var last = -1;
  trail.forEach(function (s, i) { if (s.k === here.k) last = i; });

  if (skip) {
    //(left as it is: Back goes to the last real page, which isn't this one)
    trail = trail.concat([here]);
    write(GOING, null);
    var tail = trail.slice(0, -1);
    arm(document.getElementById('trail-back'), tail.length ? tail[tail.length - 1] : null, 'Back', tail.length ? tail[tail.length - 1].k : null);
    arm(document.getElementById('trail-fwd'), null, 'Forward', null);
    return;
  }
  if (trail.length && trail[trail.length - 1].k === here.k) {
    trail[trail.length - 1] = here;                         // the same page again
  } else if (ahead.length && ahead[0].k === here.k && (going === 'fwd:' + here.k || historyMove)) {
    trail.push(here);                                       // Forward: the next page gone back from
    ahead = ahead.slice(1);
    document.documentElement.setAttribute('data-came-back', '');
  } else if (last !== -1 && (going === here.k || historyMove || last === trail.length - 2)) {
    ahead = trail.slice(last + 1).concat(ahead);            // back to a page on the trail: the
    trail = trail.slice(0, last).concat([here]);            // pages after it are where Forward goes
    //(put back as it was, static/js/keep.js, only for a real Back; a link to the page before is a
    //new arrival, everything folded: the owner, 2026-10-19)
    if (going === here.k || historyMove) document.documentElement.setAttribute('data-came-back', '');
  } else {
    trail.push(here);
    ahead = [];                                             // somewhere new: nothing ahead any more
  }
  if (trail.length > MAX) trail = trail.slice(trail.length - MAX);
  if (ahead.length > MAX) ahead = ahead.slice(0, MAX);
  write(KEY, trail);
  write(AHEAD, ahead);
  //the bar's ← and →: where each goes, named in its tooltip; grayed out with nowhere to go
  function arm(btn, to, word, going) {
    if (!btn) return;
    if (!to) { btn.setAttribute('aria-disabled', 'true'); btn.removeAttribute('href'); btn.title = 'Nothing to go ' + (word === 'Back' ? 'back' : 'forward') + ' to'; return; }
    btn.removeAttribute('aria-disabled');
    btn.href = to.p;
    btn.title = word + ': ' + to.t;
    btn.addEventListener('click', function () { write(GOING, going); });
  }
  arm(document.getElementById('trail-back'), trail.length > 1 ? trail[trail.length - 2] : null, 'Back', trail.length > 1 ? trail[trail.length - 2].k : null);
  arm(document.getElementById('trail-fwd'), ahead[0] || null, 'Forward', ahead[0] ? 'fwd:' + ahead[0].k : null);
  //(a folder tab chosen: the page's address changes without loading, folderfilter.js)
  document.addEventListener('qgen-address', function () {
    var t = read(KEY, []);
    for (var i = t.length - 1; i >= 0; i--) if (t[i].k === here.k) { t[i].p = location.pathname + location.search; break; }
    write(KEY, t);
  });

  var before = trail.length > 1 ? trail[trail.length - 2] : null;
  if (!before) return;  // opened on its own (a new tab): the server's choice stays
  var label = before.t.length > LONGEST ? before.t.slice(0, LONGEST - 1).trim() + '…' : before.t;
  document.querySelectorAll('a[data-back]').forEach(function (a) {
    a.href = before.p;
    //(the words in their own span, so a long name ends in "…" instead of widening the page)
    var span = a.querySelector('.back-label');
    if (!span) { span = document.createElement('span'); span.className = 'back-label'; a.textContent = ''; a.appendChild(span); }
    span.textContent = '← ' + label;
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
