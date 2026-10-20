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
    //(a dropped folder's name, for its Pictures folder: used once)
    if (zone.dataset.folder) { body.append('folder', zone.dataset.folder); delete zone.dataset.folder; }
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
    //(Upload files: a tile for each file as it goes up, then ✓ and where it went)
    var done = (zone.closest('.card') || document).querySelector('[data-dz-done]');
    //(Upload files, two steps: what's dropped or chosen waits in the box, each with a ✕, until
    //the page's Upload button sends them all: the owner, 2026-10-19)
    var goBtn = zone.dataset.stageBtn ? document.querySelector(zone.dataset.stageBtn) : null;
    var pending = [];
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

    //a tile for a file going up: its own picture (or the file's extension), its name, then a
    //check mark and a link to where it went, or the reason it failed
    function tile(f) {
      if (!done) return null;
      var t = document.createElement('figure');
      t.className = goBtn ? 'dz-tile pending' : 'dz-tile busy';
      t.title = f.name;
      if (/^image\//.test(f.type)) {
        var img = document.createElement('img'); img.alt = ''; img.src = URL.createObjectURL(f);
        img.onload = function () { URL.revokeObjectURL(img.src); };
        t.appendChild(img);
      } else {
        var ext = document.createElement('span'); ext.className = 'dz-tile-ext';
        ext.textContent = (f.name.split('.').pop() || 'file').slice(0, 5).toUpperCase();
        t.appendChild(ext);
      }
      var cap = document.createElement('figcaption');
      cap.innerHTML = '<span class="dz-tile-name"></span><span class="dz-tile-where muted">' + (goBtn ? '' : 'Uploading…') + '</span>';
      cap.firstChild.textContent = f.name;
      t.appendChild(cap);
      if (goBtn) {
        var x = document.createElement('button');
        x.type = 'button'; x.className = 'dz-tile-x'; x.textContent = '\u2715';
        x.title = 'Take \u201c' + f.name + '\u201d out (it isn\u2019t uploaded)';
        x.setAttribute('aria-label', x.title);
        x.addEventListener('click', function (e) {
          e.stopPropagation();
          pending = pending.filter(function (p) { return p.t !== t; });
          t.remove();
          if (!done.children.length) done.hidden = true;
          ready();
        });
        t.appendChild(x);
      }
      done.hidden = false;
      done.appendChild(t);
      return t;
    }
    function finish(t, res) {
      t.classList.remove('busy');
      var where = t.querySelector('.dz-tile-where');
      if (res.ok) {
        t.classList.add('saved');
        t.querySelector('.dz-tile-name').textContent = res.name;
        var pic = !!res.picture;
        if (res.thumb && !t.querySelector('img')) {
          var img = document.createElement('img'); img.alt = ''; img.src = res.thumb;
          t.replaceChild(img, t.querySelector('.dz-tile-ext'));
        }
        where.innerHTML = '';
        where.className = 'dz-tile-where';
        var a = document.createElement('a');
        a.href = pic ? done.dataset.pictures : done.dataset.files;
        a.textContent = '\u2713 ' + (pic ? 'Pictures' : 'Other files');
        a.title = 'Saved in ' + (pic ? 'Pictures' : 'Other files') + ': open that page';
        where.appendChild(a);
      } else {
        t.classList.add('failed');
        where.className = 'dz-tile-where';
        where.textContent = res.error || 'Upload failed';
      }
    }

    //the Upload button: grayed, with why, while nothing waits in the box
    function ready() {
      if (!goBtn) return;
      goBtn.disabled = !pending.length;
      goBtn.title = pending.length ? 'Upload the ' + (pending.length === 1 ? 'file' : pending.length + ' files') + ' in the box' : 'Drop or choose files first';
    }
    ready();
    if (goBtn) goBtn.addEventListener('click', function () {
      if (!pending.length) return;
      var list = pending; pending = []; ready();
      send(list);
    });

    function handle(files) {
      files = Array.prototype.slice.call(files || []);
      if (!files.length) return;
      if (!multiple) files = files.slice(0, 1);
      if (goBtn) {
        files.forEach(function (f) { pending.push({ f: f, t: tile(f) }); });
        ready();
        return;
      }
      send(files.map(function (f) { return { f: f, t: tile(f) }; }));
    }

    function send(list) {
      var files = list.map(function (p) { return p.f; });
      list.forEach(function (p) {
        if (!p.t) return;
        p.t.classList.remove('pending'); p.t.classList.add('busy');
        var x = p.t.querySelector('.dz-tile-x'); if (x) x.remove();
        p.t.querySelector('.dz-tile-where').textContent = 'Uploading…';
      });
      zone.classList.add('busy');
      status('Uploading ' + (files.length > 1 ? files.length + ' files' : files[0].name) + '…');
      var ok = 0, failed = [];
      list.reduce(function (p, item) {
        var f = item.f, t = item.t;
        return p.then(function () {
          return upload(zone, f).then(function (res) {
            if (t) finish(t, res);
            if (res.ok) {
              ok++;
              if (!multiple) show(res.name, res.url);
              zone.dispatchEvent(new CustomEvent('dropzone-uploaded', { bubbles: true, detail: res }));
            }
            else failed.push(f.name + ': ' + (res.error || 'upload failed'));
          }, function () { if (t) finish(t, { ok: false, error: 'network error' }); failed.push(f.name + ': network error'); });
        });
      }, Promise.resolve()).then(function () {
        zone.classList.remove('busy');
        if (failed.length) status(failed.join(' · '), true);
        else status(multiple ? 'Uploaded ' + ok + ' file' + (ok === 1 ? '' : 's') + '.' : 'Uploaded.');
        //(with the tiles there's no need to reload: they show what was saved)
        if (multiple && ok && !done) setTimeout(function () { location.reload(); }, 600);
        //(the tiles stay; the box's own line goes back to saying what to do)
        if (multiple && done && !failed.length) setTimeout(function () { status(''); }, 4000);
      });
    }

    zone.addEventListener('click', function (e) {
      //(a tile's link opens its page; its ✕ takes it out; a click on a tile does nothing)
      if (e.target === input || (e.target.closest && e.target.closest('a, [data-dz-done]'))) return;
      input.click();
    });
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
    zone.addEventListener('drop', function (e) {
      //(a folder: the problem editor's Pictures card takes it, a slot for each picture)
      var items = e.dataTransfer.items || [], entries = [], folder = false;
      for (var i = 0; i < items.length; i++) {
        var en = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
        if (en) entries.push(en);
        if (en && en.isDirectory) folder = true;
      }
      if (!folder) { handle(e.dataTransfer.files); return; }
      if (!goBtn) return;
      //(Upload files: a folder's files, and those in folders inside it, in name order)
      var got = [];
      function walk(entry) {
        return new Promise(function (ok) {
          if (entry.isFile) { entry.file(function (f) { got.push(f); ok(); }, function () { ok(); }); return; }
          var reader = entry.createReader(), all = [];
          (function more() {
            reader.readEntries(function (batch) {
              if (batch.length) { all = all.concat(Array.prototype.slice.call(batch)); more(); return; }
              all.sort(function (a, b) { return a.name.localeCompare(b.name, undefined, { numeric: true }); });
              all.reduce(function (p, c) { return p.then(function () { return walk(c); }); }, Promise.resolve()).then(ok);
            }, function () { ok(); });
          })();
        });
      }
      entries.reduce(function (p, c) { return p.then(function () { return walk(c); }); }, Promise.resolve())
        .then(function () { handle(got); });
    });
    //(so a page can hand this zone files dropped somewhere else, e.g. the problem editor's Pictures card)
    zone.qgenHandle = handle;
    zone.qgenShow = function (file, url) { show(file, url); status(''); };

    if (clearBtn) clearBtn.addEventListener('click', function () { show('', ''); status(''); });

    if (pickBtn && gallery) {
      pickBtn.addEventListener('click', function () {
        //(the problem editor: the "Choose a picture" dialog, one picture for this slot)
        if (window.qgenPickPictures) {
          window.qgenPickPictures({ single: true, onPick: function (p) { show(p[0].name, p[0].url); status(''); } });
          return;
        }
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

  //(a zone with data-own is run by its page's own script)
  function init() { document.querySelectorAll('.dropzone:not([data-own])').forEach(setup); }
  /* for drop zones added to the page later (e.g. a new picture slot) */
  window.qgenDropzone = setup;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
