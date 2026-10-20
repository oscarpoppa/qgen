/* Quiz builder: check problems, order them (when the order isn't shuffled), and
 * optionally put some in groups ("each student gets 2 of these 6"); the panel says
 * how many questions each student answers. Saved as JSON in the hidden vplist:
 *   [4, {"pick": 2, "from": [5, 6, 7]}, 9]
 */
(function () {
  var hidden = document.getElementById('vplist');
  var list = document.getElementById('order');
  var empty = document.getElementById('order-empty');
  var groupsBox = document.getElementById('groups');
  var total = document.getElementById('order-total');
  var shuffle = document.getElementById('shuffle_order');
  var shuffledNote = document.getElementById('order-shuffled');
  var fixedNote = document.getElementById('order-fixed');
  var LETTERS = 'ABCDEFGH'.split('');
  //a problem in several subjects has a checkbox in each of their containers
  var boxes = {};
  document.querySelectorAll('input.pick').forEach(function (b) { (boxes[b.value] = boxes[b.value] || []).push(b); });
  var container = document.getElementById('all-problems');
  function tick(id, on) {
    boxes[id].forEach(function (b) { b.checked = on; });
    if (container) container.dispatchEvent(new Event('qgen-ticks-changed'));
  }

  var order = [];      // [{id: '5', group: ''|'A'}]
  var picks = {};      // {A: 2}

  /* load what was saved */
  (function load() {
    var raw = hidden.value.trim(), data = [];
    try { data = raw.charAt(0) === '[' ? JSON.parse(raw) : (raw.match(/\d+/g) || []).map(Number); } catch (e) { data = []; }
    var g = 0;
    data.forEach(function (entry) {
      if (entry && typeof entry === 'object') {
        var letter = LETTERS[g++] || 'H';
        picks[letter] = entry.pick;
        (entry.from || []).forEach(function (id) { order.push({ id: String(id), group: letter }); });
      } else {
        order.push({ id: String(entry), group: '' });
      }
    });
  })();

  function save() {
    var out = [], seen = {};
    order.forEach(function (item) {
      if (!item.group) { out.push(+item.id); return; }
      if (seen[item.group]) { seen[item.group].from.push(+item.id); return; }
      seen[item.group] = { pick: +(picks[item.group] || 1), from: [+item.id] };
      out.push(seen[item.group]);
    });
    hidden.value = JSON.stringify(out);
    hidden.form.dispatchEvent(new Event('helper-refresh'));
  }

  function groupSizes() {
    var used = {};
    order.forEach(function (item) { if (item.group) used[item.group] = (used[item.group] || 0) + 1; });
    return used;
  }

  //how many questions each student answers: every ungrouped one, plus each group's pick
  function renderTotal(used) {
    var n = order.filter(function (o) { return !o.group; }).length;
    Object.keys(used).forEach(function (l) { n += Math.min(picks[l] || 1, used[l]); });
    total.textContent = order.length ? 'Each student answers ' + n + ' problem' + (n === 1 ? '' : 's') + '.' : '';
  }

  function renderGroups() {
    var used = groupSizes();
    groupsBox.innerHTML = '';
    Object.keys(used).sort().forEach(function (letter) {
      if (!picks[letter]) picks[letter] = 1;
      if (picks[letter] > used[letter]) picks[letter] = used[letter];
      var row = document.createElement('div');
      row.className = 'order-group';
      var tag = document.createElement('span');
      tag.className = 'badge badge-accent'; tag.textContent = 'Group ' + letter;
      var label = document.createElement('label');
      label.textContent = 'each student gets ';
      var num = document.createElement('input');
      num.type = 'number'; num.min = 1; num.max = used[letter]; num.value = picks[letter];
      num.className = 'order-pick';
      num.setAttribute('aria-label', 'How many problems each student gets from group ' + letter);
      num.addEventListener('input', function () {
        picks[letter] = Math.max(1, Math.min(used[letter], +num.value || 1)); renderTotal(groupSizes()); save();
      });
      var tail = document.createElement('span');
      tail.textContent = used[letter] < 2
        ? ' (put at least one more problem in group ' + letter + ': a group needs 2 or more)'
        : ' of these ' + used[letter] + ', picked at random';
      if (used[letter] < 2) tail.className = 'error';
      row.appendChild(tag); row.appendChild(document.createTextNode(' ')); row.appendChild(label);
      row.appendChild(num); row.appendChild(tail);
      groupsBox.appendChild(row);
    });
    Object.keys(picks).forEach(function (l) { if (!used[l]) delete picks[l]; });
    renderTotal(used);
  }

  function smallButton(text, label, onClick) {
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'btn btn-secondary btn-xs';
    btn.textContent = text; btn.setAttribute('aria-label', label); btn.title = label;
    btn.addEventListener('click', onClick);
    return btn;
  }

  function render() {
    order = order.filter(function (item) { return boxes[item.id]; });
    var fixed = shuffle && !shuffle.checked;
    if (shuffledNote) shuffledNote.hidden = fixed;
    if (fixedNote) fixedNote.hidden = !fixed;
    list.innerHTML = '';
    list.classList.toggle('numbered', !!fixed);
    empty.hidden = order.length > 0;
    order.forEach(function (item, i) {
      tick(item.id, true);
      var title = boxes[item.id][0].dataset.title;
      var li = document.createElement('li');
      li.className = 'order-item' + (item.group ? ' in-group' : '');
      var top = document.createElement('div');
      top.className = 'order-top';
      var name = document.createElement('span');
      name.className = 'order-title';
      name.textContent = (fixed ? (i + 1) + '. ' : '') + title;
      top.appendChild(name);
      //(a bare ✕, as every control on a list item is an icon: the owner, 2026-10-16)
      var rm = smallButton('\u2715', 'Remove \u201c' + title + '\u201d from the quiz', function () {
        order.splice(i, 1);
        if (!order.some(function (o) { return o.id === item.id; })) tick(item.id, false);
        render();
      });
      rm.className = 'btn btn-secondary btn-sm btn-icon order-remove';
      if (window.qgenIcon && window.qgenIcon('lc-x')) rm.innerHTML = window.qgenIcon('lc-x');
      top.appendChild(rm);
      li.appendChild(top);

      var bottom = document.createElement('div');
      bottom.className = 'order-bottom';
      var sel = document.createElement('select');
      sel.setAttribute('aria-label', 'Who gets ' + title);
      [''].concat(LETTERS.slice(0, 6)).forEach(function (l) {
        var o = document.createElement('option');
        o.value = l; o.textContent = l ? 'In group ' + l + ' (random pick)' : 'Every student gets it';
        if (item.group === l) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () { item.group = sel.value; render(); });
      bottom.appendChild(sel);
      if (fixed) {
        [['↑', -1, 'Move up: '], ['↓', 1, 'Move down: ']].forEach(function (b) {
          var btn = smallButton(b[0], b[2] + title, function () {
            var j = i + b[1];
            if (j < 0 || j >= order.length) return;
            order[i] = order[j]; order[j] = item;
            render();
          });
          if ((b[1] < 0 && i === 0) || (b[1] > 0 && i === order.length - 1)) btn.disabled = true;
          bottom.appendChild(btn);
        });
      }
      li.appendChild(bottom);
      list.appendChild(li);
    });
    renderGroups();
    save();
  }

  if (shuffle) shuffle.addEventListener('change', render);

  Object.keys(boxes).forEach(function (id) {
    boxes[id].forEach(function (box) {
      box.addEventListener('change', function () {
        if (this.checked) { if (!order.some(function (o) { return o.id === id; })) order.push({ id: id, group: '' }); }
        else order = order.filter(function (o) { return o.id !== id; });
        tick(id, this.checked);
        render();
      });
    });
  });
  render();
})();


/* The problem picker's folder tabs (static/js/folderfilter.js) say how many of their problems
 * are checked ("2 checked"), as the folder boxes did: kept up to date as boxes are checked and
 * when the tabs are redrawn (a tab chosen). */
(function () {
  var picker = document.getElementById('problem-picker');
  if (!picker) return;
  var data = picker.querySelector('.folder-filter-tree');
  var tree = data ? JSON.parse(data.textContent) : [];
  var byId = {}, inSome = {};
  (function index(nodes) {
    nodes.forEach(function (n) { byId[String(n.id)] = n; n.keys.forEach(function (k) { inSome[k] = 1; }); index(n.children); });
  })(tree);
  function checked() {
    var on = {};
    picker.querySelectorAll('input.pick:checked').forEach(function (b) { on['p:' + b.value] = 1; });
    return on;
  }
  function countFor(id, on) {
    var keys = Object.keys(on);
    if (id === 'all') return keys.length;
    if (id === 'none') return keys.filter(function (k) { return !inSome[k]; }).length;
    var self = id.indexOf('self:') === 0, n = byId[self ? id.slice(5) : id];
    if (!n) return 0;
    if (self && !n.children.length) return 0;  // (a grayed Uncategorized counts nothing, so has nothing checked)
    return keys.filter(function (k) {
      if (n.keys.indexOf(k) === -1) return false;
      return !self || !n.children.some(function (c) { return c.keys.indexOf(k) !== -1; });
    }).length;
  }
  function mark() {
    var on = checked();
    picker.querySelectorAll('.folder-tab').forEach(function (tab) {
      if (!tab.dataset.folder) return;  // (a tab that isn't a folder's)
      var n = countFor(tab.dataset.folder, on), badge = tab.querySelector('.tab-ticked');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'badge badge-accent tab-ticked';
        tab.appendChild(badge);
      }
      badge.hidden = !n || tab.disabled;
      badge.textContent = n + ' checked';
    });
  }
  picker.addEventListener('change', mark);
  //(the one tab over the list is drawn again with each folder picked: its count too)
  picker.addEventListener('qgen-shown', function () { setTimeout(mark, 0); });
  //(the tabs are drawn again when the window crosses the phone width)
  if (window.matchMedia) { var mq = window.matchMedia('(max-width: 640px)'); if (mq.addEventListener) mq.addEventListener('change', function () { setTimeout(mark, 0); }); }
  picker.addEventListener('click', function (e) { if (e.target.closest('.folder-tab')) setTimeout(mark, 0); });
  document.getElementById('all-problems').addEventListener('qgen-ticks-changed', mark);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(mark, 0); });
  else setTimeout(mark, 0);
})();
