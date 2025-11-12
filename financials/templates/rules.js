// static/rules.js
let rulesTable = null;

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

function loadRulesTable() {
  fetch("/api/rules")
    .then(res => res.json())
    .then(data => {
      if ($.fn.DataTable.isDataTable("#rulesTable")) {
        const table = $("#rulesTable").DataTable();
        table.clear();
        table.rows.add(data);
        table.draw();
        return;  // ✅ stop here, don't reinit
      }

      // First-time initialization
      rulesTable = $("#rulesTable").DataTable({
        data,
        columns: [
          { data: "priority" },
          { data: "source" },
          { data: "description" },
          { data: "min_amount" },
          { data: "max_amount" },
          { data: "assignment" },
          {
            data: null,
            render: () => `
              <button class="btn btn-outline-primary btn-sm me-1 edit-btn">Edit</button>
              <button class="btn btn-outline-danger btn-sm delete-btn">Delete</button>
            `,
            orderable: false
          }
        ],
        order: [[0, "asc"]],
        scrollY: "60vh",
        scrollCollapse: true,
        paging: true,
      });
    })
    .catch(err => console.error("❌ Error loading rules:", err));
}


function openAddRuleModal() {
  document.getElementById("addRuleForm").reset();
  const modal = new bootstrap.Modal(document.getElementById("addRuleModal"));
  modal.show();
}

function saveRule() {
  const form = document.getElementById("addRuleForm");
  const data = Object.fromEntries(new FormData(form).entries());
  data.priority = parseInt(data.priority);
  data.min_amount = parseFloat(data.min_amount || 0);
  data.max_amount = parseFloat(data.max_amount || 0);

  fetch("/api/rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  })
    .then(res => res.json())
    .then(resp => {
      if (resp.success) {
        bootstrap.Modal.getInstance(document.getElementById("addRuleModal")).hide();
        loadRulesTable();
      } else {
        alert("⚠️ Save failed: " + (resp.message || "unknown error"));
      }
    })
    .catch(err => console.error("❌ Save rule error:", err));
}
