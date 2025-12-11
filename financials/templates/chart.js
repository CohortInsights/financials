/* templates/chart.js
 *
 * Charting subsystem for Financials Portal.
 * Handles:
 *  - meta extraction from Assignments DataTable
 *  - JSON-driven strict eligibility (SM1)
 *  - menu enable/disable + tooltip
 *  - dialog launcher skeleton
 *  - public interface: Charting.init(), Charting.refresh()
 */

// ============================================================================
// CONFIG LOADING
// ============================================================================

// cache so repeated calls don't refetch
const ChartConfigs = {
    pie: null
};

// You may replace this with your own loadJSON()
async function loadChartConfig(chartType) {
    if (ChartConfigs[chartType]) return ChartConfigs[chartType];

    const url = `static/cfg-plots/${chartType}.json`;

    try {
        const res = await fetch(url);
        if (!res.ok) {
            console.error("Failed to load chart config:", url);
            return null;
        }
        const config = await res.json();
        ChartConfigs[chartType] = config;
        return config;
    } catch (e) {
        console.error("Error loading chart config:", e);
        return null;
    }
}

// ============================================================================
// META FROM ASSIGNMENTS TABLE
// ============================================================================

function computeAssignmentsChartMeta() {
    const table = $('#assignments').DataTable();
    const data = table.rows({ filter: 'applied' }).data();

    const levelsPresent = new Set();
    const assignmentsByLevel = new Map();
    const years = new Set();
    const periods = new Set();

    let hasPositive = false;
    let hasNegative = false;
    let countRows = 0;

    data.each(row => {
        const assignment = row.assignment;
        const level = row.level;
        const amount = row.amount;
        const sortYear = row.sort_year;
        const sortPeriod = row.sort_period;

        countRows += 1;

        // Level + assignment dimension
        if (typeof level === "number") {
            levelsPresent.add(level);

            if (assignment && assignment.trim() !== "") {
                if (!assignmentsByLevel.has(level)) {
                    assignmentsByLevel.set(level, new Set());
                }
                assignmentsByLevel.get(level).add(assignment);
            }
        }

        // Time structure
        if (typeof sortYear === "number") years.add(sortYear);
        if (typeof sortPeriod === "number") periods.add(sortPeriod);

        // Sign detection
        if (typeof amount === "number") {
            if (amount > 0) hasPositive = true;
            if (amount < 0) hasNegative = true;
        }
    });

    // Major + minor levels
    let majorLevel = null;
    const minorLevels = [];
    const sortedLevels = Array.from(levelsPresent).sort((a, b) => a - b);

    for (const lvl of sortedLevels) {
        const levelSet = assignmentsByLevel.get(lvl);
        const distinct = levelSet ? levelSet.size : 0;

        if (distinct > 1 && majorLevel === null) {
            majorLevel = lvl;
        } else if (majorLevel !== null && lvl > majorLevel) {
            minorLevels.push(lvl);
        }
    }

    // Sign state
    let signState = "zero";
    if (hasPositive && hasNegative) signState = "mixed";
    else if (hasPositive) signState = "positive";
    else if (hasNegative) signState = "negative";
    else signState = "positive"; // all-zero treated as positive for eligibility

    return {
        row_count: countRows,
        levels_present: sortedLevels,
        major_level: majorLevel,
        minor_levels: minorLevels,
        sort_year_count: years.size,
        sort_period_count: periods.size,
        sign_state: signState
    };
}

// ============================================================================
// ELIGIBILITY (STRICT MODE; JSON DRIVES EVERYTHING)
// ============================================================================

function evaluateChartEligibility(chart_type, meta, config) {
    if (!config) {
        return {
            chart_type,
            eligible: false,
            reasons: ["Chart config not found."]
        };
    }

    const reasons = [];
    const elig = config.eligibility || {};
    const dis = config.disallowed_conditions || {};

    // Requires major level
   	if (elig.requires_major_level && !meta.major_level) {
        if (dis.no_major_level) reasons.push(dis.no_major_level);
    }

    // Single year
    if (elig.requires_single_year && meta.sort_year_count > 1) {
        if (dis.multiple_years) reasons.push(dis.multiple_years);
    }

    // Single period
    if (elig.requires_single_period && meta.sort_period_count > 1) {
        if (dis.multiple_periods) reasons.push(dis.multiple_periods);
    }

    // No minor levels
    if (elig.requires_no_minor_levels && meta.minor_levels.length > 0) {
        if (dis.has_minor_levels) reasons.push(dis.has_minor_levels);
    }

    // Same sign
    if (elig.requires_same_sign && meta.sign_state === "mixed") {
        if (dis.mixed_sign) reasons.push(dis.mixed_sign);
    }

    return {
        chart_type,
        eligible: reasons.length === 0,
        reasons
    };
}

// ============================================================================
// TOOLTIP
// ============================================================================

function formatEligibilityTooltip(label, reasons) {
    if (!reasons || reasons.length === 0) return "";
    const lines = [`Cannot create ${label}:`];
    for (const r of reasons) lines.push("• " + r);
    return lines.join("<br>");
}

// ============================================================================
// PIE MENU CONTROL
// ============================================================================

async function updatePieChartMenu(meta) {
    const item = document.getElementById("chart-menu-pie");
    if (!item) return;

    const cfg = await loadChartConfig("pie");
    const result = evaluateChartEligibility("pie", meta, cfg);

    if (result.eligible) {
        item.classList.remove("disabled");
        item.style.opacity = "";
        item.dataset.chartEnabled = "true";

        // ⭐ Remove stale tooltip instance when enabling
        const tipInstance = bootstrap.Tooltip.getInstance(item);
        if (tipInstance) {
            tipInstance.dispose();
        }

        item.removeAttribute("title");
    } else {
        item.classList.add("disabled");
        item.style.opacity = "0.5";
        item.dataset.chartEnabled = "false";

        const tip = formatEligibilityTooltip("pie chart", result.reasons);
        item.setAttribute("title", tip);

        // ⭐ Ensure tooltip is active or updated
        bootstrap.Tooltip.getOrCreateInstance(item, { html: true });
    }

}

function attachPieChartMenuHandler() {
    const item = document.getElementById("chart-menu-pie");
    if (!item) return;

    item.addEventListener("click", function (e) {
        e.preventDefault();
        if (item.dataset.chartEnabled !== "true") return;
        openPieChartDialogSkeleton();
    });
}

// ============================================================================
// DIALOG SKELETON
// ============================================================================

function openPieChartDialogSkeleton() {
    const title = document.getElementById("chart-modal-title");
    if (title) title.textContent = "Pie Chart";

    const btn = document.getElementById("chart-generate-btn");
    if (btn && !btn.dataset.bound) {
        btn.addEventListener("click", () => {
            console.log("Generate Chart (Pie) — placeholder");
            // Here we will later call: compute_pie_chart(...)
        });
        btn.dataset.bound = "true";
    }

    const modalEl = document.getElementById("chart-modal");
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

// ============================================================================
// PUBLIC API
// ============================================================================

const Charting = {

    init() {
        attachPieChartMenuHandler();
    },

    async refresh() {
        const meta = computeAssignmentsChartMeta();
        await updatePieChartMenu(meta);
    }
};

window.Charting = Charting;
