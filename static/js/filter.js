/* <input class="filter" data-filter="#table-id">: hide table rows that don't match */
document.querySelectorAll('input.filter[data-filter]').forEach(function (box) {
  var rows = document.querySelectorAll(box.dataset.filter + ' tbody tr');
  box.addEventListener('input', function () {
    var q = box.value.trim().toLowerCase();
    rows.forEach(function (r) { r.hidden = q && r.textContent.toLowerCase().indexOf(q) === -1; });
  });
});
