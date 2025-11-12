// --- Global variable for DataTable reference ---
var transactionTable = null;

// --- Collect selected years from the checkbox group ---
function getSelectedYears() {
    return Array.from(document.querySelectorAll('#yearSelector input[type=checkbox]:checked'))
                .map(cb => cb.value);
}

// --- Fetch and display transactions for selected years ---
function loadTransactions() {
    const years = getSelectedYears();
    const param = years.join(',');
    const url = `/api/transactions?years=${param}`;
    console.log("📡 Fetching:", url);

    fetch(url)
        .then(res => res.json())
        .then(data => {
            console.log(`✅ Loaded ${data.length} transactions`);

            if (transactionTable) {
                // 🆕 Preserve the current page before clearing
                const currentPage = transactionTable.page();

                transactionTable.clear().rows.add(data).draw(false);

                // 🆕 Restore the previous page
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
        initComplete: addColumnFilters
    });

    // Handle manual assignment button clicks
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

        $(input).on('keyup change clear', function () {
            if (column.search() !== this.value) {
                column.search(this.value, true, false).draw();
            }
        });
    });
}

// --- When user clicks "Assign" on a row ---
function onAssignClick() {
    const id = $(this).data('id');
    const newAssign = prompt("Enter new assignment (e.g. Expense.Food.Restaurant):");
    if (!newAssign) return;

    fetch('/assign_transaction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_id: id, assignment: newAssign })
    })
    .then(res => res.json())
    .then(resp => {
        if (resp.success) {
            console.log(`✅ Transaction ${id} updated to ${newAssign}`);
            loadTransactions(); // reload table
        } else {
            alert("⚠️ Update failed: " + (resp.message || 'Unknown error'));
        }
    })
    .catch(err => {
        console.error("❌ Error assigning transaction:", err);
    });
}

// --- Watch year checkbox changes to reload table ---
function attachYearCheckboxListeners() {
    const checkboxes = document.querySelectorAll('#yearSelector input[type=checkbox]');
    checkboxes.forEach(cb => cb.addEventListener('change', loadTransactions));
}

// --- 🔁 Detect when Transactions tab becomes active and refresh if rules changed ---
function attachTabRefreshListener() {
  // Works for both <a> and <button> tab toggles
  const allTabToggles = document.querySelectorAll('[data-bs-toggle="tab"]');

  allTabToggles.forEach(tab => {
    tab.addEventListener('shown.bs.tab', event => {
      const targetId = event.target.getAttribute('data-bs-target');
      if (targetId === '#tab-transactions' && localStorage.getItem('transactionsNeedRefresh') === 'true') {
        console.log('🔁 Reloading transactions after rule changes...');
        loadTransactions();
        localStorage.removeItem('transactionsNeedRefresh');
      }
    });
  });

  // Handle the edge case where Transactions is already active on load
  const activePane = document.querySelector('#tab-transactions.active');
  if (activePane && localStorage.getItem('transactionsNeedRefresh') === 'true') {
    console.log('🔁 Reloading transactions after rule changes (active on load)...');
    loadTransactions();
    localStorage.removeItem('transactionsNeedRefresh');
  }
}

// --- Module entry point called from code.js ---
function initTransactions() {
    console.log("🚀 Initializing transaction dashboard");
    attachYearCheckboxListeners();
    attachTabRefreshListener();   // 🔁 new listener added
    loadTransactions();
}
