/* Scan workbook pages: the review page (app/qgen/templates/scan_review.html).
 * - while the AI reads, check on it and reload when it's done
 * - crop boxes over each page picture: drag to move, drag a corner to resize; they
 *   write "left,top,right,bottom" (fractions of the page) into their hidden input
 * - "+ Add a picture", remove, the question kind and "Use the page's numbers" switches
 * - "Check and show examples": the item as it stands, checked by the server (nothing saved) */
(function () {
  function csrf() { return document.querySelector('meta[name=csrf-token]').content; }

  /* ---------- reading progress ---------- */
  var progress = document.getElementById('scan-progress');
  if (progress) {
    var words = { waiting: 'waiting', reading: 'reading…', done: 'done ✓', error: 'couldn’t be read' };
    var poll = function () {
      fetch(progress.dataset.status, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (s) {
        var done = 0;
        s.pages.forEach(function (p) {
          var li = progress.querySelector('li[data-n="' + p.n + '"] span');
          if (li) li.textContent = words[p.state] || p.state;
          if (p.state === 'done' || p.state === 'error') done += 1;
        });
        var now = s.pages.filter(function (p) { return p.state === 'reading'; })[0];
        document.getElementById('scan-progress-line').textContent = now
          ? 'Reading page ' + now.n + ' of ' + s.pages.length + '…'
          : done + ' of ' + s.pages.length + ' pages read';
        if (!s.reading) location.replace(location.href);
        else setTimeout(poll, 4000);
      }).catch(function () { setTimeout(poll, 8000); });
    };
    setTimeout(poll, 2000);
    return;
  }

  var form = document.getElementById('scan-form');
  if (!form) return;

  /* ---------- crop boxes ---------- */
  function readBox(input) {
    var p = (input.value || '').split(',').map(parseFloat);
    if (p.length !== 4 || p.some(isNaN)) p = [0, 0, 1, 1];
    return { l: p[0], t: p[1], r: p[2], b: p[3] };
  }
  function writeBox(input, b) {
    input.value = [b.l, b.t, b.r, b.b].map(function (v) { return Math.round(v * 10000) / 10000; }).join(',');
  }
  function place(crop) {
    var input = document.getElementById(crop.dataset.for);
    if (!input) { crop.hidden = true; return; }
    var b = readBox(input);
    crop.style.left = (b.l * 100) + '%';
    crop.style.top = (b.t * 100) + '%';
    crop.style.width = ((b.r - b.l) * 100) + '%';
    crop.style.height = ((b.b - b.t) * 100) + '%';
  }
  function addHandles(crop) {
    ['nw', 'ne', 'sw', 'se'].forEach(function (c) {
      var h = document.createElement('span');
      h.className = 'crop-handle crop-' + c;
      h.dataset.corner = c;
      h.setAttribute('aria-hidden', 'true');
      crop.appendChild(h);
    });
  }
  function setUp(crop) {
    addHandles(crop);
    place(crop);
    crop.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      var canvas = crop.parentElement, rect = canvas.getBoundingClientRect();
      var input = document.getElementById(crop.dataset.for);
      var start = readBox(input), x0 = e.clientX, y0 = e.clientY;
      var corner = e.target.dataset.corner || null;
      crop.setPointerCapture(e.pointerId);
      crop.classList.add('is-dragging');
      var MIN = 0.02;
      function move(ev) {
        var dx = (ev.clientX - x0) / rect.width, dy = (ev.clientY - y0) / rect.height;
        var b = { l: start.l, t: start.t, r: start.r, b: start.b };
        if (!corner) {
          var w = b.r - b.l, h = b.b - b.t;
          b.l = Math.min(Math.max(0, start.l + dx), 1 - w); b.r = b.l + w;
          b.t = Math.min(Math.max(0, start.t + dy), 1 - h); b.b = b.t + h;
        } else {
          if (corner.indexOf('w') !== -1) b.l = Math.min(Math.max(0, start.l + dx), b.r - MIN);
          if (corner.indexOf('e') !== -1) b.r = Math.max(Math.min(1, start.r + dx), b.l + MIN);
          if (corner.indexOf('n') !== -1) b.t = Math.min(Math.max(0, start.t + dy), b.b - MIN);
          if (corner.indexOf('s') !== -1) b.b = Math.max(Math.min(1, start.b + dy), b.t + MIN);
        }
        writeBox(input, b);
        place(crop);
      }
      function up() {
        crop.removeEventListener('pointermove', move);
        crop.removeEventListener('pointerup', up);
        crop.removeEventListener('pointercancel', up);
        crop.classList.remove('is-dragging');
      }
      crop.addEventListener('pointermove', move);
      crop.addEventListener('pointerup', up);
      crop.addEventListener('pointercancel', up);
    });
  }
  form.querySelectorAll('.crop').forEach(setUp);

  //"remove" on a picture hides its box (and puts it back when unchecked)
  form.addEventListener('change', function (e) {
    var t = e.target;
    if (t.classList.contains('scan-pic-remove')) {
      var row = t.closest('.scan-pic');
      var crop = form.querySelector('.crop[data-for="' + row.dataset.box + '"]');
      if (crop) crop.hidden = t.checked;
      row.classList.toggle('is-off', t.checked);
    }
    if (t.classList.contains('scan-include')) t.closest('.scan-item').classList.toggle('is-off', !t.checked);
    if (t.classList.contains('scan-use-page')) showFixed(t.closest('.scan-item'));
    if (t.classList.contains('scan-qtype')) showChoices(t.closest('.scan-item'));
    if (t.classList.contains('scan-kind')) showKind(t.closest('.scan-value'));
  });

  //a crop box the AI missed
  var added = 0, template = document.getElementById('scan-new-pic');
  form.querySelectorAll('.scan-add-pic').forEach(function (btn) {
    btn.addEventListener('click', function () {
      added += 1;
      var n = btn.dataset.page, pre = 'p' + n, id = 'new' + added;
      var html = template.innerHTML.replace(/__P__/g, pre).replace(/__ID__/g, id);
      var list = form.querySelector('.scan-pics[data-page="' + n + '"]');
      var wrap = document.createElement('div');
      wrap.innerHTML = html.trim();
      var row = wrap.firstElementChild;
      list.appendChild(row);
      var crop = document.createElement('div');
      crop.className = 'crop crop-new';
      crop.dataset.for = pre + '-' + id + '-box';
      crop.title = 'New picture: drag to move, drag the corners to resize';
      crop.innerHTML = '<span class="crop-label">🖼 new picture</span>';
      form.querySelector('.scan-canvas[data-page="' + n + '"]').appendChild(crop);
      setUp(crop);
      var label = row.querySelector('input[type=text]');
      if (label) label.focus();
    });
  });

  /* ---------- an item's fields ---------- */
  var CHOICE = ['choice_one', 'choice_many'];
  function showFixed(item) {
    var fixed = item.querySelector('.scan-use-page');
    if (!fixed) return;
    item.querySelector('.scan-random').hidden = fixed.checked;
    item.querySelector('.scan-fixed').hidden = !fixed.checked;
  }
  function showChoices(item) {
    var q = item.querySelector('.scan-qtype');
    if (!q) return;
    item.querySelectorAll('.t-choice').forEach(function (el) { el.hidden = CHOICE.indexOf(q.value) === -1; });
  }
  function showKind(row) {
    var kind = row.querySelector('.scan-kind').value;
    row.dataset.kind = kind;
    row.querySelectorAll('[class*="k-"]').forEach(function (el) {
      var kinds = Array.prototype.filter.call(el.classList, function (c) { return c.indexOf('k-') === 0; });
      if (kinds.length) el.hidden = kinds.indexOf('k-' + kind) === -1;
    });
  }
  form.querySelectorAll('.scan-item').forEach(function (item) { showFixed(item); showChoices(item); });
  form.querySelectorAll('.scan-value').forEach(showKind);

  //the item being worked on is lit up on its page
  form.addEventListener('focusin', function (e) {
    var item = e.target.closest('.scan-item');
    form.querySelectorAll('.crop.is-current').forEach(function (c) { c.classList.remove('is-current'); });
    if (!item) return;
    var crop = form.querySelector('.crop[data-for="p' + item.dataset.page + 'i' + item.dataset.item + '-box"]');
    if (crop) crop.classList.add('is-current');
  });

  /* ---------- check one item ---------- */
  form.addEventListener('click', function (e) {
    var btn = e.target.closest('.scan-try');
    if (!btn) return;
    var item = btn.closest('.scan-item'), out = item.querySelector('.scan-check');
    var data = new FormData(form);
    data.set('page', item.dataset.page);
    data.set('item', item.dataset.item);
    btn.disabled = true;
    out.textContent = 'Checking…';
    fetch(form.dataset.check, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() } })
      .then(function (r) { return r.json(); })
      .then(function (res) { if (res.ok) out.innerHTML = res.html; else out.textContent = res.error; })
      .catch(function () { out.textContent = 'Couldn’t check it just now. Please try again.'; })
      .then(function () { btn.disabled = false; });
  });
})();
