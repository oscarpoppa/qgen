/* "Choose pictures" (templates/_dialog_pick_pictures.html; the owner, 2026-10-19):
 * qgenPickPictures({ single: bool, onPick: function ([{ name, url }]) }).
 * Several: check any number, then Add (the problem editor's card button: a slot each).
 * Single: picking one unchecks the rest, then "Use this picture" (a slot's own button). */
(function () {
  var box = document.getElementById('pick-pictures-dialog');
  if (!box) return;
  var head = box.querySelector('[data-head]'), ok = box.querySelector('[data-ok]');
  var err = box.querySelector('[data-pics-error]'), count = box.querySelector('[data-pics-count]');
  var single = false, onPick = null;
  function boxes() { return box.querySelectorAll('input[name=pick-pic]'); }
  function recount() {
    var n = box.querySelectorAll('input[name=pick-pic]:checked').length;
    if (count) count.textContent = n + ' checked';
    if (n) err.hidden = true;
  }
  box.addEventListener('change', function (e) {
    if (e.target.name !== 'pick-pic') return;
    if (single && e.target.checked) boxes().forEach(function (b) { if (b !== e.target) b.checked = false; });
    recount();
  });
  box.addEventListener('click', function (e) {
    var b = e.target.closest('[data-pics]');
    if (b) {
      boxes().forEach(function (c) {
        if (b.dataset.pics === 'none') c.checked = false;
        else if (c.closest('li').offsetParent) c.checked = true;  // (only the ones shown)
      });
      recount();
    }
    if (e.target.closest('[data-cancel]')) box.close();
  });
  ok.addEventListener('click', function () {
    var picked = Array.prototype.filter.call(boxes(), function (b) { return b.checked; })
      .map(function (b) { return { name: b.value, url: b.dataset.url }; });
    if (!picked.length) { err.hidden = false; return; }
    box.close();
    if (onPick) onPick(single ? picked.slice(0, 1) : picked);
  });
  window.qgenPickPictures = function (opts) {
    single = !!opts.single; onPick = opts.onPick;
    head.textContent = single ? 'Choose a picture' : 'Choose pictures';
    ok.textContent = single ? 'Use this picture' : 'Add';
    box.querySelectorAll('[data-many-only]').forEach(function (el) { el.hidden = single; });
    boxes().forEach(function (b) { b.checked = false; });
    err.hidden = true;
    recount();
    box.showModal();
  };
})();
