/* Taking things out of a folder, the same on every folder page (app/takeout.py): every form
 * marked data-takeout (a folder chip's ✕, "Take out of folder" on the checked bar, a card's
 * "Take out") first asks the site what would happen (check=1). Something that would be left
 * in no folder is never changed without asking: "Do you want me to permanently delete this or
 * put it in Uncategorized?" The answer goes with the form (confirm=delete|uncategorized).
 *
 * data-takeout-shown: the form acts on the folder shown (the folder tab chosen, or the folder
 * box it's in: data-here), filled in when it's sent; grayed while no folder is shown. */
(function () {
  //the folder something is shown in: a folder tab's choice ("self:7" is folder 7's own), else
  //the folder box it sits in
  window.qgenShownFolder = function (el) {
    //(a form outside the list, e.g. the checked bar: the page's own folder tabs)
    var ff = el.closest('[data-folder-filter]') || (el.closest('[data-here]') ? null : document.querySelector('[data-folder-filter][data-url-tab]'));
    if (ff && ff.dataset.shown) {
      var c = ff.dataset.shown.replace(/^self:/, '');
      return /^\d+$/.test(c) ? c : null;
    }
    var here = el.closest('[data-here]');
    return here && /^\d+$/.test(here.dataset.here) ? here.dataset.here : null;
  };

  window.qgenTakeOutChoices = [
    { value: 'delete', label: 'Delete for good', danger: true, title: 'Delete it (asked because it’s in no other folder)' },
    { value: 'uncategorized', label: 'Put in Uncategorized', title: 'Keep it, in no folder' }];

  function fetchJson(url, data) {
    return fetch(url, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); });
  }

  function hidden(form, name, value) {
    var i = form.querySelector('input[type=hidden][name="' + name + '"][data-added]');
    if (!i) { i = document.createElement('input'); i.type = 'hidden'; i.name = name; i.dataset.added = ''; form.appendChild(i); }
    i.value = value;
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('form[data-takeout]')) return;
    //the checked bar's other button (Put in folder) goes straight through
    var sub = e.submitter;
    if (form.dataset.takeout === 'remove' && !(sub && sub.name === 'action' && sub.value === 'remove')) return;
    if (form.dataset.asked === '1') { delete form.dataset.asked; return; }
    e.preventDefault();
    e.stopImmediatePropagation();
    if ('takeoutShown' in form.dataset) {
      var f = window.qgenShownFolder(form);
      if (!f) return;
      hidden(form, 'folder', f);
    }
    //the checked bar: everyone checked (data-takeout-items: which check boxes)
    if (form.dataset.takeoutItems) {
      form.querySelectorAll('input[data-added][name=items]').forEach(function (i) { i.remove(); });
      var seen = {};
      document.querySelectorAll(form.dataset.takeoutItems).forEach(function (b) {
        if (seen[b.value]) return;
        seen[b.value] = 1;
        var i = document.createElement('input'); i.type = 'hidden'; i.name = 'items'; i.value = b.value; i.dataset.added = '';
        form.appendChild(i);
      });
    }
    var data = new FormData(form);
    if (sub && sub.name) data.set(sub.name, sub.value);
    data.set('check', '1');
    fetchJson(form.action, data).then(function (res) {
      if (!res.ok) { window.qgenSay(res.error || 'That didn\'t work. Please reload the page and try again.', 'error'); return; }
      var go = function (choice) {
        if (choice) hidden(form, 'confirm', choice);
        if (sub && sub.name) hidden(form, sub.name, sub.value);
        form.dataset.asked = '1';
        form.submit();
      };
      if (!res.question) { go(null); return; }
      window.qgenChoose(res.question, window.qgenTakeOutChoices).then(function (choice) { if (choice) go(choice); });
    });
  }, true);

  //buttons that act on the folder shown: grayed, with why, while no folder is shown
  function mark() {
    document.querySelectorAll('form[data-takeout-shown] button').forEach(function (b) {
      var f = window.qgenShownFolder(b);
      b.disabled = !f;
      if (!b.dataset.tip) b.dataset.tip = b.title;
      b.title = f ? b.dataset.tip : 'Open a folder to take things out of it';
    });
  }
  document.addEventListener('qgen-shown', mark);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mark); else mark();
})();
