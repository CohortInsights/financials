// Parse user_data JSON injected into dashboard.html
var userData = JSON.parse(document.getElementById("user-data").textContent);
let transactionTable = null;

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
    console.log("Fetching:", url);

    fetch(url)
        .then(res => {
            console.log("Response status:", res.status);
            return res.json();
        })
        .then(data => {
            console.log("✅ API returned", data.length, "rows");
            if (data.length > 0) {
                console.log("🔍 First row sample:", data[0]);
            } else {
                console.warn("⚠️ No data returned from API");
            }

            if (transactionTable) {
                transactionTable.clear().rows.add(data).draw();
                console.log("♻️ Table reloaded with new data");
            } else {
                transactionTable = $('#transactions').DataTable({
                    data: data,
                    columns: [
                        { data: 'date', title: 'Date' },
                        { data: 'source', title: 'Source' },
                        { data: 'description', title: 'Description' },
                        { data: 'amount', title: 'Amount', render: $.fn.dataTable.render.number(',', '.', 2, '$') },
                        { data: 'type', title: 'Type' }
                    ],
                    order: [[0, 'desc']],
                    scrollY: '70vh',
                    scrollCollapse: true,
                    paging: true,
                    initComplete: function () {
                        const api = this.api();

                        // Build text boxes inside footer cells
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
                });

                console.log("🆕 Table initialized with filters and", data.length, "rows");
            }
        })
        .catch(err => {
            console.error("❌ Error loading transactions:", err);
        });
}

// --- Reload data when checkboxes change ---
function attachYearCheckboxListeners() {
    const checkboxes = document.querySelectorAll('#yearSelector input[type=checkbox]');
    checkboxes.forEach(cb => cb.addEventListener('change', () => {
        console.log("Year selection changed");
        loadTransactions();
    }));
}

// --- Reload button handler ---
function reloadPage() {
    console.log("🔄 Reload button clicked");
    window.location.href = '/reload';
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', function() {
    console.log("📦 Initializing dashboard UI");
    attachYearCheckboxListeners();

    const reloadButton = document.getElementById('reloadButton');
    if (reloadButton) reloadButton.addEventListener('click', reloadPage);

    console.log("🚀 Initial load for default year selection");
    loadTransactions();
});
