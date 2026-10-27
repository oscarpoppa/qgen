/* My profile's Theme card (the owner, 2026-10-26, To do 64): a swatch pressed shows its colors at once, on this page,
 * and saves them on the account; the form sends it the plain way when this script doesn't run. */
(function () {
  var form = document.querySelector('[data-theme-pick]');
  if (!form) return;
  form.addEventListener('click', function (e) {
    var b = e.target.closest('button[name="theme"]');
    if (!b) return;
    e.preventDefault();
    document.documentElement.dataset.theme = b.value;
    form.querySelectorAll('button[name="theme"]').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
    var data = new FormData(form);
    data.set('theme', b.value);
    fetch(form.getAttribute('action'), { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw new Error(); })
      //(not saved, e.g. signed out meanwhile: sent the plain way instead, and the page that comes back says why)
      .catch(function () {
        var i = document.createElement('input'); i.type = 'hidden'; i.name = 'theme'; i.value = b.value;
        form.appendChild(i); form.submit();
      });
  });
})();
