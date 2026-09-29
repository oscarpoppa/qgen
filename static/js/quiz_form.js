/* Quiz builder: tick problems, order them, and optionally put some in groups
 * ("each student gets 2 of these 6"). Saved as JSON in the hidden vplist:
 *   [4, {"pick": 2, "from": [5, 6, 7]}, 9]
 */
(function () {
  var hidden = document.getElementById('vplist');
  var list = document.getElementById('order');
  var empty = document.getElementById('order-empty');
  var groupsBox = document.getElementById('groups');
  var LETTERS = 'ABCDEFGH'.split('');
  var boxes = {};
  document.querySelectorAll('input.pick').forEach(function (b) { boxes[b.value] = b; });

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
    hidden.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function renderGroups() {
    var used = {};
    order.forEach(function (item) { if (item.group) used[item.group] = (used[item.group] || 0) + 1; });
    groupsBox.innerHTML = '';
    Object.keys(used).sort().forEach(function (letter) {
      if (!picks[letter]) picks[letter] = 1;
      if (picks[letter] > used[letter]) picks[letter] = used[letter];
      var row = document.createElement('div');
      row.className = 'btn-row';
      row.style.margin = '6px 0';
      var label = document.createElement('label');
      label.textContent = 'Group ' + letter + ': each student gets ';
      var num = document.createElement('input');
      num.type = 'number'; num.min = 1; num.max = used[letter]; num.value = picks[letter];
      num.style.width = '70px';
      num.setAttribute('aria-label', 'How many problems each student gets from group ' + letter);
      num.addEventListener('input', function () { picks[letter] = Math.max(1, Math.min(used[letter], +num.value || 1)); save(); });
      var tail = document.createElement('span');
      tail.textContent = ' of these ' + used[letter] + (used[letter] < 2 ? ' (a group needs at least 2)' : '');
      row.appendChild(label); row.appendChild(num); row.appendChild(tail);
      groupsBox.appendChild(row);
    });
    Object.keys(picks).forEach(function (l) { if (!used[l]) delete picks[l]; });
  }

  function render() {
    order = order.filter(function (item) { return boxes[item.id]; });
    list.innerHTML = '';
    empty.hidden = order.length > 0;
    order.forEach(function (item, i) {
      boxes[item.id].checked = true;
      var title = boxes[item.id].dataset.title;
      var li = document.createElement('li');
      var name = document.createElement('span');
      name.style.flex = '1';
      name.textContent = (i + 1) + '. ' + title;
      li.appendChild(name);
      var sel = document.createElement('select');
      sel.setAttribute('aria-label', 'Group for ' + title);
      sel.style.width = 'auto'; sel.style.minHeight = '32px'; sel.style.padding = '2px 6px';
      [''].concat(LETTERS.slice(0, 6)).forEach(function (l) {
        var o = document.createElement('option');
        o.value = l; o.textContent = l ? 'Group ' + l : 'No group';
        if (item.group === l) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () { item.group = sel.value; render(); });
      li.appendChild(sel);
      [['↑', -1, 'Move up'], ['↓', 1, 'Move down'], ['✕', 0, 'Remove']].forEach(function (b) {
        var btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'btn btn-secondary btn-sm';
        btn.textContent = b[0]; btn.setAttribute('aria-label', b[2] + ': ' + title);
        btn.addEventListener('click', function () {
          if (b[1] === 0) {
            order.splice(i, 1);
            if (!order.some(function (o) { return o.id === item.id; })) boxes[item.id].checked = false;
          } else {
            var j = i + b[1];
            if (j < 0 || j >= order.length) return;
            order[i] = order[j]; order[j] = item;
          }
          render();
        });
        li.appendChild(btn);
      });
      list.appendChild(li);
    });
    renderGroups();
    save();
  }

  Object.keys(boxes).forEach(function (id) {
    boxes[id].addEventListener('change', function () {
      if (this.checked) { if (!order.some(function (o) { return o.id === id; })) order.push({ id: id, group: '' }); }
      else order = order.filter(function (o) { return o.id !== id; });
      render();
    });
  });
  render();
})();
