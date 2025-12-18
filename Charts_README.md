# Financials Portal — Charting Specification (Canonical README)

This README documents the **complete charting system** for the Financials Portal,
including:

- Overall charting philosophy  
- Definitions and terminology  
- Eligibility rules for each chart type  
- Interpretation rules for levels, assignments, years, and periods  
- Detailed disallow and ignore rules  
- Canonical JSON chart-spec format  
- Labeling and ordering rules  
- Canonical examples from real data  
- Behavior for mixed-sign data  
- Integration notes for compute_chart()  

This document is authoritative and is intended to eliminate ambiguity in both
client-side and server-side logic.

───────────────────────────────────────────────────────────────────────────────

# 1. Charting Philosophy

Charts in the Financials Portal are generated **entirely from the FILTERED state
of the Assignments tab**.  
Charts **never reach back to the server** for aggregate values.

The system follows this philosophy:

1. **User filtering controls the levels that appear in the table**  
2. **Starting from level 1,2,3 the first level containing more than one assignment is dubbed the "major" level**  
3. **A chart is either allowed or disallowed**  
4. If disallowed, a **modal dialog** explains *every* reason (not just the first encountered one)  
5. Client charting uses **Plotly** or similar, with minimal data massaging, Do NOT perform data integrity checks in charting layaer
6. Server prepares consistent data including `sort_year` and `sort_period".  
7. The server performs all data roll ups
8. Missing time periods are treated as **zero amounts**, not absent data
9. The goal is consistent, predictable chart behavior, not a “best guess” chart,
C0. Chart properties that the operator may change are in a "parameters" section of the chart type

───────────────────────────────────────────────────────────────────────────────

# 2. Data Model and Terminology

## 2.1 Assignment Levels  
Assignments are hierarchical:  
Example: `Expense.Food.Restaurant` has:

- Level 1: Expense  
- Level 2: Expense.Food  
- Level 3: Expense.Food.Restaurant  

Filtered data contains one or more levels depending on the user’s level filter.

### Top Level
The **lowest numbered level** present in the filtered data.

### Major Level
The **first level** whose filtered data contains **more than one distinct
assignment**.  
This level determines the assignment dimension that drives the chart.

### Minor Levels  
All levels deeper than the major level (if any exist).

───────────────────────────────────────────────────────────────────────────────

## 2.2 Time Structure

Three independent notions:

### Literal Period (`period`)
Exact string from the table:  
Examples: `2023`, `2025-Q3`, `2025-07`.

### Canonical Year (`sort_year`)
Integer year extracted by server.

### Canonical Period Index (`sort_period`)
Integer period ordering number created by server for correct chronological order:
- Annual view: `sort_period = 1`
- Quarter view: `sort_period = 1…4`
- Month view: `sort_period = 1…12`

### Time Categories  
- **Y1**: one year present  
- **Ym**: multiple years present  
- **P1**: one period present (meaning *annual*)  
- **Pm**: multiple periods (quarterly or monthly) present  

───────────────────────────────────────────────────────────────────────────────

## 2.3 Sign Behavior

Before rendering:

- If **all values ≥ 0**, plot normally.  
- If **all values ≤ 0**, plot using **absolute value**.  
- If **mixed-sign**, behavior depends on chart type:

### Mixed-sign rules:
- Pie chart → **disallowed**  
- Stacked area → **disallowed**  
- Bar charts → **allowed** (positive upward, negative downward). 
- When mixed-sign and multiple years are present, the cluster is ordered by year only i.e. positive & negative values within the same time period are in the same cluster

───────────────────────────────────────────────────────────────────────────────

# 3. Chart Eligibility Overview

The system supports **three chart types**, each with variants:

1. **Pie Chart**  
2. **Bar Chart**  
   - Simple bars  
   - Stacked bars  
3. **Stacked Area Chart**

Each chart type has explicit **allowed/disallowed conditions** based on:

- Number of assignments  
- Number of periods  
- Number of years  
- Presence of minor levels  
- Sign of data  

All disallow conditions appear in a single modal dialog.

───────────────────────────────────────────────────────────────────────────────

# 4. Pie Chart Specification

## 4.1 Eligibility Rules

A pie chart is allowed **only if ALL are true**:

1. Major level exists (major_levels = [Lm])  
2. No minor levels present  
3. **sort_period_count = 1** (P1)  
4. **sort_year_count = 1** (Y1)  
5. All data **same sign** (all positive or all negative)

If any fail → disallowed with reasons.

## 4.2 Behavior When Allowed

- One pie per major assignment if multiple pies are needed.  
- Multi-chart limit: If >4 pies → show warning and use grid layout.  
- Slices represent the minor values **within the same major layer**.  
- Slice labels use **shortest unique trailing fragment**.  
- “Other” rule: slices < {min_fraction} of total combine into “Other”.
- Producing warning if number of pie charts > {max_chart_count}

───────────────────────────────────────────────────────────────────────────────

# 5. Bar Charts (Core Specification)

Two types:

- **Simple Bar Chart** (no minor levels)  
- **Stacked Bar Chart** (minor levels present)

Bar charts are **very flexible** and support:

- Mixed signs  
- Multi-year (clusters)  
- Multi-period (chart rows)  
- Multi-assignment  
- Minor assignments (stacking)

## 5.1 Axis Roles

### Bar axis:
- Always **assignment axis**, except special case:
  - If exactly **one major assignment** and multiple periods are present, bar axis = **period axis**

### Amount axis:
- Always vertical (y) for vertical bars 
- Always horizontal (x) for horizontal vars
- Zero is centered up/down (vertical) or left/right (horizontal) if mixed-sign

───────────────────────────────────────────────────────────────────────────────

## 5.2 Time Layout for Bar Charts

### If **Pm** (multiple periods):
- One **chart row per period** (Q1, Q2, Q3, Q4)
- Within each row:
  - Bars are grouped by assignment OR  
  - If one assignment, bars along non bar axis represent periods

### If **Ym** (multiple years):
- Each period row contains **clusters of bars**, one per year:
  Example for quarterly with same sign: 3 cluster years (2023,2024, 2025):
      Q1 row:
        [2023-Q1 Expense] [2024-Q1 Expense] [2025-Q1 Expense]
      Q2 row
        [2023-Q1 Expense ] [2024-Q1 Expense ] [2025-Q1 Expense ]
  Example for mixed-sign quarterly with income(+) and expense(-): 2 cluster years (2023,2024):
      Q1 row:
        [2023-Q1 Income (up), Expense(down)] [2024-Q1 Income (up), Expense(down)]
      Q2 row
        [2023-Q2 Income (up), Expense(down)] [2024-Q2 Income (up), Expense(down)]

───────────────────────────────────────────────────────────────────────────────

## 5.3 Simple Bar Eligibility

Simple bar allowed if:

1. Exactly **one major level**  
2. **No minor levels**  
3. Period/year structure irrelevant  
4. Mixed-sign allowed  

If >1 assignment at major level AND minor levels absent → still simple bars.
Simple bars are used unless minor levels force stacking.

───────────────────────────────────────────────────────────────────────────────

## 5.4 Stacked Bar Eligibility

Stacked bar used when:

- Major level has >1 assignment AND  
- Minor levels exist (levels deeper than major)  

Interpretation:

- Bar = assignment  
- Stack = minor-level components  
- If one assignment, bars = periods, stacks = minors

───────────────────────────────────────────────────────────────────────────────

# 6. Stacked Area Chart Specification

## 6.1 Eligibility Rules

Stacked area chart is allowed only if:

1. **sort_period_count > 1 (Pm)**  
2. Exactly one major assignment OR multiple assignments
3. **All values are same-sign** (no mixed-sign values)  
4. There is a meaningful time series on x-axis

Disallowed if:

- Mixed-sign amounts  
- Only one period (P1)

## 6.2 Behavior When Allowed

- Only rows for major level are processed; rows with level < major level are ignored
- x-axis = chronological periods  
- y-axis = amount value (or absolute if negative-only)  
- Each distinct assignment value is a stacked layer
- Default y-values are **integrals across time**, but raw series may be another mode  

───────────────────────────────────────────────────────────────────────────────

# 7. Labeling Rules

## Shortest Unique Trailing Fragment
Given assignments:

    Expense.Food.Restaurant
    Expense.Food.Fast
    Expense.Services.HVAC

We extract trailing components:

    Restaurant → unique
    Fast → unique
    HVAC → unique

If conflict arises, extend leftward:

    a.c → c  
    a.d → d  
    a.c.x → “a.x” (because “x” alone not unique)

Labels evaluated separately for:

- Bar-level assignment labels  
- Stack-level labels (minor levels)  
- Pie slice labels  

───────────────────────────────────────────────────────────────────────────────

# 8. Ordering Rules

### Assignment ordering:
Always determined by **the table order**, which is server-defined by:

- Sorting assignments by **sum of absolute amounts** across the dataset.

### Stack ordering:
Bottom to top = table order (largest values in the table are at the bottom stack layer).
Parent Bar height: SOLELY determined by amount of major row (NOT sum of child segments!!!) 
Segment height: Solely determined by amount of child (Sum of child segments ARE OFTEN LESS than height of parent bar!!!)
Bar colors: Best to use a parent color distinct from segment color.  This will make it obvious when sum of segment heights < parent height
Example:
  Expense.Travel -10000
  Expense.Travel.Air -5320
  Expense.Travel.Lodging -2100
  Expense.Entertainment  -8000
  Two bars (Travel,Entertainment) with heights of 10000 and 8000.
  The Entertainment bar is all blue with no segments
  The Travel bar from bottom to top has two yellow segments (Air,Lodging with heights of 5320 and 2100)
  The top segment of the Travel bar is blue (no label). The blue height is (10000 - 5320 - 2100 = 3700)
  IMPLEMENTATION NOTE: Van be thought of as plotting a blue bar with height 10000 and overlaying two opaque bottom yellow segments (heights of 5320 and 2100)

### Area ordering:
Same as stacked bar ordering.

───────────────────────────────────────────────────────────────────────────────

# 9. Canonical JSON Chart Specification

Each chart type has a JSON file in `cfg-plots/`.

Example structure:

    {
      "chart_type": "pie",
      "parameters": {
        "min_fraction": 0.05,
        "max_chart_count": 4
      },
      "disallowed": {
        "mixed_sign": true,
        "multiple_years": true,
        "multiple_periods": true,
        "has_minor_levels": true
      },
      "interpretation": {
        "uses_major_level": true,
        "uses_minor_level": false,
        "abs_for_negative": true
      },
      "labeling": {
        "shortest_unique_fragment": true
      }
    }

All compute functions read this JSON when determining whether a chart is
allowed and how to process data.

───────────────────────────────────────────────────────────────────────────────

# 10. Canonical Examples

Below are the real examples provided during design.

Each example includes the **meta state**, **allowed charts**, and the **reasons**.

───────────────────────────────────────────────────────────────────────────────

# Example A: Single Level, One Year (Annual)

Data (abbreviated):

    2025   Expense.Food.Restaurant   -11725.94
    2025   Expense.Food.Groceries    -10309.62
    …

Meta:

    major_level = 3
    minor_levels = none
    sort_year = Y1
    sort_period = P1
    sign = negative-only

Allowed:

- Pie chart (single year, single period, single level, same sign)
- Simple bar chart (no minors)

───────────────────────────────────────────────────────────────────────────────

# Example B: Single Level, Quarterly (One Year)

Meta:

    major_level = 3
    minor_levels = none
    sort_year = Y1
    sort_period = Pm
    sign = negative-only

Allowed:

- Pie chart → disallowed (multiple periods)
- Simple bar chart → allowed
- Stacked area → allowed (multiple periods, uniform sign)

───────────────────────────────────────────────────────────────────────────────

# Example C: Multi-Year Annual (Single Level)

Meta:

    major_level = 3
    sort_year = Ym
    sort_period = P1

Allowed:

- Pie → disallowed (multiple years)
- Simple bar → allowed (clusters by year)
- Stacked area → disallowed (only one period)
- Stacked bar → allowed (clusters)

───────────────────────────────────────────────────────────────────────────────

# Example D: Single Assignment, Monthly Series (One Level)

Meta:

    major_level = 3
    assignments = 1
    sort_period = Pm
    sort_year = Y1
    sign = negative-only

Allowed:

- Stacked area chart (positive-only after abs transform)
- Simple bar chart (one assignment → x-axis = periods)
- Pie chart → disallowed

───────────────────────────────────────────────────────────────────────────────

# Example E: Multi-Level, One Year (Annual)

Meta:

    major_level = 2
    minor_levels = [3]
    sort_period = P1
    sort_year = Y1

Allowed:

- Pie chart → one pie per level-2 assignment, slices = level-3
- Stacked bar chart → bars = level-2 assignments, stacks = level-3
- Simple bar → disallowed (minor levels exist)
- Stacked area → disallowed (only one period)

───────────────────────────────────────────────────────────────────────────────

# Example F: Multi-Level, Multi-Year (Annual)

Meta:

    major_level = 2
    minor_levels = [3]
    sort_year = Ym
    sort_period = P1

Allowed:

- Pie chart → disallowed (Ym)
- Stacked bar → allowed (clusters per year; stacks = minors)
- Simple bar → disallowed
- Stacked area → disallowed (only one period)

───────────────────────────────────────────────────────────────────────────────

# Example G: Multi-Level, Multi-Year, Multi-Period (Single Major Level)

Meta:

    major_level = 2
    minor_levels = [3]
    sort_year = Ym
    sort_period = Pm
    mixed_sign = yes/no depending on dataset

Allowed:

- Stacked area → disallowed (minors exist)
- Stacked bar → allowed
- Simple bar → disallowed (minors exist)  
- Pie → disallowed (Pm + Ym + sign rules)

───────────────────────────────────────────────────────────────────────────────

# Example H: Mixed-Sign Income/Expense Quarterly (Level 1)

This is the canonical mixed-sign example.

Meta:

    major_level = 1
    minor_levels = none
    sort_year = Ym
    sort_period = Pm
    mixed_sign = true

Allowed:

- Simple bar chart → YES if there are no minor data rows
  - Clusters by year  
  - Chart rows for each period  
  - Stacks = Each year cluster contains positive bar (up) and negative bar (down)
- Stacked bar chart -> YES (if there ARE minor data rows)
  - Just like simple bar chart with minor data appearing as segments
- Pie → NO (mixed sign + multi-year + multi-period)
- Stacked area → NO (mixed sign)

───────────────────────────────────────────────────────────────────────────────

# 11. Disallowed Conditions (Modal)

When a chart is disallowed, the modal lists **every triggered reason**.

Examples:

    - Multiple periods present (pie requires P1)
    - Multiple years present (pie requires Y1)
    - Mixed positive and negative values (pie/area disallow)
    - Minor levels present (simple bar requires no minors)
    - Only one period present (stacked area requires >1)
    - Multiple assignments present (simple bar special case violated)

This is an explicit feature: charts never silently disappear.

───────────────────────────────────────────────────────────────────────────────

# 12. Integration Notes for compute_chart()

The compute system:

- Reads the JSON spec  
- Extracts meta from filtered data  
- Calls chart-specific compute functions:

      compute_pie_chart(meta, data)
      compute_bar_chart(meta, data)
      compute_stacked_area_chart(meta, data)

- Performs only minimal transformations:
  - Zero-fill missing periods  
  - Apply abs(values) for all-negative charts  
  - Prepare cluster structures (years)  
  - Derive shortest unique labels

All ordering, filtering, collapsing, and hierarchy interpretation are upstream.

#13 Color Management 

Color assignment is owned by our charting system, not by Matplotlib.
Matplotlib receives explicit colors and never invents or cycles them.

Within a single rendering, the same assignment always has the same color across all charts.
Across different renderings, colors are not guaranteed to be stable.

Color identity is guaranteed only up to 16 distinct assignments per rendering; beyond that, colors are reused deterministically with warning.

───────────────────────────────────────────────────────────────────────────────

# 14. Summary Matrix

A compact reference:

    Pie:        Y1, P1, Lm, same-sign, no minors
    Bar-Simple: minor_levels = none
    Bar-Stack:  minor_levels exist
    Area:       Pm AND same-sign AND (major only OR one assignment)

Mixed-sign → only **bar charts**.

───────────────────────────────────────────────────────────────────────────────

# End of README
