# Financials Portal — Charting Specification

This README documents the **complete charting system** for the Financials Portal,
including:

- Overall charting philosophy  
- Definitions and terminology  
- Canonical examples from real data  

This document is authoritative and is intended to eliminate ambiguity in both
client-side and server-side logic.

# 1. Charting Philosophy

The filtered Assignments table is the sole authoritative source for chart-data computation.

1. User filtering controls the table data. Fitering can occur by assignment and level  
2. Tabular Assignment (or "source data") is transposed into tabular chart data specific  
for each chart type. All post assignment computation, ordering, and
chart content including color assignment are completed in this layer.
3. The maplotlib engine is used to render charts from the chart data. The
rendering layer should make no decisions or computations. Its only
function is to render.

# 2. Source Data Model and Terminology

## 2.1 Assignment Levels  
Assignments are hierarchical:  
Example: `Expense.Food.Restaurant` has:

- Level 1: Expense  
- Level 2: Expense.Food  
- Level 3: Expense.Food.Restaurant  

Rows can be chosen in the assignments tab with a user filter. For example, a filter of "2,3" would result
in only rows appearing with a level of 2 or 3.

### Major Level
The **first level** whose filtered data contains **more than one distinct
item (row)**.  
This level determines the assignment dimension that drives the chart.

### Minor Level  
The assignment level deeper than the major level (if not filtered). In
a filter of 2,3 where both levels contain more than one row, 2 is
the major level and 3 is the minor level.

### Levels Left After Charting
When charting occurs, the number of items will be computed for each level
* Let n = the number of levels containing MORE than one item
- n == 1: A single major level exists in the chart
- n == 2: A major and minor level exists in the chart
- n > 2: The two most deep levels are chosen to be the major and minor level

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

## 2.3 Sign Behavior

When chart data is computed:

- If **all values ≥ 0**, plot normally.  
- If **all values ≤ 0**, plot using **absolute value**.  
- If **mixed-sign**, behavior depends on chart type. 

### Mixed-sign rules:
- Bar charts → positive and negative data appear above and below a zero line 
- Pie and stack area charts → negative values are ignored  (removed from chart data)

# 3. Chart Eligibility Overview

The system supports **three chart types**, each with variants:

1. **Pie Chart**  
2. **Bar Chart**  
   - Simple bars  
   - Stacked bars  
3. **Stacked Area Chart**

# 4. Pie Charts

## 4.1 Pie Slices

Pie charts are intended to show the relative composition
of assignments. 
- The amount for each assignment determines
the size of each pie slice.  
- Minor levels are ignored

## 4.2 Time Periods

It is not possible to show time evolution with a pie chart.
If multiple period are present, separate charts are display
for each time period.

# 5. Bar Charts

Two types:

- **Simple Bar Chart** (no minor levels)  
- **Stacked Bar Chart** (minor level present)

Bar charts are **very flexible** and support:

- Mixed signs  
- Multi-year (clusters)  
- Multi-period (chart rows)  
- Multi-assignment  
- Minor assignments (stacking)

## 5.1 Axis Roles

### Bar axis:
- No axis labels per se
- Meaning of each bar is determined by ordering and labels
- The bar label always contains the assignment (e.g. Expense)
- The bar label **may** contain the period (e.g. Expense 2025 or Expense.Food 2025-01)
- Bar grouping is optimized in the source data for comparison (e.g. Bars)
with the same assignment and different years appear adjacent
to one another (e.g. Income 2025, Income 2026).
- When the duration is quarterly or monthly, the source
data is grouped by (Month/Quarter, Assignment, Year).

### Amount axis:
- Always vertical (y) for vertical bars 
- Always horizontal (x) for horizontal vars
- Zero is centered up/down (vertical) or left/right (horizontal) if mixed-sign

# 6. Stacked Area Charts

- Only rows for major level is processed; the minor level (if present) is ignored
- x-axis = chronological period(s)  
- y-axis = amount value (or absolute if negative-only)  
- Each distinct assignment value is a stacked layer
- Chart areas are rendered from the bottom up *i.e.* the first (largest) chart
row is rendered at the bottom and the next rows are layered on top.
- Default y-values are **integrals across time**, but raw series may be another mode  

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
- Stack-level labels (minor level)  
- Pie slice labels  

# 8. Ordering Rules

- Initial row order is computed for assignment data
- Computation of chart data from assignment data may do further
sorting by chart index (multiple charts) but will otherwise preserve
the ordering of source data
- Rendering will **never** change the sort order i.e. the order
of chart elements (bar, pie slice, area, etc.) is identical to
the order of rows in the chart data.

# End of README
