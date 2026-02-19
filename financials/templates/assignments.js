// templates/assignments.js

// --- Global reference to the assignments DataTable ---
var assignmentsTable = null;

// --- Duration selection state ---
let currentDuration = "year";

// --- View selection state ---
let currentView = "table";

// --- Reload Assignments table when rules change ---
window.addEventListener("ruleSaved", () => {
    if (assignmentsTable) {
        console.log("🔔 ruleSaved → reloading assignments NOW");
        loadAssignments();
        if (currentView !== "table") renderAssignmentsChart();
    } else {
        console.log("🔔 ruleSaved → assignments not initialized yet");
    }
});

// --- Collect selected years for the Assignments tab ---
function getSelectedAssignmentYears() {
    return Array.from(
        document.querySelectorAll('#assignmentsYearSelector input[type=checkbox]:checked')
    ).map(cb => cb.value);
}

// --- Read footer filter values (raw, backend-safe) ---
function getAssignmentsFooterFilters() {
    if (!assignmentsTable) {
        return { asn: "", level: "" };
    }

    const asnInput = assignmentsTable
        .column(1)
        .footer()
        ?.querySelector("input");

    const levelInput = assignmentsTable
        .column(4)
        .footer()
        ?.querySelector("input");

    return {
        asn: asnInput ? asnInput.value.trim() : "",
        level: levelInput ? levelInput.value.trim() : ""
    };
}

// --- Load assignments data from API ---
function loadAssignments() {
    const years = getSelectedAssignmentYears();
    const param = years.join(',');

    const url =
        `/api/assigned_transactions?years=${param}&duration=${currentDuration}&expand=1`;

    console.log("📘 loadAssignments() →", url);

    fetch(url, { cache: "no-store" })
        .then(res => res.json())
        .then(data => {
            console.log(`📘 Loaded ${data.length} assignment rows`);

            if (assignmentsTable) {
                const page = assignmentsTable.page();
                assignmentsTable.clear().rows.add(data).draw(false);
                assignmentsTable.page(page).draw(false);
            } else {
                buildAssignmentsTable(data);
            }

            if (currentView !== "table") renderAssignmentsChart();
        })
        .catch(err => {
            console.error("❌ Error loading assignments:", err);
        });
}

// --- Render chart image ---
function renderAssignmentsChart() {
    const years = getSelectedAssignmentYears().join(',');
    if (!years) return;

    const { asn, level } = getAssignmentsFooterFilters();

    const params = new URLSearchParams({
        chart: currentView,
        years: years,
        duration: currentDuration,
        asn: asn || "",
        level: level || ""
    });

    const img = document.getElementById("assignmentsChartImage");
    img.src = `/api/charts/render?${params.toString()}`;
}

// --- Build the Assignments DataTable ---
function buildAssignmentsTable(data) {
    assignmentsTable = $('#assignments').DataTable({
        data: data,
        columns: [
            { data: 'period',   title: 'Period' },
            { data: 'assignment', title: 'Assignment', defaultContent: '' },
            { data: 'count',    title: 'Count' },
            {
                data: 'amount',
                title: 'Amount',
                render: $.fn.dataTable.render.number(',', '.', 2, '$')
            },
            { data: 'level',    title: 'Level' },
            {
                data: null,
                title: 'Action',
                render: () => ""
            }
        ],
        order: [],
        ordering: false,
        scrollY: '70vh',
        scrollCollapse: true,
        paging: true,
        initComplete: addAssignmentFilters
    });
}

// --- Add ONLY the Assignment + Level filters ---
function addAssignmentFilters() {
    const api = this.api();

    api.columns().every(function () {
        const column = this;
        const idx = column.index();

        if (!(idx === 1 || idx === 4)) {
            $(column.footer()).empty();
            return;
        }

        const input = document.createElement("input");
        input.placeholder = idx === 1 ? "Filter Assignment" : "Filter Level";
        input.style.width = "90%";
        input.style.fontSize = "12px";
        input.style.padding = "2px 4px";

        $(column.footer()).empty().append(input);

        $(input).on('keyup change clear', debounce(function () {
            column.search(this.value).draw();
            if (currentView !== "table") renderAssignmentsChart();
        }, 150));
    });
}

// --- Year selector event listeners ---
function attachAssignmentYearListeners() {
    const checkboxes = document.querySelectorAll('#assignmentsYearSelector input[type=checkbox]');
    checkboxes.forEach(cb => cb.addEventListener('change', () => {
        loadAssignments();
    }));
}

// --- Duration segmented-button listeners ---
function attachDurationListeners() {
    const buttons = document.querySelectorAll('#durationSelector button');

    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            const newValue = btn.getAttribute("data-duration");
            if (!newValue) return;

            currentDuration = newValue;

            buttons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            console.log(`⏳ Duration changed → ${currentDuration}`);
            loadAssignments();
        });
    });
}

// --- View selector listeners ---
function attachViewListeners() {
    const buttons = document.querySelectorAll('#assignmentsViewSelector button');

    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            const newView = btn.getAttribute("data-view");
            if (!newView) return;

            currentView = newView;

            buttons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            const tableWrapper = document.getElementById("assignments_wrapper");
            const chartContainer = document.getElementById("assignmentsChartContainer");

            if (currentView === "table") {
                if (tableWrapper) tableWrapper.style.display = "";
                chartContainer.style.display = "none";
            } else {
                if (tableWrapper) tableWrapper.style.display = "none";
                chartContainer.style.display = "";
                renderAssignmentsChart();
            }
        });
    });
}

function renderAssignmentsYearCheckboxes(years) {
    const container = document.getElementById("assignmentsYearSelector");
    if (!container) return;

    container.innerHTML = "";
    if (!Array.isArray(years) || years.length === 0) return;

    const newest = Math.max(...years);

    years.forEach(year => {
        const label = document.createElement("label");
        const cb = document.createElement("input");

        cb.type = "checkbox";
        cb.value = String(year);
        cb.checked = (year === newest);

        label.appendChild(cb);
        label.append(` ${year}`);
        container.appendChild(label);
    });
}

function initAssignments() {
    console.log("📘 Initializing Assignments tab");

    fetch("/api/transaction_years")
        .then(res => res.json())
        .then(data => {
            const years = data.years || [];

            renderAssignmentsYearCheckboxes(years);

            attachAssignmentYearListeners();
            attachDurationListeners();
            attachViewListeners();

            loadAssignments();
        })
        .catch(err => {
            console.error("❌ Failed to load assignment years:", err);
        });
}
