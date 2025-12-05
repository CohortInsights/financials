// templates/code.js

// --- Reload button handler ---
function reloadPage() {
    console.log("🔄 Reload button clicked");
    window.location.href = '/reload';
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', function() {
    console.log("📦 Initializing dashboard shell");

    // Attach reload button listener
    const reloadButton = document.getElementById('reloadButton');
    if (reloadButton) reloadButton.addEventListener('click', reloadPage);

    // Delegate all transaction handling to transactions.js
    if (typeof initTransactions === "function") {
        initTransactions();  // ✅ defined in transactions.js
    } else {
        console.error("❌ transactions.js not loaded or initTransactions missing");
    }

    // -------------------------------------------------------------
    // ⭐ NEW: Initialize Assignments ONLY when its tab is activated
    // -------------------------------------------------------------
    let assignmentsInitialized = false;

    const assignmentsTab = document.getElementById('assignments-tab');
    if (assignmentsTab) {
        assignmentsTab.addEventListener('shown.bs.tab', function () {
            if (!assignmentsInitialized) {
                if (typeof initAssignments === "function") {
                    console.log("📘 Initializing assignments dashboard");
                    initAssignments();
                    assignmentsInitialized = true;
                } else {
                    console.error("❌ assignments.js not loaded or initAssignments missing");
                }
            }
        });
    }
    // -------------------------------------------------------------
});
