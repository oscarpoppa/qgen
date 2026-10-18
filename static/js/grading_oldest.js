/* Grading: "The 5 oldest waiting" (the owner, 2026-10-17). Its button under the folder list
 * opens it as a pop-over beside the folders; it closes with its ✕, Esc or a click elsewhere.
 * Pinned (the pin in its heading), it sits in the page under the folders instead and stays open
 * until closed. Pinned or not, and open or not when pinned, is remembered in this browser. */
(function () {
  var card = document.getElementById('grading-oldest'), btn = document.querySelector('.oldest-toggle');
  if (!card || !btn) return;
  var pin = card.querySelector('.oldest-pin'), close = card.querySelector('.oldest-close');
  var home = card.parentElement, next = card.nextSibling;
  var KEY = 'qgen-grading-oldest';
  var state = { pinned: false, open: false };
  try { state = Object.assign(state, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  //(the open folder makes room for it, or takes the room back: static/js/folderfilter.js)
  function refit() { window.dispatchEvent(new Event('resize')); }

  function place() {
    var r = btn.getBoundingClientRect(), side = btn.closest('.folder-side');
    var left = (side ? side.getBoundingClientRect().right : r.right) + 8;
    card.style.left = left + 'px';
    card.style.top = Math.max(8, Math.min(r.top, window.innerHeight - card.offsetHeight - 8)) + 'px';
    card.style.width = Math.min(900, window.innerWidth - left - 16) + 'px';
  }
  function draw(open) {
    var floating = !state.pinned;
    card.classList.toggle('oldest-pop', floating);
    if (floating && card.parentElement !== document.body) document.body.appendChild(card);
    if (!floating && card.parentElement !== home) home.insertBefore(card, next);
    if (!floating) { card.style.left = card.style.top = card.style.width = ''; }
    card.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    pin.setAttribute('aria-pressed', state.pinned ? 'true' : 'false');
    window.qgenIconButton(pin, state.pinned ? 'lc-pin-off' : 'pin', state.pinned ? 'Unpin' : 'Pin',
      state.pinned ? 'Let it float over the page from its button, closing when you click elsewhere' : 'Keep it in the page, under the quizzes, until you close it');
    if (open && floating) place();
    refit();
  }
  btn.addEventListener('click', function () {
    var open = card.hidden;
    if (state.pinned) { state.open = open; save(); }
    draw(open);
    if (open && state.pinned) card.scrollIntoView({ block: 'nearest' });
  });
  pin.addEventListener('click', function () {
    state.pinned = !state.pinned;
    state.open = state.pinned;
    save();
    draw(true);
  });
  close.addEventListener('click', function () {
    if (state.pinned) { state.open = false; save(); }
    draw(false);
    btn.focus();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !state.pinned && !card.hidden) { draw(false); btn.focus(); }
  });
  document.addEventListener('mousedown', function (e) {
    if (state.pinned || card.hidden || card.contains(e.target) || btn.contains(e.target)) return;
    draw(false);
  });
  window.addEventListener('resize', function () { if (!state.pinned && !card.hidden) place(); });
  draw(state.pinned && state.open);
})();
