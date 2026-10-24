/* Help tips: the label a tip macro sits beside shows its help (see below). */
(function () {
  /* (the owner, 2026-10-24: no "?" circles; the label, heading or words the help is about show it, with a faint dotted underline.
   * Each tip macro's "?" is turned into that here: the label just before it, the words just before it, or the heading of the box
   * it's in. Hovering or focusing the label shows the help; a click or tap keeps it open; Esc, the label again or a click elsewhere
   * closes it.) */
  var open = null;      // the label whose tip is showing
  var pinned = false;   // opened by a click/tap, so hover-out doesn't close it
  var hideTimer = null;
  var uid = 0;
  var SKIP = '.badge, .muted, .sr-only, script, template';
  var STOP = 'button, input, select, textarea';

  //the label a tip belongs to: the nearest thing before its "?" that names something (a label, a heading, some words),
  //else the heading of the box it's in
  function hostFor(wrap) {
    for (var n = wrap.previousSibling; n; n = n.previousSibling) {
      if (n.nodeType === 3) {
        var t = n.textContent;
        if (!t.trim()) continue;
        var span = document.createElement('span');
        var lead = t.match(/^\s*/)[0], trail = t.match(/\s*$/)[0];
        span.textContent = t.trim();
        var frag = document.createDocumentFragment();
        if (lead) frag.appendChild(document.createTextNode(lead));
        frag.appendChild(span);
        if (trail) frag.appendChild(document.createTextNode(trail));
        n.parentNode.replaceChild(frag, n);
        return span;
      }
      if (n.nodeType !== 1) continue;
      if (n.matches(STOP)) break;
      if (n.matches(SKIP)) continue;
      return n;
    }
    var d = wrap.closest('details');
    var sum = d && d.querySelector(':scope > summary');
    if (sum) return sum.querySelector('.box-title') || sum;
    return null;
  }

  function setUp(root) {
    (root || document).querySelectorAll('.tip-wrap:not(.tip-moved)').forEach(function (wrap) {
      var body = wrap.querySelector('.tip-body'), host = hostFor(wrap);
      if (!body || !host) return;
      wrap.classList.add('tip-moved');
      host.classList.add('has-tip');
      //(a title it had goes first in the help: one tooltip, not two)
      if (host.title) { var p = document.createElement('p'); p.textContent = host.title; body.insertBefore(p, body.firstChild); host.removeAttribute('title'); }
      //(a label too: the keyboard reaches its help as it reached the "?" button, Enter or Space opening it)
      if (!host.matches('a, button, summary, input, [tabindex]')) host.tabIndex = 0;
      host._tipBody = body;
    });
  }
  setUp();
  //(rows added to the page later: the values table, a dialog)
  if (window.MutationObserver) {
    var later = null;
    new MutationObserver(function (records) {
      //(only when something with a tip came in: cheap otherwise)
      var any = records.some(function (r) { return Array.prototype.some.call(r.addedNodes, function (n) { return n.nodeType === 1 && (n.matches('.tip-wrap') || n.querySelector('.tip-wrap')); }); });
      if (any) { clearTimeout(later); later = setTimeout(function () { setUp(); }, 50); }
    })
      .observe(document.body, { childList: true, subtree: true });
  }

  function hostOf(el) { var h = el && el.closest && el.closest('.has-tip'); return h && h._tipBody ? h : null; }
  function bodyOf(host) { return host._tipBody; }

  function place(host) {
    var body = bodyOf(host);
    var gap = 8, margin = 12;
    var r = host.getBoundingClientRect();
    body.style.left = '0px';
    body.style.top = '0px';
    var w = body.offsetWidth, h = body.offsetHeight;
    var left = Math.min(Math.max(margin, r.left + r.width / 2 - w / 2), window.innerWidth - w - margin);
    var below = r.bottom + gap;
    var top = (below + h > window.innerHeight - margin && r.top - gap - h > margin) ? r.top - gap - h : below;
    body.style.left = Math.max(margin, left) + 'px';
    body.style.top = top + 'px';
  }

  function show(host, pin) {
    clearTimeout(hideTimer);
    if (open && open !== host) hide();
    var body = bodyOf(host);
    if (!body.id) body.id = 'tip-' + (++uid);
    host.setAttribute('aria-describedby', body.id);
    body.hidden = false;
    open = host;
    pinned = pinned || !!pin;
    place(host);
  }

  function hide() {
    clearTimeout(hideTimer);
    if (!open) return;
    bodyOf(open).hidden = true;
    open = null;
    pinned = false;
  }

  function hideSoon() {
    if (pinned) return;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, 150);
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('.tip-body')) return;
    var host = hostOf(e.target);
    //(a label that's also a fold or a box's heading still does that; its help shows on hover and focus)
    //(on a touch screen there's no hover: a tap on a fold's heading also opens its help, and the fold still opens)
    if (host && (host.matches('summary') || host.closest('summary')) && matchMedia('(hover: none)').matches) {
      if (open === host && pinned) hide(); else show(host, true);
      return;
    }
    if (host && !host.matches('summary') && !host.closest('summary')) {
      if (open === host && pinned) hide(); else show(host, true);
      return;
    }
    if (open && !e.target.closest('.tip-body')) hide();
  });

  document.addEventListener('mouseover', function (e) {
    var host = hostOf(e.target);
    if (host) { if (!pinned) show(host, false); return; }
    if (open && e.target.closest('.tip-body') === bodyOf(open)) clearTimeout(hideTimer);
  });
  document.addEventListener('mouseout', function (e) {
    if (!open || pinned) return;
    var to = e.relatedTarget;
    if (to && (open.contains(to) || bodyOf(open).contains(to))) return;
    hideSoon();
  });

  document.addEventListener('focusin', function (e) {
    var host = hostOf(e.target);
    if (host && host === e.target && !pinned) show(host, false);
  });
  document.addEventListener('focusout', function (e) {
    if (hostOf(e.target) && !pinned) hideSoon();
  });

  document.addEventListener('keydown', function (e) {
    var host = hostOf(e.target);
    if ((e.key === 'Enter' || e.key === ' ') && host && host === e.target && !host.matches('a, button, summary, input')) {
      e.preventDefault();
      if (open === host && pinned) hide(); else show(host, true);
      return;
    }
    if (e.key === 'Escape' && open) {
      var host = open;
      hide();
      if (host.focus) host.focus();
    }
  });

  window.addEventListener('scroll', function () { if (open) place(open); }, true);
  window.addEventListener('resize', function () { if (open) place(open); });
})();

/* Link tooltips: a link with data-tip (a name that opens a student's page or a quiz's history)
 * shows its tip just above it while hovered or focused. One shared tip; it never covers the link. */
(function () {
  var tip = null, on = null;
  function make() {
    tip = document.createElement('div');
    tip.className = 'link-tip';
    tip.id = 'link-tip';
    tip.setAttribute('role', 'tooltip');
    tip.hidden = true;
    document.body.appendChild(tip);
  }
  function show(a) {
    if (!tip) make();
    on = a;
    tip.textContent = a.getAttribute('data-tip');
    tip.hidden = false;
    a.setAttribute('aria-describedby', 'link-tip');
    var r = a.getBoundingClientRect(), margin = 8;
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.min(Math.max(margin, r.left + r.width / 2 - w / 2), window.innerWidth - w - margin);
    tip.style.left = Math.max(margin, left) + 'px';
    tip.style.top = Math.max(margin, r.top - h - 6) + 'px';
  }
  function hide() {
    if (on) on.removeAttribute('aria-describedby');
    on = null;
    if (tip) tip.hidden = true;
  }
  function linkOf(t) { return t && t.closest ? t.closest('a[data-tip]') : null; }
  document.addEventListener('mouseover', function (e) { var a = linkOf(e.target); if (a && a !== on) show(a); });
  document.addEventListener('mouseout', function (e) {
    var a = linkOf(e.target);
    if (a && a === on && !a.contains(e.relatedTarget)) hide();
  });
  document.addEventListener('focusin', function (e) { var a = linkOf(e.target); if (a) show(a); });
  document.addEventListener('focusout', function (e) { if (linkOf(e.target) === on) hide(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, true);
  window.addEventListener('pagehide', hide);
  //a part of the page redrawn under the pointer (the Dashboard's refresh...): its tip goes too
  if (window.MutationObserver) new MutationObserver(function () {
    if (on && !on.isConnected) hide();
  }).observe(document.body, { childList: true, subtree: true });
})();
