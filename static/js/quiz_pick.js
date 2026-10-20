/* Problems into quizzes from the Problems page (the owner, 2026-10-15):
 *  - Add to a quiz: a row's icon (that problem) or the checked bar's button (the checked ones)
 *    opens a small dialog to choose the quiz; they go at the end of it (/quiz/addtoquiz).
 *  - Picking for the quiz being built: on New quiz / Edit quiz, "Pick on the Problems page"
 *    keeps what's filled in (this tab only) and goes to the Problems page, which then has a
 *    bar "Choosing problems for …" with the quiz's problems already checked; check and uncheck
 *    there (in any folder), then "Add to the quiz" goes back to the quiz with the problems
 *    checked there in it (Cancel: as it was). Nothing is saved until the quiz is. */
(function () {
  var KEY = 'qgen-quiz-pick', HOURS = 3;
  function get() {
    try {
      var d = JSON.parse(sessionStorage.getItem(KEY) || 'null');
      return d && Date.now() - d.at < HOURS * 3600e3 ? d : null;
    } catch (e) { return null; }
  }
  function put(d) {
    try {
      if (d) { d.at = Date.now(); sessionStorage.setItem(KEY, JSON.stringify(d)); } else sessionStorage.removeItem(KEY);
    } catch (e) {}
  }
  //every problem id in a quiz's list: [4, {"pick": 2, "from": [5, 6]}]
  function idsOf(raw) {
    var out = [];
    try { (JSON.parse(raw || '[]') || []).forEach(function (e) { (e && typeof e === 'object' ? e.from || [] : [e]).forEach(function (id) { out.push(String(id)); }); }); } catch (e) {}
    return out;
  }
  //the quiz's list with just the picked ones: those already in it keep their place (and group),
  //new ones at the end
  function merged(raw, picked) {
    var want = {}, have = {}, out = [], data = [];
    picked.forEach(function (id) { want[id] = 1; });
    try { data = JSON.parse(raw || '[]') || []; } catch (e) {}
    data.forEach(function (e) {
      if (e && typeof e === 'object') {
        var from = (e.from || []).filter(function (id) { return want[id]; });
        from.forEach(function (id) { have[id] = 1; });
        if (from.length) out.push({ pick: Math.min(e.pick || 1, from.length), from: from });
      } else if (want[e]) { have[e] = 1; out.push(e); }
    });
    picked.forEach(function (id) { if (!have[id]) { have[id] = 1; out.push(+id); } });
    return JSON.stringify(out);
  }

  var form = document.getElementById('quiz-form');
  if (form) quizPage(form); else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', problemsPage); else problemsPage();

  /* New quiz / Edit quiz (runs before static/js/quiz_form.js reads the list) */
  function quizPage(form) {
    var hidden = document.getElementById('vplist');
    //what's filled in, each field by its name and place among those with the same name
    function fields(each) {
      var seen = {};
      Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.name || el === hidden || el.name === 'csrf_token' || el.type === 'file' || el.type === 'submit'
            || el.type === 'button' || el.classList.contains('pick')) return;
        var k = el.name + '#' + (seen[el.name] = (seen[el.name] || 0) + 1);
        each(k, el);
      });
    }
    var d = get();
    if (d && d.back && d.url === location.pathname) {
      fields(function (k, el) {
        if (!(k in d.fields)) return;
        if (el.type === 'checkbox' || el.type === 'radio') el.checked = d.fields[k];
        else el.value = d.fields[k];
      });
      hidden.value = merged(d.vplist, d.picked);
      put(null);
    }
    var go = document.getElementById('pick-on-problems');
    if (go) go.addEventListener('click', function (e) {
      e.preventDefault();
      var keep = {};
      fields(function (k, el) { keep[k] = el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.value; });
      var title = form.elements.title ? form.elements.title.value.trim() : '';
      var now = idsOf(hidden.value);
      put({ url: location.pathname, back: false, picking: true, title: title, fields: keep, vplist: hidden.value,
            picked: now, was: now });
      location.href = go.href;
    });
  }

  /* the Problems page */
  function problemsPage() {
    var main = document.querySelector('.folder-main');
    if (!main) return;
    var ticks = Array.prototype.slice.call(main.querySelectorAll('input[name="items"]'));
    function checkedIds() {
      //(everything checked, in other folders too: static/js/checked.js)
      if (window.qgenCheckedIds) return window.qgenCheckedIds();
      //(in the order they're listed, each once)
      var out = [];
      ticks.forEach(function (t) { if (t.checked && out.indexOf(t.value) === -1) out.push(t.value); });
      return out;
    }

    //Add to a quiz
    var dialog = document.getElementById('add-quiz-dialog');
    var barBtn = document.querySelector('[data-add-quiz="checked"]');
    function keepBarBtn() {
      if (barBtn && 'noQuiz' in barBtn.dataset) { barBtn.disabled = true; barBtn.title = 'There are no quizzes yet'; }
    }
    keepBarBtn();
    var fileForm = document.getElementById('file-form');
    if (fileForm) fileForm.addEventListener('change', keepBarBtn);
    ticks.forEach(function (t) { t.addEventListener('change', keepBarBtn); });
    var fromBar = false;  // (opened by the checked bar's button, not one row's)
    function ask(ids, what) {
      if (!dialog || !ids.length) return;
      dialog.querySelector('[data-what]').textContent = what;
      var box = dialog.querySelector('[data-problem-ids]');
      box.innerHTML = '';
      ids.forEach(function (id) {
        var i = document.createElement('input');
        i.type = 'hidden'; i.name = 'items'; i.value = id;
        box.appendChild(i);
      });
      //(the link to a new quiz: these problems in it, and Back comes back to this page and tab)
      var make = dialog.querySelector('[data-new-quiz]');
      if (make) {
        make.textContent = 'Make a new quiz with ' + (ids.length === 1 ? 'it' : 'them') + ' instead';
        make.href = make.getAttribute('href').split('?')[0] + '?problems=' + ids.join(',') + '&next=' + encodeURIComponent(location.pathname + location.search);
      }
      dialog.showModal();
      var first = dialog.querySelector('.filter-list:not([hidden])') || dialog.querySelector('input[name=quiz]');
      if (first) first.focus();
    }
    if (dialog) {
      dialog.querySelector('[data-cancel]').addEventListener('click', function () { dialog.close(); });
      //(like the Assign dialogs: the Quizzes page's folder list and the filter narrow the list
      //(folderfilter.js, filter.js); Check all shown / Uncheck all; as many quizzes as wanted)
      var err = dialog.querySelector('[data-quiz-error]');
      var rows = Array.prototype.slice.call(dialog.querySelectorAll('.add-quiz-list > li'));
      var count = dialog.querySelector('[data-quiz-count]');
      function sync() {
        var n = dialog.querySelectorAll('input[name=quiz]:checked').length;
        if (count) count.textContent = n + ' checked';
        if (n) err.hidden = true;
      }
      dialog.addEventListener('change', sync);
      dialog.querySelector('[data-quizzes="all"]').addEventListener('click', function () {
        rows.forEach(function (li) { if (li.offsetParent) li.querySelector('input').checked = true; }); sync();
      });
      dialog.querySelector('[data-quizzes="none"]').addEventListener('click', function () {
        rows.forEach(function (li) { li.querySelector('input').checked = false; }); sync();
      });
      sync();
      dialog.querySelector('form').addEventListener('submit', function (e) {
        if (!dialog.querySelector('input[name=quiz]:checked')) { e.preventDefault(); err.hidden = false; }
    if (!e.defaultPrevented && fromBar && window.qgenCheckedClear) window.qgenCheckedClear();  // (the checked ones done: nothing stays checked)
  });
    }
    document.addEventListener('click', function (e) {
      var b = e.target.closest('[data-add-quiz]');
      if (!b || b.disabled) return;
      if (b.dataset.addQuiz === 'checked') {
        var ids = checkedIds();
        fromBar = true;
        ask(ids, ids.length === 1 ? 'the checked problem' : 'the ' + ids.length + ' checked problems');
      } else { fromBar = false; ask([b.dataset.addQuiz], b.dataset.what); }
    });

    //picking for the quiz being built
    var d = get();
    if (!d || !d.picking) return;
    var bar = main.querySelector('.folder-tools-bar');
    if (!bar) return;
    var picked = {};
    d.picked.forEach(function (id) { picked[id] = 1; });
    ticks.forEach(function (t) { t.checked = !!picked[t.value]; });
    if (ticks[0]) ticks[0].dispatchEvent(new Event('change', { bubbles: true }));  // (the checked bar counts them)
    var banner = document.createElement('div');
    banner.className = 'pick-banner';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-label', 'Choosing problems for a quiz');
    var p = document.createElement('p');
    var strong = document.createElement('strong');
    strong.textContent = d.title ? 'Choosing problems for “' + d.title + '”' : 'Choosing problems for your new quiz';
    var how = document.createElement('span');
    how.className = 'muted small';
    how.textContent = ': check the ones you want (in any folder), then press Add to the quiz. ';
    var count = document.createElement('span');
    count.className = 'badge badge-accent pick-count';
    p.appendChild(strong); p.appendChild(how); p.appendChild(count);
    var add = document.createElement('button');
    add.type = 'button'; add.className = 'btn btn-sm'; add.textContent = 'Add to the quiz';
    add.title = 'Go back to the quiz with the checked problems in it';
    var cancel = document.createElement('button');
    cancel.type = 'button'; cancel.className = 'btn btn-secondary btn-sm'; cancel.textContent = 'Cancel';
    cancel.title = 'Go back to the quiz without changing its problems';
    var row = document.createElement('div');
    row.className = 'btn-row';
    row.appendChild(add); row.appendChild(cancel);
    banner.appendChild(p); banner.appendChild(row);
    bar.insertBefore(banner, bar.firstChild);
    function sync() {
      var n = Object.keys(picked).length;
      count.textContent = n + ' checked';
    }
    sync();
    ticks.forEach(function (t) {
      t.addEventListener('change', function () {
        if (t.checked) picked[t.value] = 1; else delete picked[t.value];
        d.picked = Object.keys(picked);
        put(d);
        sync();
      });
    });
    function back(ids) {
      d.picked = ids; d.back = true; d.picking = false;
      put(d);
      location.href = d.url;
    }
    add.addEventListener('click', function () {
      //(in the quiz's own order first, then the new ones in the order they're listed here)
      var order = d.was.filter(function (id) { return picked[id]; });
      ticks.forEach(function (t) { if (picked[t.value] && order.indexOf(t.value) === -1) order.push(t.value); });
      Object.keys(picked).forEach(function (id) { if (order.indexOf(id) === -1) order.push(id); });
      back(order);
    });
    cancel.addEventListener('click', function () { back(d.was); });
  }
})();
