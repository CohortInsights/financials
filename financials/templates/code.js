// Load userData JSON injected into dashboard.html
var userData = JSON.parse(document.getElementById("user-data").textContent);
var year_list = userData.years;
var start_year = year_list[0];
let transactionTable = null;

// Invoked upon page load to populate yearDropdown menu from year_list
function populateYearDropdown(yearDropdown) {
    yearDropdown.innerHTML = ''; // Clear existing options
    year_list.forEach(year => {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearDropdown.appendChild(option);
    });
}

// Load transactions for selected year
function loadTransactions(year) {
    const url = `/api/transactions?year=${year}`;
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
                        { data: 'date' },
                        { data: 'source' },
                        { data: 'description' },
                        { data: 'amount', render: $.fn.dataTable.render.number(',', '.', 2, '$') },
                        { data: 'type' }
                    ],
                    scrollY: '70vh',
                    scrollCollapse: true,
                    paging: true,
                    order: [[0, 'desc']]
                });
                console.log("🆕 Table initialized with", data.length, "rows");
            }
        })
        .catch(err => {
            console.error("❌ Error loading transactions:", err);
        });
}

function setStartYear() {
    const yearDropdown = document.getElementById('yearDropdown');
    let value = yearDropdown.value;
    if (value !== start_year) {
        start_year = value;
        console.log("Selected start year:", start_year);
        loadTransactions(start_year);
    }
}

function reloadPage() {
    console.log("🔄 Reload button clicked");
    window.location.href = '/reload';
}

// Set up UI after page load
document.addEventListener('DOMContentLoaded', function() {
    console.log("📦 Initializing dashboard UI");
    const yearDropdown = document.getElementById('yearDropdown');
    populateYearDropdown(yearDropdown);
    yearDropdown.addEventListener('change', setStartYear);

    const reloadButton = document.getElementById('reloadButton');
    reloadButton.addEventListener('click', reloadPage);

    // Initial load
    console.log("🚀 Loading initial year:", start_year);
    loadTransactions(start_year);
});
