/* templates/chart.js
 *
 * RESTORED WORKING BASELINE
 * ----------------------------------------------------------
 * This version:
 *   - computes pie data from the Assignments table
 *   - renders directly into #chart-canvas (no offscreen PNG)
 *   - preserves eligibility + menu enable/disable
 *   - ensures the Generate button works correctly
 *   - is stable and safe for iterative development
 */

// ============================================================================
// CONFIG LOADING
// ============================================================================

const ChartConfigs = { pie: null };

async function loadChartConfig(chartType) {
    if (ChartConfigs[chartType]) return ChartConfigs[chartType];
    const url = `static/cfg-plots/${chartType}.json`;

    try {
        const res = await fetch(url);
        if (!res.ok) {
            console.error("Failed to load chart config:", url);
            return null;
        }
        ChartConfigs[chartType] = await res.json();
        return ChartConfigs[chartType];
    } catch (err) {
        console.error("Error loading chart config:", err);
        return null;
    }
}

// ============================================================================
// META EXTRACTION
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
        const level = row.level;
        const assignment = row.assignment;
        const amount = row.amount;

        const y = row.sort_year;
        const p = row.sort_period;

        countRows += 1;

        if (typeof level === "number") {
            levelsPresent.add(level);
            if (assignment) {
                if (!assignmentsByLevel.has(level)) {
                    assignmentsByLevel.set(level, new Set());
                }
                assignmentsByLevel.get(level).add(assignment);
            }
        }

        if (typeof y === "number") years.add(y);
        if (typeof p === "number") periods.add(p);

        if (amount > 0) hasPositive = true;
        if (amount < 0) hasNegative = true;
    });

    // Determine major + minor
    let majorLevel = null;
    const minorLevels = [];
    const sortedLevels = Array.from(levelsPresent).sort((a,b)=>a-b);

    for (const lvl of sortedLevels) {
        const distinct = assignmentsByLevel.get(lvl)?.size || 0;
        if (distinct > 1 && majorLevel === null) {
            majorLevel = lvl;
        } else if (majorLevel !== null && lvl > majorLevel) {
            minorLevels.push(lvl);
        }
    }

    let sign = "zero";
    if (hasPositive && hasNegative) sign = "mixed";
    else if (hasPositive) sign = "positive";
    else if (hasNegative) sign = "negative";

    return {
        row_count: countRows,
        levels_present: sortedLevels,
        major_level: majorLevel,
        minor_levels: minorLevels,
        sort_year_count: years.size,
        sort_period_count: periods.size,
        sign_state: sign
    };
}

// ============================================================================
// ELIGIBILITY
// ============================================================================

function evaluateChartEligibility(chartType, meta, config) {
    if (!config) {
        return { chartType, eligible:false, reasons:["Missing config file"] };
    }

    const E = config.eligibility;
    const D = config.disallowed_conditions;
    const reasons = [];

    if (E.requires_major_level && !meta.major_level)
        reasons.push(D.no_major_level);

    if (E.requires_single_year && meta.sort_year_count > 1)
        reasons.push(D.multiple_years);

    if (E.requires_single_period && meta.sort_period_count > 1)
        reasons.push(D.multiple_periods);

    if (E.requires_no_minor_levels && meta.minor_levels.length > 0)
        reasons.push(D.has_minor_levels);

    if (E.requires_same_sign && meta.sign_state === "mixed")
        reasons.push(D.mixed_sign);

    return {
        chartType,
        eligible: reasons.length === 0,
        reasons
    };
}

// ============================================================================
// TOOLTIP
// ============================================================================

function formatEligibilityTooltip(label, reasons) {
    if (!reasons || reasons.length === 0) return "";
    return ["Cannot create " + label + ":", ...reasons.map(r=>"• "+r)].join("<br>");
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

        const tip = bootstrap.Tooltip.getInstance(item);
        if (tip) tip.dispose();
        item.removeAttribute("title");
    } else {
        item.classList.add("disabled");
        item.style.opacity = "0.5";
        item.dataset.chartEnabled = "false";

        const tipText = formatEligibilityTooltip("pie chart", result.reasons);
        item.setAttribute("title", tipText);
        bootstrap.Tooltip.getOrCreateInstance(item, { html:true });
    }
}

function attachPieChartMenuHandler() {
    const item = document.getElementById("chart-menu-pie");
    if (!item) return;
    item.addEventListener("click", e => {
        e.preventDefault();
        if (item.dataset.chartEnabled === "true") {
            openPieChartDialog();
        }
    });
}

// ============================================================================
// PIE COMPUTATION (simple working version)
// ============================================================================

async function compute_pie_chart() {
    console.log("▶ compute_pie_chart()");

    const table = $('#assignments').DataTable();
    const rows = table.rows({ filter:'applied' }).data().toArray();

    const sums = {};
    for (const r of rows) {
        const a = r.assignment;
        if (!a) continue;
        sums[a] = (sums[a] || 0) + Math.abs(r.amount);
    }

    return {
        chart_type: "pie",
        pies: [{
            labels: Object.keys(sums),
            values: Object.values(sums)
        }]
    };
}

// ============================================================================
// WORKING PIE RENDERER (stable baseline)
// ============================================================================

async function renderPieChart(spec) {
    console.log("▶ renderPieChart()");

    const pie = spec.pies[0];
    const container = document.getElementById("chart-canvas");
    if (!container) {
        console.error("chart-canvas not found");
        return;
    }

    container.innerHTML = "";

    const trace = {
        type: "pie",
        labels: pie.labels,
        values: pie.values,
        textinfo: "percent",
        textposition: "inside",
        sort: false
    };

    const layout = {
        margin: { t: 20, l: 20, r: 20, b: 20 },
        width: container.clientWidth || 600,
        height: container.clientHeight || 400
    };

    await Plotly.newPlot(container, [trace], layout);

    console.log("▶ renderPieChart() done");
}

// ============================================================================
// DIALOG
// ============================================================================

function openPieChartDialog() {
    const modalEl = document.getElementById("chart-modal");
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

// ============================================================================
// INITIALIZATION
// ============================================================================

const Charting = {
    init() {
        attachPieChartMenuHandler();

        const btn = document.getElementById("chart-generate-btn");
        if (btn && !btn.dataset.bound) {
            btn.addEventListener("click", async () => {
                console.log("▶ PIE GENERATE CLICK");
                const spec = await compute_pie_chart();
                await renderPieChart(spec);
            });
            btn.dataset.bound = "true";
        }
    },

    async refresh() {
        const meta = computeAssignmentsChartMeta();
        await updatePieChartMenu(meta);
    }
};

window.Charting = Charting;
