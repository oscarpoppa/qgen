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
  var ICON = { error: '✗', warn: '!', tip: '•', ok: '✓' };

  function render(target, hints) {
    target.innerHTML = '';
    hints.forEach(function (h) {
      //(a choice already made, Keep as it is, stays hidden while this page is open)
      try { if (h.key && sessionStorage.getItem('qgen-helper-dismissed:' + location.pathname + ':' + form.id + ':' + h.key)) return; } catch (e) {}
      var li = document.createElement('li');
      li.className = 'hint hint-' + h.level;
      var icon = document.createElement('span');
      icon.className = 'hint-icon'; icon.setAttribute('aria-hidden', 'true');
      if (h.level === 'tip' && window.qgenIcon) icon.innerHTML = window.qgenIcon('bulb');  // the site's drawn icon (app/icons.py)
      else icon.textContent = ICON[h.level] || '•';
      var text = document.createElement('span');
      text.textContent = h.text;
      li.appendChild(icon); li.appendChild(text);
      //(the Helper only reads the page and says what it sees: no buttons in it, ever; a choice lives on the thing it's
      //about, e.g. a scanned page's Try again on that page's box: the owner, 2026-10-24)
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
