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
