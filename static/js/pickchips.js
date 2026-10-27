/* A picker card's checked ones as chips (their names, A to Z), kept up as boxes are checked; each
 * one's ✕ unchecks it (the owner, 2026-10-24): the Assign page's Quiz and Students cards, the Add
 * to quizzes page. The card holds <div class="pick-chips" data-chips-for="(the boxes' name)">, with
 * data-chip-icon="(an icon's name)" when its chips carry one. */
(function () {
  document.querySelectorAll('.pick-chips[data-chips-for]').forEach(function (box) {
    var card = box.closest('.card'), name = box.dataset.chipsFor, t = null;
    function draw() {
      var byName = {}, names = [];
      card.querySelectorAll('input[name="' + name + '"]:checked').forEach(function (b) {
        var l = card.querySelector('label[for="' + b.id + '"]');
        var n = l ? (l.firstChild && l.firstChild.nodeType === 3 ? l.firstChild.textContent : l.textContent).trim() : '';
        if (!n) return;
        if (!byName[n]) names.push(byName[n] = { n: n, boxes: [] });
        byName[n].boxes.push(b);
      });
      box.textContent = '';
      //(each one's ✕ unchecks it: the owner, 2026-10-24)
      names.sort(function (a, b) { return a.n.localeCompare(b.n); }).forEach(function (it) {
        var c = document.createElement('span'), x = document.createElement('button');
        c.className = 'pick-chip';
        //(a quiz's chip has the quiz drawing, a person's the person: the owner, 2026-10-26)
        if (box.dataset.chipIcon && window.qgenIcon) c.innerHTML = window.qgenIcon(box.dataset.chipIcon);
        c.appendChild(document.createTextNode(it.n));
        x.type = 'button'; x.className = 'chip-x'; x.textContent = '✕';
        x.setAttribute('aria-label', 'Uncheck ' + it.n); x.title = 'Uncheck “' + it.n + '”';
        x.addEventListener('click', function () {
          it.boxes.forEach(function (b) { b.checked = false; b.dispatchEvent(new Event('change', { bubbles: true })); });
        });
        c.appendChild(x);
        box.appendChild(c);
      });
      box.hidden = !names.length;
      if (window.qgenChipCap) window.qgenChipCap(box);  // (the first ten; the rest in a “+N more” card)
    }
    card.addEventListener('change', function () { clearTimeout(t); t = setTimeout(draw, 0); });
    draw();
  });
})();
