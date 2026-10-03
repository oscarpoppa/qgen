/* Live helper panel. A form with data-check-url is checked a moment after
 * each change; hints appear in the #helper panel. One-click fixes are sent
 * to the page as a "helper-action" event (see problem_form.js). */
(function () {
  var panel = document.getElementById('helper');
  if (!panel) return;
  var form = document.getElementById(panel.dataset.form);
  var list = panel.querySelector('.hints');
  var status = panel.querySelector('.helper-status');
  var timer = null, seq = 0;
  var ICON = { error: '✗', warn: '!', tip: '💡', ok: '✓' };

  function render(target, hints) {
    target.innerHTML = '';
    hints.forEach(function (h) {
      var li = document.createElement('li');
      li.className = 'hint hint-' + h.level;
      var icon = document.createElement('span');
      icon.className = 'hint-icon'; icon.setAttribute('aria-hidden', 'true');
      icon.textContent = ICON[h.level] || '•';
      var text = document.createElement('span');
      text.textContent = h.text;
      li.appendChild(icon); li.appendChild(text);
      if (h.action) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'btn btn-secondary btn-sm';
        b.textContent = h.action.label;
        b.addEventListener('click', function () {
          form.dispatchEvent(new CustomEvent('helper-action', { detail: h.action }));
          check();
        });
        li.appendChild(b);
      }
      target.appendChild(li);
    });
  }

  function post(url) {
    return fetch(url, { method: 'POST', body: new FormData(form), credentials: 'same-origin',
                        headers: { 'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content } })
      .then(function (r) { return r.json(); });
  }

  function check() {
    var mine = ++seq;
    status.textContent = 'Checking…';
    post(panel.dataset.checkUrl).then(function (res) {
      if (mine !== seq) return;  // a newer check is on its way
      render(list, res.hints || []);
      status.textContent = '';
    }, function () { status.textContent = 'Couldn\'t check just now.'; });
  }

  function soon() { clearTimeout(timer); timer = setTimeout(check, 700); }
  form.addEventListener('input', soon);
  form.addEventListener('change', soon);
  form.addEventListener('helper-refresh', soon);

  check();
})();
