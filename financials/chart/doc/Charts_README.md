# Financials Portal — Charting Specification

This README documents the complete charting system for the Financials Portal.

It is authoritative and intended to eliminate ambiguity in:
- server-side computation
- client-side consumption
- renderer behavior
- future extensions

This document defines both:
- the conceptual meaning of charts, and
- the data contracts that enforce those meanings.

----------------------------------------------------------------
## 1. Charting Philosophy
----------------------------------------------------------------

1. The filtered Assignments table is the sole authoritative source for computing chart content.
2. Assignment data may be filtered by user controls (currently assignment substring and level).
3. All chart-specific computation (aggregation, ordering, sign handling, color assignment, percentages)
   is completed before rendering.
4. The resulting chart data (chart_element and figure_data) is the sole authoritative input to rendering.
5. Renderers (Matplotlib server-side; Plotly or others later) perform no decisions, inference,
   sorting, or computation. Their only job is to render what they are given.

----------------------------------------------------------------
## 2. Pipeline Overview
----------------------------------------------------------------

A single chart query expresses intent and may be materialized at multiple stages.

Example query (as URL parameters):

    ?chart=area&asn=Food&level=3,4&years=2023,2024,2025

Routes using the same query:

- /api/filtered_assignments  -> source data (filtered assignments)
- /api/charts/data           -> chart element data
- /api/charts/figures        -> figure specifications
- /api/charts/render         -> rendered image (PNG/SVG)

Each route answers a different question.
No route recomputes decisions made upstream.

The browser JavaScript consumes:
- /api/assignments for tables and drill-down
- /api/charts/render for final visuals

All routes are directly accessible for manual inspection and debugging.

----------------------------------------------------------------
## 3. Source Data Model and Terminology
----------------------------------------------------------------

### 3.1 Assignment Identity

Assignments are represented as strings (e.g. `Expense.Food.Restaurant`).

The charting system does not assign semantic meaning to assignment depth,
hierarchy, or prefix structure. Any interpretation of assignment structure
is the responsibility of upstream computation.

For charting purposes:
- Assignment values are treated as opaque identifiers.
- Series identity is determined solely by explicit bindings in chart data.
- No inference is performed based on assignment string structure.

### 3.2 Time Structure

Three independent notions exist:

Literal Period (period):
- Exact string from source data (e.g. 2023, 2025-Q3, 2025-07).

Canonical Year (sort_year):
- Integer year extracted by the server.

Canonical Period Index (sort_period):
- Integer ordering index used for correct chronology:
  - Annual: 1
  - Quarterly: 1..4
  - Monthly: 1..12

Time categories:
- Y1 / Ym -> one or multiple years
- P1 / Pm -> one or multiple periods

### 3.3 Sign Behavior

When chart data is computed:

- All values >= 0 -> plotted normally
- All values <= 0 -> plotted using absolute values
- Mixed-sign behavior depends on chart type

Mixed-sign rules:
- Bar charts        -> positive above zero, negative below
- Pie charts        -> negative values removed
- Stacked area      -> negative values removed

----------------------------------------------------------------
## 4. Chart Types
----------------------------------------------------------------

Supported chart types:

1. Pie Chart
2. Bar Chart
   - Simple bars
   - Stacked bars
3. Stacked Area Chart

----------------------------------------------------------------
## 5. Chart Element Data (chart_element)
----------------------------------------------------------------

Purpose:
- chart_element is the authoritative, fully computed description of what will be drawn.
- It is a pandas DataFrame and is renderer-ready.

Row Semantics:
- Each row represents one drawable element within one figure.

chart_index (authoritative):
- Canonical figure identifier
- All rows with the same chart_index belong to exactly one figure
- Rows with different chart_index values must never be combined
- Figures are rendered in data order of first appearance
- chart_index has no temporal meaning

cluster (authoritative):
- Explicit stacking and grouping identifier
- Rows with the same (chart_index, period, cluster) are stacked together
- Rows with different cluster values are never stacked together
- cluster has no semantic meaning beyond grouping

Irregularity Rule:
- All irregular, data-dependent, order-sensitive entities live in chart_element.

Examples of irregular entities that must be in chart_element:
- bars, slices, stacked areas
- per-element labels
- per-element colors
- per-element percentages
- stacking group membership (cluster)

Geometry and Metrics:
- values     -> exact geometry used for drawing
- percent    -> precomputed upstream; renderer never computes percentages
- count,
  amount,
  mag,
  threshold -> informational only

Color:
- color is a color index assigned upstream
- Color sequencing follows DataFrame row order
- Renderers never infer or cycle colors

Ordering Invariant (global):
- All visual ordering derives strictly from DataFrame row order. Always.

This applies to:
- x-axis progression
- legend order
- color order
- annotation order

----------------------------------------------------------------
## 6. Figure Specification Data (figure_data)
----------------------------------------------------------------

Purpose:
- figure_data describes how each figure is rendered, not what data exists.
- It contains only singletons and regular (rule-based) layout instructions.

Structure:
- figure_data is a dictionary keyed by chart_index:

    {
      chart_index: {
        key: value,
        key: value,
        ...
      }
    }

Values are JSON-safe scalars or lists and may be returned directly from an API route.

What figure_data may contain:

Singletons:
- chart_type
- title / subtitle
- legend visibility and title
- palette name
- order policy (data_order)
- frame dimensions and DPI
- axis bindings
- orientation rules

Regular rules:
- axis bindings (which column is x, y, stack, legend)
- tick spacing rules
- label formatting
- label orientation
- grid rules

What figure_data must not contain:
- irregular lists
- per-element data
- computed metrics
- renderer heuristics

Rule:
- If something is irregular and not a singleton, it is illegal in figure_data.

----------------------------------------------------------------
## 7. Axis and Tick Model
----------------------------------------------------------------

No Implicit Axes:
- No column has implicit axis meaning.
- Axis roles are explicitly declared in figure_data.

Time Axes:
- Time tick spacing is always regular.
- Supported units: year, quarter, month.
- Ticks are specified by rules, not lists.

Major Ticks:
- Defined by regular rules
- All major ticks are labeled by default
- Label format always matches format of period column in element data
- Figure specifies label orientation or rotation

Minor Ticks:
- Defined by regular rules
- Never labeled by default
- Exist only if explicitly specified

Explicit Rule:
- Ticks (major or minor) exist only if specified.
- No inference. No automatic "nice" behavior.

----------------------------------------------------------------
## 8. Chart-Type-Specific Notes
----------------------------------------------------------------

### 8.1 Pie Charts
- Show relative composition of assignments.
- Multiple periods produce multiple charts (no time evolution within a single pie).
- Negative values are removed prior to rendering.

### 8.2 Bar Charts
- Support mixed signs.
- Support multiple years and periods.
- Support stacked bars via cluster.
- Axis orientation determined by figure_data.
- Zero line centered if mixed-sign.

### 8.3 Stacked Area Charts
- Each stacked area corresponds to one row in chart_element.
- Stacking is determined explicitly by the cluster column.
- Rows with the same (chart_index, period, cluster) are stacked together.
- Stack order is bottom-up in DataFrame row order.
- x-axis is chronological as bound in figure_data.
- y-axis is values (absolute if negative-only).
- No hierarchical or structural inference is performed.

----------------------------------------------------------------
## 9. Renderer Contract
----------------------------------------------------------------

The renderer:
- Consumes:
  - chart_element (DataFrame)
  - figure_data (dictionary)
- Performs:
  - no computation
  - no inference
  - no sorting or reordering
- Produces pixels only

----------------------------------------------------------------
## 10. Design Doctrine (Summary)
----------------------------------------------------------------

- chart_element owns all irregularity
- figure_data owns only singletons and regular rules
- chart_index defines figures
- cluster defines stacking
- Data order is law
- Percentages are precomputed
- Renderers are dumb

This separation is intentional and enforced.

# End of README
