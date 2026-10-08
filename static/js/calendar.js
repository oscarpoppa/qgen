/* Calendar control for every date field on the site.
 *
 * Any <input type="datetime-local"> or <input type="date"> is enhanced: a
 * calendar button opens a month view (with time lists for date-and-time
 * fields), and a friendly reading of the value appears below the field.
 * The input keeps its usual value format (YYYY-MM-DDTHH:MM or YYYY-MM-DD),
 * so forms and the server work exactly as before, and people can still type.
 *
 * Keyboard: arrows move by day/week, PageUp/PageDown by month, Enter picks,
 * Escape closes.
 */
(function () {
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
  var DAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
  var open = null;  // the picker currently shown

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function parse(value, withTime) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(value || '');
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3], withTime && m[4] ? +m[4] : 0, withTime && m[5] ? +m[5] : 0);
  }

  function format(d, withTime) {
    var s = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    return withTime ? s + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()) : s;
  }

  function friendly(d, withTime) {
    var s = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    return withTime ? s + ' at ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : s;
  }

  function sameDay(a, b) {
    return a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function enhance(input) {
    if (input.dataset.calendar === 'on') return;
    input.dataset.calendar = 'on';
    var withTime = input.type === 'datetime-local';
    var label = (input.labels && input.labels[0] ? input.labels[0].textContent.trim() : 'date');

    //the row: the field plus a calendar button; a friendly reading underneath
    var row = el('div', 'cal-row');
    input.parentNode.insertBefore(row, input);
    row.appendChild(input);
    var btn = el('button', 'btn btn-secondary cal-btn');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Choose ' + label + ' from a calendar');
    btn.title = 'Choose ' + label + ' from a calendar';
    btn.setAttribute('aria-haspopup', 'dialog');
    btn.innerHTML = '<span aria-hidden="true">📅</span>';
    row.appendChild(btn);
    var reading = el('div', 'cal-reading small muted');
    reading.setAttribute('aria-live', 'polite');
    row.parentNode.insertBefore(reading, row.nextSibling);

    function showReading() {
      var d = parse(input.value, withTime);
      reading.textContent = d ? friendly(d, withTime) : '';
    }
    input.addEventListener('input', showReading);
    input.addEventListener('change', showReading);
    showReading();

    btn.addEventListener('click', function () {
      if (open && open.input === input) { close(); return; }
      openPicker(input, btn, withTime, label, showReading);
    });
  }

  function close() {
    if (!open) return;
    open.box.remove();
    open.button.setAttribute('aria-expanded', 'false');
    open = null;
  }

  function openPicker(input, button, withTime, label, onChange) {
    close();
    var chosen = parse(input.value, withTime);
    var cursor = chosen ? new Date(chosen) : new Date();
    cursor.setHours(0, 0, 0, 0);
    var hour = chosen ? chosen.getHours() : 9, minute = chosen ? chosen.getMinutes() : 0;

    var box = el('div', 'cal-pop card');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-label', 'Choose ' + label);

    var head = el('div', 'cal-head');
    var prev = el('button', 'btn btn-secondary btn-sm', '‹');
    prev.type = 'button'; prev.setAttribute('aria-label', 'Previous month'); prev.title = 'Show the month before';
    var title = el('div', 'cal-title');
    title.setAttribute('aria-live', 'polite');
    var next = el('button', 'btn btn-secondary btn-sm', '›');
    next.type = 'button'; next.setAttribute('aria-label', 'Next month'); next.title = 'Show the month after';
    head.appendChild(prev); head.appendChild(title); head.appendChild(next);
    box.appendChild(head);

    var grid = el('div', 'cal-grid');
    grid.setAttribute('role', 'grid');
    box.appendChild(grid);

    var hourSel, minSel;
    if (withTime) {
      var time = el('div', 'cal-time');
      var tl = el('span', 'small muted', 'Time');
      hourSel = el('select'); hourSel.setAttribute('aria-label', 'Hour');
      for (var h = 0; h < 24; h++) {
        var o = el('option', '', ((h % 12) || 12) + (h < 12 ? ' AM' : ' PM'));
        o.value = h; hourSel.appendChild(o);
      }
      minSel = el('select'); minSel.setAttribute('aria-label', 'Minutes');
      var mins = [];
      for (var m = 0; m < 60; m += 5) mins.push(m);
      if (mins.indexOf(minute) === -1) { mins.push(minute); mins.sort(function (a, b) { return a - b; }); }
      mins.forEach(function (m) { var o = el('option', '', ':' + pad(m)); o.value = m; minSel.appendChild(o); });
      hourSel.value = hour; minSel.value = minute;
      time.appendChild(tl); time.appendChild(hourSel); time.appendChild(minSel);
      box.appendChild(time);
      [hourSel, minSel].forEach(function (s) {
        s.addEventListener('change', function () {
          hour = +hourSel.value; minute = +minSel.value;
          if (chosen) { set(chosen); }
        });
      });
    }

    var foot = el('div', 'cal-foot btn-row');
    var today = el('button', 'btn btn-secondary btn-sm', 'Today');
    var clear = el('button', 'btn btn-secondary btn-sm', 'Clear');
    var done = el('button', 'btn btn-sm', 'Done');
    today.title = 'Pick today\'s date'; clear.title = 'Empty this date box'; done.title = 'Close the calendar';
    [today, clear, done].forEach(function (b) { b.type = 'button'; foot.appendChild(b); });
    box.appendChild(foot);

    function set(day) {
      chosen = new Date(day.getFullYear(), day.getMonth(), day.getDate(), withTime ? hour : 0, withTime ? minute : 0);
      input.value = format(chosen, withTime);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      onChange();
    }

    function draw(focusIt) {
      title.textContent = MONTHS[cursor.getMonth()] + ' ' + cursor.getFullYear();
      grid.innerHTML = '';
      DAYS.forEach(function (d) { var c = el('div', 'cal-dow small muted', d); c.setAttribute('role', 'columnheader'); grid.appendChild(c); });
      var first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
      var start = new Date(first); start.setDate(1 - first.getDay());
      var now = new Date(), focusBtn = null;
      for (var i = 0; i < 42; i++) {
        var day = new Date(start); day.setDate(start.getDate() + i);
        var b = el('button', 'cal-day', String(day.getDate()));
        b.type = 'button';
        b.setAttribute('role', 'gridcell');
        b.setAttribute('aria-label', friendly(day, false));
        b.title = 'Pick ' + friendly(day, false);
        if (day.getMonth() !== cursor.getMonth()) b.classList.add('cal-other');
        if (sameDay(day, now)) { b.classList.add('cal-today'); b.setAttribute('aria-current', 'date'); }
        if (sameDay(day, chosen)) { b.classList.add('cal-chosen'); b.setAttribute('aria-selected', 'true'); }
        var isCursor = sameDay(day, cursor);
        b.tabIndex = isCursor ? 0 : -1;
        if (isCursor) focusBtn = b;
        (function (d) {
          b.addEventListener('click', function () {
            cursor = new Date(d); set(d);
            if (withTime) { draw(true); return; }
            //a date-only field is done once a day is picked
            close(); button.focus();
          });
        })(day);
        grid.appendChild(b);
      }
      if (focusIt && focusBtn) focusBtn.focus();
    }

    function moveMonths(n) { cursor.setMonth(cursor.getMonth() + n, 1); draw(true); }

    prev.addEventListener('click', function () { moveMonths(-1); });
    next.addEventListener('click', function () { moveMonths(1); });
    today.addEventListener('click', function () { var t = new Date(); t.setHours(0, 0, 0, 0); cursor = t; set(t); draw(true); });
    clear.addEventListener('click', function () {
      chosen = null; input.value = '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      onChange(); draw(true);
    });
    done.addEventListener('click', function () { close(); button.focus(); });

    grid.addEventListener('keydown', function (e) {
      var step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
      if (step) { cursor.setDate(cursor.getDate() + step); draw(true); e.preventDefault(); }
      else if (e.key === 'PageUp') { moveMonths(-1); e.preventDefault(); }
      else if (e.key === 'PageDown') { moveMonths(1); e.preventDefault(); }
      else if (e.key === 'Home') { cursor.setDate(cursor.getDate() - cursor.getDay()); draw(true); e.preventDefault(); }
      else if (e.key === 'End') { cursor.setDate(cursor.getDate() + 6 - cursor.getDay()); draw(true); e.preventDefault(); }
    });
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { close(); button.focus(); e.preventDefault(); }
    });

    //place it under the field, kept on screen
    button.parentNode.appendChild(box);
    button.setAttribute('aria-expanded', 'true');
    open = { box: box, input: input, button: button };
    draw(true);
  }

  //clicking anywhere else closes it
  document.addEventListener('mousedown', function (e) {
    if (open && !open.box.contains(e.target) && !open.button.contains(e.target)) close();
  });

  function init() {
    document.querySelectorAll('input[type=datetime-local], input[type=date]').forEach(enhance);
  }
  window.qgenCalendar = enhance;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
