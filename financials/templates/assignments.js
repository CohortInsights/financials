// templates/assignments.js

// --- Global reference to the assignments DataTable ---
var assignmentsTable = null;

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
    const url = `/api/assigned_transactions?years=${param}&expand=1`;

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
            { data: 'amount',   title: 'Amount', render: $.fn.dataTable.render.number(',', '.', 2, '$') },
            { data: 'level',    title: 'Level' },
            {
                data: null,
                title: 'Action',
                render: () => ""   // Blank for now
            }
        ],
        order: [[0, 'desc']],
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
        // 5 = Action (no filter)

        // Only add filters to Assignment (1) and Level (4)
        if (!(idx === 1 || idx === 4)) {
            $(column.footer()).empty(); // ensure footer cell is blank
            return;
        }

        // Create input
        const input = document.createElement("input");
        input.placeholder = idx === 1 ? "Filter Assignment" : "Filter Level";
        input.style.width = "90%";
        input.style.fontSize = "12px";
        input.style.padding = "2px 4px";

        $(column.footer()).empty().append(input);

        // --- Assignment filter (substring OR match: "a,b")
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

                // Build OR pattern for substring match
                let pattern = tokens.map(t => `(?=.*${t})`).join("|");
                column.search(pattern, true, false).draw();

            }, 150));
        }

        // --- Level filter (numeric OR match: "1,3")
        if (idx === 4) {
            $(input).on('keyup change clear', debounce(function () {
                let raw = this.value.trim();

                if (raw === "") {
                    column.search("", true, false).draw();
                    return;
                }

                // Split into integers
                let nums = raw.split(',')
                              .map(s => s.trim())
                              .filter(s => /^\d+$/.test(s)); // keep only numeric tokens

                if (nums.length === 0) {
                    column.search("", true, false).draw();
                    return;
                }

                // Build OR pattern for exact matches (e.g., (^2$|^3$))
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

// --- Primary entry point, called when tab is activated ---
function initAssignments() {
    console.log("📘 Initializing Assignments tab");

    attachAssignmentYearListeners();
    loadAssignments();
}
