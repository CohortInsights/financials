let rulesTable = null;
let editingRuleId = null;  // tracks whether we're editing an existing rule

document.addEventListener("DOMContentLoaded", () => {
  const tab = document.getElementById("tab-rules");
  if (!tab) return;

  // Initialize table when tab becomes active
  const observer = new MutationObserver(() => {
    if (tab.classList.contains("active") && !rulesTable) loadRulesTable();
  });
  observer.observe(tab, { attributes: true, attributeFilter: ["class"] });

  // Wire buttons
  document.getElementById("addRuleBtn")?.addEventListener("click", openAddRuleModal);
  document.getElementById("saveRuleBtn")?.addEventListener("click", saveRule);
});


// === Load all rules and render DataTable ===
function loadRulesTable() {
  fetch("/api/rules")
    .then(res => res.json())
    .then(data => {
      if ($.fn.DataTable.isDataTable("#rulesTable")) {
        const table = $("#rulesTable").DataTable();
        table.clear();
        table.rows.add(data);
        table.draw();
        return;
      }

      // FIRST-TIME INITIALIZATION
      rulesTable = $("#rulesTable").DataTable({
        data,
        columns: [
          { data: "assignment" },
          { data: "priority" },
          { data: "source" },
          { data: "description" },
          { data: "min_amount", defaultContent: "" },
          { data: "max_amount", defaultContent: "" },
          {
            data: null,
            render: () => `
              <button class="btn btn-outline-primary btn-sm me-1 edit-btn">Edit</button>
              <button class="btn btn-outline-danger btn-sm delete-btn">Delete</button>
            `,
            orderable: false
          }
        ],
        order: [[1, "asc"]],

        // PATCH 2: Mirror Transactions DataTable behavior
        scrollY: "55vh",
        scrollCollapse: true,
        paging: true,
        info: true,
        orderCellsTop: true,
        fixedHeader: false
      });

      // PATCH 3: Hook up footer-search filters
      rulesTable.columns().every(function () {
        let column = this;
        $('input', column.footer()).on('keyup change clear', function () {
          if (column.search() !== this.value) {
            column.search(this.value).draw();
          }
        });
      });

      // Wire up action buttons
      $("#rulesTable tbody").on("click", ".edit-btn", onEditRule);
      $("#rulesTable tbody").on("click", ".delete-btn", onDeleteRule);
    })
    .catch(err => console.error("❌ Error loading rules:", err));
}



// === Open modal for adding new rule ===
function openAddRuleModal() {
  editingRuleId = null;
  document.getElementById("addRuleForm").reset();
  document.getElementById("addRuleLabel").textContent = "Add New Rule";
  const modal = new bootstrap.Modal(document.getElementById("addRuleModal"));
  modal.show();
}



// === Open modal pre-filled for editing existing rule ===
function onEditRule() {
  const rowData = rulesTable.row($(this).closest("tr")).data();
  editingRuleId = rowData._id;

  // Populate form fields
  const form = document.getElementById("addRuleForm");
  form.priority.value = rowData.priority;
  form.source.value = rowData.source;
  form.description.value = rowData.description;
  form.min_amount.value = rowData.min_amount;
  form.max_amount.value = rowData.max_amount;
  form.assignment.value = rowData.assignment;

  document.getElementById("addRuleLabel").textContent = "Edit Rule";
  const modal = new bootstrap.Modal(document.getElementById("addRuleModal"));
  modal.show();
}



// === Save rule (create or update) ===
function saveRule() {
  const form = document.getElementById("addRuleForm");
  const data = Object.fromEntries(new FormData(form).entries());
  data.priority = parseInt(data.priority);
  data.min_amount = data.min_amount ? parseFloat(data.min_amount) : null;
  data.max_amount = data.max_amount ? parseFloat(data.max_amount) : null;

  const url = editingRuleId ? `/api/rules/${editingRuleId}` : "/api/rules";
  const method = editingRuleId ? "PUT" : "POST";

  fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  })
    .then(res => res.json())
    .then(resp => {
      if (resp.success) {
        bootstrap.Modal.getInstance(document.getElementById("addRuleModal")).hide();
        loadRulesTable();
        console.log(`✅ Rule ${editingRuleId ? "updated" : "added"} successfully.`);

        // 🔁 Mark transactions for refresh when tab is next opened
        window.localStorage.setItem("transactionsNeedRefresh", "true");

        if (resp.summary) {
          console.log(`🔁 Rules reapplied: ${resp.summary.updated} updated, ${resp.summary.unchanged} unchanged`);
        }

      } else {
        alert("⚠️ Save failed: " + (resp.message || "unknown error"));
      }
    })
    .catch(err => console.error("❌ Save rule error:", err));
}



// === Delete rule ===
function onDeleteRule() {
  const rowData = rulesTable.row($(this).closest("tr")).data();
  const ruleId = rowData._id;

  if (!confirm(`Delete rule for assignment "${rowData.assignment}"?`)) return;

  fetch(`/api/rules/${ruleId}`, { method: "DELETE" })
    .then(res => res.json())
    .then(resp => {
      if (resp.success) {
        console.log(`🗑️ Deleted rule ${ruleId}`);
        loadRulesTable();

        window.localStorage.setItem("transactionsNeedRefresh", "true");

        if (resp.summary) {
          console.log(`🔁 Rules reapplied: ${resp.summary.updated} updated, ${resp.summary.unchanged} unchanged`);
        }

      } else {
        alert("⚠️ Delete failed: " + (resp.message || "unknown error"));
      }
    })
    .catch(err => console.error("❌ Delete rule error:", err));
}



// -----------------------------
// Footer Filter Inputs  (PATCH 1)
// -----------------------------
$('#rulesTable tfoot th').each(function () {
    const title = $(this).text();
    if (title !== 'Actions') {
        $(this).html('<input type="text" placeholder="Filter ' + title + '" />');
    } else {
        $(this).html('');
    }
});
