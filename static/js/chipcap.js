/* A row of chips (data-chip-cap="10": a list's folders and quizzes, a quiz's problems, a picker's
 * checked ones) shows its first ten; the rest go in a “+N more” chip that opens them in a card
 * popping out over the page (details.row-pop: static/js/rowopen.js), so a long list never runs
 * to the edge of its card or makes it taller (the owner, 2026-10-26). Scripts that redraw a row
 * call window.qgenChipCap(row) after. */
(function () {
  var CHIP = '.pick-chip, .folder-chip';
  function cap(box) {
    var n = parseInt(box.dataset.chipCap, 10) || 10;
    //(drawn again: what was in the card goes back in its place first)
    var old = box.querySelector(':scope > details.chip-more-pop');
    if (old) {
      Array.prototype.slice.call(old.querySelector('.chip-pop').children).forEach(function (c) { box.insertBefore(c, old); });
      old.remove();
    }
    var chips = Array.prototype.filter.call(box.children, function (c) { return c.matches(CHIP); });
    if (chips.length <= n) return;
    var rest = chips.slice(n);
    var pop = document.createElement('details');
    pop.className = 'row-pop row-more-pop chip-more-pop';
    var more = document.createElement('summary');
    more.className = 'chip-more';
    more.textContent = '+' + rest.length + ' more';
    more.title = 'See the other ' + rest.length;
    var card = document.createElement('div');
    card.className = 'row-pop-body chip-pop';
    rest.forEach(function (c) { card.appendChild(c); });
    pop.appendChild(more);
    pop.appendChild(card);
    box.insertBefore(pop, chips[n - 1].nextSibling);
  }
  function all(root) { (root || document).querySelectorAll('[data-chip-cap]').forEach(cap); }
  window.qgenChipCap = cap;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { all(); });
  else all();
  document.addEventListener('qgen-swapped', function () { all(); });   // (a list swapped in without a reload)
})();
