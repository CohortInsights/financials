// templates/assignments.js

// --- Global reference to the assignments DataTable ---
var assignmentsTable = null;

// --- Duration selection state ---
let currentDuration = "year";

// --- Reload Assignments table when rules change ---
window.addEventListener("ruleSaved", () => {
    if (assignmentsTable) {
        console.log("🔔 ruleSaved → reloading assignments NOW");
        loadAssignments();
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
        })
        .catch(err => {
            console.error("❌ Error loading assignments:", err);
        });
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
                render: () => ""   // Blank for now
            }
        ],

        // NEW: Disable all client-side sorting and respect backend order fully
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

        // Column indices:
        // 0 = Period (no filter)
        // 1 = Assignment (filter)
        // 2 = Count (no filter)
        // 3 = Amount (no filter)
        // 4 = Level (filter)
        // 5 = Action (none)

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

        // --- Assignment filter
        if (idx === 1) {
            $(input).on('keyup change clear', debounce(function () {
                let raw = this.value.trim().toLowerCase();
                if (raw === "") {
                    column.search("", true, false).draw();
                    return;
                }

                let tokens = raw.split(',')
                    .map(s => s.trim())
                    .filter(s => s.length > 0);

                let pattern = tokens.map(t => `(?=.*${t})`).join("|");
                column.search(pattern, true, false).draw();
            }, 150));
        }

        // --- Level filter
        if (idx === 4) {
            $(input).on('keyup change clear', debounce(function () {
                let raw = this.value.trim();
                if (raw === "") {
                    column.search("", true, false).draw();
                    return;
                }

                let nums = raw.split(',')
                    .map(s => s.trim())
                    .filter(s => /^\d+$/.test(s));

                if (nums.length === 0) {
                    column.search("", true, false).draw();
                    return;
                }

                let pattern = nums.map(n => `^${n}$`).join("|");
                column.search(pattern, true, false).draw();
            }, 150));
        }
    });
}

// --- Year selector event listeners ---
function attachAssignmentYearListeners() {
    const checkboxes = document.querySelectorAll('#assignmentsYearSelector input[type=checkbox]');
    checkboxes.forEach(cb => cb.addEventListener('change', loadAssignments));
}

// --- Duration segmented-button listeners ---
function attachDurationListeners() {
    const buttons = document.querySelectorAll('#durationSelector button');

    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            const newValue = btn.getAttribute("data-duration");
            if (!newValue) return;

            currentDuration = newValue;

            // Update button visual state
            buttons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            console.log(`⏳ Duration changed → ${currentDuration}`);
            loadAssignments();
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

            // IMPORTANT: listeners must come AFTER rendering
            attachAssignmentYearListeners();
            attachDurationListeners();

            loadAssignments();
        })
        .catch(err => {
            console.error("❌ Failed to load assignment years:", err);
        });
}