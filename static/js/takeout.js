/* Taking things out of a folder, the same on every folder page (app/takeout.py): every form
 * marked data-takeout (a folder chip's ✕, "Take out of folder" on the checked bar, a card's
 * "Remove", which first asks which folder when it's in several: data-takeout-pick) first asks
 * the site what would happen (check=1). Something that would be left
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

  //canDelete false: nothing left can be deleted (the question says why), so that choice is grayed
  window.qgenTakeOutChoices = function (canDelete) {
    return [{ value: 'delete', label: 'Delete for good', danger: true, title: 'Delete it (asked because it’s in no other folder)',
              disabled: canDelete === false ? 'It can’t be deleted (the question above says why)' : null },
            { value: 'uncategorized', label: 'Put in Uncategorized', title: 'Keep it, in no folder' }];
  };

  function fetchJson(url, data) {
    return fetch(url, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.json().catch(function () { return { ok: false }; }); });
  }

  //(a field the form already has, e.g. Remove's folder, is set; else one is added for this sending)
  function hidden(form, name, value) {
    var i = form.querySelector('input[type=hidden][name="' + name + '"]:not([data-added])') ||
            form.querySelector('input[type=hidden][name="' + name + '"][data-added]');
    if (!i) { i = document.createElement('input'); i.type = 'hidden'; i.name = name; i.dataset.added = ''; form.appendChild(i); }
    i.value = value;
  }

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches || !form.matches('form[data-takeout]')) return;
    var sub = e.submitter;
    //(both of the bar's buttons) the checked bar: everyone checked (data-takeout-items: which check boxes)
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
    //the checked bar's other button (Put in folder) goes straight through
    if (form.dataset.takeout === 'remove' && !(sub && sub.name === 'action' && sub.value === 'remove')) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    clean(form);
    if ('takeoutShown' in form.dataset) {
      var f = window.qgenShownFolder(form);
      if (!f) return;
      hidden(form, 'folder', f);
    }
    //a card's Remove: in several folders, which one?
    if ('takeoutPick' in form.dataset) {
      var ids = JSON.parse(form.dataset.folders || '[]'), names = JSON.parse(form.dataset.names || '[]');
      if (ids.length > 1) {
        window.qgenChoose('Remove ' + form.dataset.label + ' from which folder?',
          ids.map(function (id, i) { return { value: String(id), label: names[i], title: 'Take it out of “' + names[i] + '”' }; }))
          .then(function (f) { if (f) { hidden(form, 'folder', f); send(form, sub); } });
        return;
      }
    }
    send(form, sub);
  }, true);

  //added fields never outlive one sending (a page brought back with the browser's Back button
  //must ask again)
  function clean(form) { form.querySelectorAll('input[data-added]').forEach(function (i) { if (i.name !== 'items' && (i.name !== 'folder' || !('takeoutShown' in form.dataset || 'takeoutPick' in form.dataset))) i.remove(); }); }
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('form[data-takeout]').forEach(function (form) { form.querySelectorAll('input[data-added]').forEach(function (i) { i.remove(); }); });
  });

  function send(form, sub) {
    var data = new FormData(form);
    if (sub && sub.name) data.set(sub.name, sub.value);
    data.set('check', '1');
    fetchJson(form.action, data).then(function (res) {
      if (!res.ok) { window.qgenSay(res.error || 'That didn\'t work. Please reload the page and try again.', 'error'); return; }
      var go = function (choice) {
        if (choice) hidden(form, 'confirm', choice);
        if (sub && sub.name) hidden(form, sub.name, sub.value);
        form.submit();  // (no submit event: not asked again; the added fields go with it)
      };
      if (!res.question) { go(null); return; }
      window.qgenChoose(res.question, window.qgenTakeOutChoices(res.can_delete)).then(function (choice) { if (choice) go(choice); });
    });
  }

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
