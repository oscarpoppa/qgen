/* Drag-and-drop picture picker.
 *
 * <div class="dropzone" data-target="image" data-upload="/upload/json" data-list="/upload/imagelist">
 * Drop or choose a file and it is uploaded right away; the file name goes
 * into the hidden input named by data-target. With data-multiple (upload
 * page) several files can be dropped at once and the page reloads after.
 */
(function () {
  function csrf() {
    var m = document.querySelector('meta[name=csrf-token]');
    return m ? m.content : '';
  }

  function upload(zone, file) {
    var body = new FormData();
    body.append('file', file);
    return fetch(zone.dataset.upload, {
      method: 'POST', body: body, credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrf() }
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: 'Upload failed (' + r.status + ').' }; });
    });
  }

  function setup(zone) {
    var input = zone.querySelector('input[type=file]');
    var hidden = zone.dataset.target ? document.getElementById(zone.dataset.target) : null;
    var field = zone.closest('.field') || zone.parentNode;
    var preview = zone.querySelector('.dz-preview');
    var name = zone.querySelector('.dz-name');
    var hint = zone.querySelector('.dz-hint');
    var hintText = hint ? hint.textContent : '';
    var clearBtn = field.querySelector('.dz-clear');
    var pickBtn = field.querySelector('.dz-pick');
    var gallery = field.querySelector('.dz-gallery');
    var multiple = zone.hasAttribute('data-multiple');
    if (multiple) input.multiple = true;

    function show(file, url) {
      if (hidden && hidden.value !== (file || '')) {
        hidden.value = file || '';
        //so the page's Helper (and anything else watching the form) checks it again
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      }
      if (preview) {
        if (url) { preview.src = url; preview.hidden = false; } else { preview.removeAttribute('src'); preview.hidden = true; }
      }
      if (name) name.textContent = file || '';
      if (clearBtn) clearBtn.hidden = !file;
    }

    function status(text, bad) {
      if (!hint) return;
      hint.textContent = text || hintText;
      hint.style.color = bad ? 'var(--bad)' : '';
    }

    function handle(files) {
      files = Array.prototype.slice.call(files || []);
      if (!files.length) return;
      if (!multiple) files = files.slice(0, 1);
      zone.classList.add('busy');
      status('Uploading ' + (files.length > 1 ? files.length + ' files' : files[0].name) + '…');
      var done = 0, failed = [];
      files.reduce(function (p, f) {
        return p.then(function () {
          return upload(zone, f).then(function (res) {
            if (res.ok) {
              done++;
              if (!multiple) show(res.name, res.url);
              zone.dispatchEvent(new CustomEvent('dropzone-uploaded', { bubbles: true, detail: res }));
            }
            else failed.push(f.name + ': ' + (res.error || 'upload failed'));
          }, function () { failed.push(f.name + ': network error'); });
        });
      }, Promise.resolve()).then(function () {
        zone.classList.remove('busy');
        if (failed.length) status(failed.join(' · '), true);
        else status(multiple ? 'Uploaded ' + done + ' file' + (done === 1 ? '' : 's') + '.' : 'Uploaded.');
        if (multiple && done) setTimeout(function () { location.reload(); }, 600);
      });
    }

    zone.addEventListener('click', function (e) { if (e.target !== input) input.click(); });
    zone.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
    });
    input.addEventListener('change', function () { handle(input.files); input.value = ''; });
    ['dragenter', 'dragover'].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add('over'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove('over'); });
    });
    zone.addEventListener('drop', function (e) { handle(e.dataTransfer.files); });

    if (clearBtn) clearBtn.addEventListener('click', function () { show('', ''); status(''); });

    if (pickBtn && gallery) {
      pickBtn.addEventListener('click', function () {
        if (!gallery.hidden) { gallery.hidden = true; return; }
        gallery.innerHTML = '<p class="muted">Loading…</p>';
        gallery.hidden = false;
        fetch(zone.dataset.list, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (items) {
          gallery.innerHTML = '';
          if (!items.length) { gallery.innerHTML = '<p class="muted">No pictures uploaded yet.</p>'; return; }
          items.forEach(function (it) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'thumb btn-secondary';
            b.title = 'Use ' + it.name + ' as the picture';
            var img = document.createElement('img');
            img.src = it.thumb; img.alt = '';
            var cap = document.createElement('div');
            cap.className = 'name'; cap.textContent = it.name;
            b.appendChild(img); b.appendChild(cap);
            b.addEventListener('click', function () { show(it.name, it.url); gallery.hidden = true; status(''); });
            gallery.appendChild(b);
          });
        }, function () { gallery.innerHTML = '<p class="muted">Couldn\'t load pictures.</p>'; });
      });
    }
  }

  function init() { document.querySelectorAll('.dropzone').forEach(setup); }
  /* for drop zones added to the page later (e.g. "+ Add a picture") */
  window.qgenDropzone = setup;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
