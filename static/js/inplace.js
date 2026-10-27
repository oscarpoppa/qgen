/* Actions done in place (the owner, 2026-10-27: an action that comes back to the same page shouldn't reload it; the
 * page stays exactly as it was but for what changed). A form marked data-in-place, or one sent with qgenSubmit(), goes
 * by fetch with X-In-Place: 1; the server answers its messages and where it would have gone (app/__init__.py
 * _in_place). Back on the same page: the messages float over it and the list is redrawn in place (folders.js
 * qgenRefreshList, or the Dashboard's qgenDashRefresh); anywhere else, or a page that can't redraw itself: it goes
 * there, as before. */
(function () {
  function say(messages) {
    if (!messages || !messages.length) return;
    var list = document.createElement('ul');
    list.className = 'alerts';
    list.setAttribute('role', 'status');
    messages.forEach(function (m) {
      var li = document.createElement('li');
      li.className = 'alert ' + (m.error ? 'alert-error' : 'alert-success');
      li.innerHTML = m.html;  // (escaped by the server unless it was its own Markup, e.g. a link to the Trash)
      list.appendChild(li);
    });
    var main = document.querySelector('main');
    main.insertBefore(list, main.firstChild);
    if (window.qgenFloat) window.qgenFloat(list);  // (over the page, not in it: nothing below moves)
  }
  function samePage(loc) {
    if (!loc) return true;
    var u = new URL(loc, location.href);
    return u.origin === location.origin && u.pathname === location.pathname;
  }
  //redrawn in place, if this page can; false: it can't (the caller goes there instead)
  function redraw() {
    if (window.qgenRefreshList && document.querySelector('.folder-main [data-folder-filter]')) { window.qgenRefreshList(); return true; }
    if (window.qgenDashRefresh) { window.qgenDashRefresh(); return true; }
    //(any other page made of folder lists, e.g. a student's history: its lists swapped for fresh ones, each set up again
    //as folders.js does; anything that doesn't line up: the page is loaded again)
    var boxes = lists(document);
    if (!boxes.length || !window.qgenFolderFilterSetUp || !window.DOMParser) return false;
    fetch(location.href, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok || r.redirected) throw new Error('not the page');
      return r.text();
    }).then(function (html) {
      var fresh = lists(new DOMParser().parseFromString(html, 'text/html'));
      if (fresh.length !== boxes.length) throw new Error('not the same page');
      boxes.forEach(function (b, i) {
        var nb = document.importNode(fresh[i], true);
        if (b.qgenTearDown) b.qgenTearDown();
        b.replaceWith(nb);
        window.qgenFolderFilterSetUp(nb);
      });
      document.dispatchEvent(new CustomEvent('qgen-swapped', { detail: { list: boxes[0] } }));
    }).catch(function () { go(null); });
    return true;
  }
  //(also when the page changed elsewhere, static/js/messages.js: redrawn in place where it can be, the owner 2026-10-27)
  window.qgenRedraw = redraw;
  function lists(doc) {
    return Array.prototype.filter.call(doc.querySelectorAll('[data-folder-filter]'), function (b) {
      return !b.closest('dialog, template') && !b.parentElement.closest('[data-folder-filter]');
    });
  }
  function go(loc) { location.assign(loc || location.href); }

  window.qgenInPlace = function (url, data) {
    return fetch(url, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-In-Place': '1' } }).then(function (r) {
      var type = r.headers.get('Content-Type') || '';
      if (type.indexOf('application/json') === -1) {
        //(a page of its own came back, e.g. a form with a mistake shown on it: shown as it came)
        return r.text().then(function (html) { document.open(); document.write(html); document.close(); });
      }
      return r.json().then(function (res) {
        if (res.inplace) {
          if (!samePage(res.location)) { go(res.location); return; }
          say(res.messages);
          if (!redraw()) go(res.location);
          return;
        }
        //(a route that answers JSON itself, {ok, message} or {ok: false, error})
        say([{ html: escapeHtml(res.ok ? res.message || '' : res.error || 'That didn’t work. Please reload the page and try again.'), error: !res.ok }].filter(function (m) { return m.html; }));
        if (res.ok && !redraw()) go(null);
      });
    }).catch(function () {
      say([{ html: 'That didn’t work: no connection. Please try again.', error: true }]);
    });
  };
  function escapeHtml(t) { var d = document.createElement('div'); d.textContent = t; return d.innerHTML; }

  //a form sent by a script (after its own question): in place when it's marked, else the usual way
  window.qgenSubmit = function (form, submitter) {
    if (!window.fetch || !form.matches('[data-in-place]')) { form.submit(); return; }
    //(a dialog it was sent from closes, as the reload used to close it: the owner, 2026-10-27)
    var dlg = form.closest('dialog');
    if (dlg && dlg.open) dlg.close();
    var data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    if (window.qgenCheckedClear && form.dataset.clearsChecked !== undefined) window.qgenCheckedClear();
    window.qgenInPlace(form.getAttribute('action') || location.href, data);
  };
  //a marked form sent by its own button (nothing else stopped it first, e.g. a question)
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (e.defaultPrevented || !form.matches || !form.matches('form[data-in-place]') || !window.fetch) return;
    e.preventDefault();
    window.qgenSubmit(form, e.submitter);
  });
})();
