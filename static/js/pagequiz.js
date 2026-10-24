/* A quiz taken on its scanned page (the owner, 2026-10-18): each question that has a place on
 * the page is there and, for phones, in the usual list too. Only one of the two is in use at a
 * time: the other is marked data-off (hidden, and its fields disabled so they aren't saved or
 * handed in). Switching (turning a tablet, say) carries the answers over. */
(function () {
  var form = document.getElementById('take-form');
  var page = form && form.querySelector('[data-page-quiz]');
  if (!page) return;
  var phone = window.matchMedia('(max-width: 599px)');
  var cards = Array.prototype.slice.call(form.querySelectorAll('.pq-has-slot'));

  function fields(root) { return Array.prototype.slice.call(root.querySelectorAll('input:not([type=hidden]), textarea, select')); }
  function zone(onPage) { return onPage ? [page] : cards; }
  function each(roots, fn) { roots.forEach(function (r) { fields(r).forEach(fn); }); }

  function carry(from, to) {
    var typed = {}, picked = {};
    each(from, function (el) {
      if (el.type === 'radio' || el.type === 'checkbox') { if (el.checked) (picked[el.name] = picked[el.name] || {})[el.value] = true; }
      else typed[el.name] = el.value;
    });
    each(to, function (el) {
      if (el.type === 'radio' || el.type === 'checkbox') el.checked = !!(picked[el.name] && picked[el.name][el.value]);
      else if (el.name in typed) el.value = typed[el.name];
    });
  }

  //(a browser can put text it remembers back in the boxes when a page opens again; what's in a box at the start is only what the server sent)
  function fresh() { fields(form).forEach(function (el) { if (el.type === 'text' || el.tagName === 'TEXTAREA') el.value = el.defaultValue; }); }
  fresh();
  window.addEventListener('pageshow', function (e) { if (e.persisted) fresh(); });

  var onPage = null;
  function apply() {
    var want = !phone.matches;
    if (want === onPage) return;
    if (onPage !== null) carry(zone(onPage), zone(want));
    zone(!want).forEach(function (r) { r.setAttribute('data-off', ''); each([r], function (el) { el.disabled = true; }); });
    zone(want).forEach(function (r) { r.removeAttribute('data-off'); each([r], function (el) { el.disabled = false; }); });
    var first = onPage === null;
    onPage = want;
    if (!first) form.dispatchEvent(new Event('change'));  // the "answered" count (at the start, the page's own script counts)
  }
  if (phone.addEventListener) phone.addEventListener('change', apply); else phone.addListener(apply);
  apply();
})();
