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
});
