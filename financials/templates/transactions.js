// --- Global variable for DataTable reference ---
var transactionTable = null;

// --- GLOBAL listener for ruleSaved events (fires even if tab never switches) ---
window.addEventListener("ruleSaved", () => {
  console.log("🔔 ruleSaved received globally — reloading transactions NOW");
  if (typeof loadTransactions === "function") {
    loadTransactions();
  }
});

// --- Debounce utility (150ms) ---
function debounce(fn, delay = 150) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

// --- Collect selected years from the checkbox group ---
function getSelectedYears() {
  const from = document.getElementById("yearSelector_from")?.value;
  const to = document.getElementById("yearSelector_to")?.value;

  if (!from || !to) return [];

  const start = parseInt(from);
  const end = parseInt(to);

  if (start > end) return [];

  const years = [];
  for (let y = start; y <= end; y++) {
    years.push(y);
  }

  return years;
}

// --- Fetch and display transactions for selected years ---
function loadTransactions() {
  const years = getSelectedYears();
  const param = years.join(',');

  const ytdChecked = document.getElementById("transactionsYtdCheckbox")?.checked;
  let url = `/api/transactions?years=${param}`;
  if (ytdChecked) {
    url += "&ytd=true";
  }
  console.log("🔁 loadTransactions() called; URL =", url);

  fetch(url, { cache: "no-store" })
    .then(res => res.json())
    .then(data => {
      console.log(`✅ Loaded ${data.length} transactions`);

      if (transactionTable) {
        const currentPage = transactionTable.page();
        transactionTable.clear().rows.add(data).draw(false);
        transactionTable.page(currentPage).draw(false);
        console.log("♻️ Table reloaded with new data (page preserved)");
      } else {
        buildTransactionTable(data);
      }
    })
    .catch(err => {
      console.error("❌ Error loading transactions:", err);
    });
}

// --- Initialize the DataTable for the first time ---
function buildTransactionTable(data) {
  transactionTable = $('#transactions').DataTable({
    data: data,
    columns: [
      { data: 'date', title: 'Date' },
      { data: 'source', title: 'Source' },
      { data: 'description', title: 'Description' },
      { data: 'amount', title: 'Amount', render: $.fn.dataTable.render.number(',', '.', 2, '$') },
      { data: 'type', title: 'Type' },
      { data: 'assignment', title: 'Assignment', defaultContent: 'Unspecified' },
      { data: 'google_primary_type', title: 'Primary Type', defaultContent: '' },
      {
        data: null,
        title: 'Action',
        render: function (data, type, row) {
          return `<button class="assign-btn" data-id="${row.id}">Assign</button>`;
        }
      }
    ],
    order: [[0, 'desc']],
    scrollY: '70vh',
    scrollCollapse: true,
    paging: true,
    initComplete: addColumnFilters,

    // -----------------------------------------------------------
    // ✅ Net Row Logic (fixed, no redraw recursion)
    // -----------------------------------------------------------
    drawCallback: function () {
      const api = this.api();

      // Use the cloned header (visible frozen header), not the original <thead>
      const header = $("#transactions_wrapper .dataTables_scrollHead thead");

      // Remove existing Net row
      header.find("#net-row").remove();

      const amountIdx = 3;

      // Sum filtered amounts
      const sum = api
        .column(amountIdx, { search: "applied" })
        .data()
        .reduce((acc, v) => acc + parseFloat(v || 0), 0);

      const formatted = sum.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      });

      // We want "Net" to appear under the Description column (index 2)
      const descriptionIdx = 2;

      // Build Net row cells
      const colCount = api.columns().count();
      let cells = "";

      for (let i = 0; i < colCount; i++) {
          if (i === descriptionIdx) cells += "<td>Net</td>";
          else if (i === amountIdx) cells += `<td>$${formatted}</td>`;
          else cells += "<td></td>";
      }

      const netRow = `<tr id="net-row">${cells}</tr>`;

      // Insert just under the main header row (in the cloned header)
      header.find("tr:first").after(netRow);
    }
    // -----------------------------------------------------------
  });

  $('#transactions tbody').on('click', 'button.assign-btn', onAssignClick);
}

// --- Add footer text filters for each column ---
function addColumnFilters() {
  const api = this.api();

  api.columns().every(function () {
    const column = this;
    const headerText = $(column.header()).text();

    const input = document.createElement("input");
    input.placeholder = "Filter " + headerText;
    input.style.width = "90%";
    input.style.fontSize = "12px";
    input.style.padding = "2px 4px";

    $(column.footer()).empty().append(input);

    $(input).on(
      'keyup change clear',
      debounce(function () {
        let raw = this.value.trim();

        if (raw === "") {
          column.search("", true, false).draw();
          return;
        }

        let parts = raw.split(",")
          .map(s => s.trim())
          .filter(s => s !== "");

        let include = parts.filter(p => !p.startsWith("!"));
        let exclude = parts.filter(p => p.startsWith("!"))
          .map(p => p.substring(1));

        let pattern = "";

        exclude.forEach(ex => {
          pattern += `(?!.*${ex})`;
        });

        if (include.length > 0) {
          pattern += `(${include.join("|")})`;
        } else if (exclude.length > 0) {
          pattern += `.*`;
        }

        column.search(pattern, true, false).draw();
      }, 150)
    );
  });
}

// --- When user clicks "Assign" on a row (now creates a rule instead) ---
function onAssignClick() {
  const rowData = transactionTable.row($(this).closest('tr')).data();
  if (!rowData) return;

  const form = document.getElementById("addRuleForm");
  const modalEl = document.getElementById("addRuleModal");
  const modal = new bootstrap.Modal(modalEl);

  form.reset();
  form.priority.value = 3;
  form.source.value = "";
  form.description.value = rowData.description;
  form.min_amount.value = "";
  form.max_amount.value = "";
  form.assignment.value = "";

  window.editingRuleId = null;
  document.getElementById("addRuleLabel").textContent = "Add Rule From Transaction";

  modal.show();
}

// --- Watch year checkbox changes to reload table ---
function attachYearSelectorListeners() {
  const from = document.getElementById("yearSelector_from");
  const to = document.getElementById("yearSelector_to");

  if (from) from.addEventListener("change", loadTransactions);
  if (to) to.addEventListener("change", loadTransactions);
}

function renderYearSelectorRange(containerId, years) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = "";
  if (!Array.isArray(years) || years.length === 0) return;

  years.sort((a, b) => a - b);

  const maxYear = years[years.length - 1];

  const fromSelect = document.createElement("select");
  const toSelect = document.createElement("select");

  fromSelect.id = containerId + "_from";
  toSelect.id = containerId + "_to";

  years.forEach(year => {
    fromSelect.add(new Option(year, year));
    toSelect.add(new Option(year, year));
  });

  // Default: most recent year only
  fromSelect.value = maxYear;
  toSelect.value = maxYear;

  container.appendChild(document.createTextNode("From "));
  container.appendChild(fromSelect);
  container.appendChild(document.createTextNode(" To "));
  container.appendChild(toSelect);
}

// --- Fix DataTables column sizing when Transactions tab becomes visible ---
document.addEventListener('DOMContentLoaded', function () {
    const tabBtn = document.getElementById('transactions-tab');

    if (tabBtn) {
      tabBtn.addEventListener('shown.bs.tab', function () {
        if ($.fn.DataTable.isDataTable('#transactions')) {
          $('#transactions').DataTable().columns.adjust();
        }
      });
    }

    // --- YTD checkbox binding ---
    const ytd = document.getElementById("transactionsYtdCheckbox");
    if (ytd) {
      ytd.addEventListener("change", loadTransactions);
    }
});

function initTransactions() {
  console.log("🚀 Initializing transaction dashboard");

  fetch("/api/transaction_years")
    .then(res => res.json())
    .then(data => {
      const years = data.years || [];

      renderYearSelectorRange("yearSelector", years);

      // IMPORTANT: listeners must be attached AFTER rendering
      attachYearSelectorListeners();

      // Initial load
      loadTransactions();
    })
    .catch(err => {
      console.error("❌ Failed to load transaction years:", err);
    });
}
