/* Help tips: a small "?" button next to a label (see the tip macro).
 * Hovering or focusing it shows the explanation; clicking or tapping keeps it
 * open (touch screens have no hover); Esc, the button again, or a click
 * elsewhere closes it. Works for rows added to the page later, too. */
(function () {
  var open = null;      // the button whose tip is showing
  var pinned = false;   // opened by a click/tap, so hover-out doesn't close it
  var hideTimer = null;
  var uid = 0;

  function bodyOf(btn) { return btn.nextElementSibling; }

  function place(btn) {
    var body = bodyOf(btn);
    var gap = 8, margin = 12;
    var r = btn.getBoundingClientRect();
    body.style.left = '0px';
    body.style.top = '0px';
    var w = body.offsetWidth, h = body.offsetHeight;
    var left = Math.min(Math.max(margin, r.left + r.width / 2 - w / 2), window.innerWidth - w - margin);
    var below = r.bottom + gap;
    var top = (below + h > window.innerHeight - margin && r.top - gap - h > margin) ? r.top - gap - h : below;
    body.style.left = Math.max(margin, left) + 'px';
    body.style.top = top + 'px';
  }

  function show(btn, pin) {
    clearTimeout(hideTimer);
    if (open && open !== btn) hide();
    var body = bodyOf(btn);
    if (!body || !body.classList.contains('tip-body')) return;
    if (!body.id) body.id = 'tip-' + (++uid);
    btn.setAttribute('aria-describedby', body.id);
    body.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    open = btn;
    pinned = pinned || !!pin;
    place(btn);
  }

  function hide() {
    clearTimeout(hideTimer);
    if (!open) return;
    bodyOf(open).hidden = true;
    open.setAttribute('aria-expanded', 'false');
    open = null;
    pinned = false;
  }

  function hideSoon() {
    if (pinned) return;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, 150);
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('button.tip');
    if (btn) {
      e.preventDefault();
      if (open === btn && pinned) hide(); else show(btn, true);
      return;
    }
    if (open && !e.target.closest('.tip-body')) hide();
  });

  document.addEventListener('mouseover', function (e) {
    var btn = e.target.closest('button.tip');
    if (btn) { if (!pinned) show(btn, false); return; }
    if (open && e.target.closest('.tip-body') === bodyOf(open)) clearTimeout(hideTimer);
  });
  document.addEventListener('mouseout', function (e) {
    if (!open || pinned) return;
    var from = e.target.closest('button.tip, .tip-body');
    var to = e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('button.tip, .tip-body');
    if (from && to !== open && to !== bodyOf(open)) hideSoon();
  });

  document.addEventListener('focusin', function (e) {
    if (e.target.matches('button.tip') && !pinned) show(e.target, false);
  });
  document.addEventListener('focusout', function (e) {
    if (e.target.matches('button.tip') && !pinned) hideSoon();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && open) {
      var btn = open;
      hide();
      btn.focus();
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
