## Example B: Multi year, annual, multi assignment, single sign

### Query

| Asn | Food |
| --- | --- |
| Level | 3   |
| Duration | &lt;Annual&gt; |

### Source Data (Filtered Assignments)

| **Period** | **Assignment** | **Count** | **Amount** | **Level** |
| --- | --- | --- | --- | --- |
| 2024 | Expense.Food.Restaurant | 218 | \-\$10,820.22 | 3   |
| 2025 | Expense.Food.Restaurant | 213 | \-\$12,249.57 | 3   |
| 2024 | Expense.Food.Groceries | 191 | \-\$10,813.72 | 3   |
| 2025 | Expense.Food.Groceries | 196 | \-\$11,445.96 | 3   |
| 2024 | Expense.Food.Fast | 176 | \-\$2,154.41 | 3   |
| 2025 | Expense.Food.Fast | 147 | \-\$2,050.98 | 3   |
| 2024 | Expense.Food.Snack | 338 | \-\$1,576.57 | 3   |
| 2025 | Expense.Food.Snack | 311 | \-\$1,680.74 | 3   |
| 2024 | Expense.Food.Cafeteria | 53  | \-\$308.97 | 3   |
| 2025 | Expense.Food.Cafeteria | 77  | \-\$474.16 | 3   |
| 2024 | Expense.Food.Liquor | 2   | \-\$134.72 | 3   |
| 2025 | Expense.Food.Liquor | 4   | \-\$527.93 | 3   |
| 2024 | Expense.Food.Bakery | 6   | \-\$69.79 | 3   |
| 2025 | Expense.Food.Bakery | 6   | \-\$74.32 | 3   |
| 2025 | Expense.Food.Delivery | 1   | \-\$39.77 | 3   |

### Source Meta Data


| major level | 3           |
| --- |-------------|
| minor_level | &lt;none&gt; |
| major_asignment_count | 8           |
| sort_year_count | 2           |
| sort_period_count | 1           |
| sign | negative    |
| Min Frac | 0.05        |
| Common Prefix | Expense.Food |

## Pie Chart Representation

URL: _api/charts/data?chart=pie&asn=Food&level=3&year=2024,2025

**Chart Index:** In multi period pie charts, charts are indexed by Period

**Slice Color**: By Assignment across all charts

**Slice Labels**: Assignment only (**no** period)

**Merging**: All value within the same period below global threshold are merged into "Other &lt;Period&gt;"

### Pie Chart Data

| Chart Index | Chart Title                 | Sum | Absolute Sum | Max | Threshold
| --- |-----------------------------| --- | --- | --- | --- |
| 1   | asn=Food L3 2024 Sum $25878 | -25878 | 25878 | 10820 | 541
| 2   | asn=Food L3 2025 Sum $28543 | -28543 | 28543 | 12250 | 612

## Pie Chart Element Data

| **Chart Index** | **Period** | **Slice Label** | **Slice Color** | **Slice Value** | **Slice Percent** |
| --- | --- |-------| --- | --- | --- |
| 1   | 2024 | Restaurant | 1   | \$10,820.22 | 41.81% |
| 1   | 2024 | Groceries | 2   | \$10,813.72 | 41.79% |
| 1   | 2024 | Fast  | 3   | \$2,154.41 | 8.33% |
| 1   | 2024 | Snack | 4   | \$1,576.57 | 6.09% |
| 1   | 2024 | Other | 5   | \$513.48 | 1.98% |
| 2   | 2025 | Restaurant | 1   | \$12,249.57 | 42.92% |
| 2   | 2025 | Groceries | 2   | \$11,445.96 | 40.10% |
| 2   | 2025 | Fast  | 3   | \$2,050.98 | 7.19% |
| 2   | 2025 | Snack | 4   | \$1,680.74 | 5.89% |
| 2   | 2025 | Other | 5   | \$1,116.18 | 3.91% |

## Bar Chart Representation

URL: _api/charts/render?chart=bar&asn=Food&level=3&year=2024,2025

**Chart Index**: All bars are on the same chart.

**Bar Color**: By period (2024,2025)

**Bar Labels**: **Include** the period with assignment

**Merging**: All value within the same period below global threshold are merged into "Other &lt;Period&gt;"

**X-Axis Labels**: None

## Bar Chart Data

| Chart Index | Chart Title | Sum | Absolute Sum | Max | Threshold
| --- |-------------| --- | --- | --- | --- |
| 1 | asn=Food L3 | -54422 | 54442 | 12250 | 612

## Bar Chart Element Data

| **Chart Index** | **Period** | **Bar Label** | **Bar Color** | **Bar Value** |
| --- | --- | --- | --- | --- |
| 1   | 2024 | Restaurant 2024 | 1   | \$10,820.22 |
| 1   | 2025 | Restaurant 2025 | 2   | \$12,249.57 |
| 1   | 2024 | Groceries 2024 | 1   | \$10,813.72 |
| 1   | 2025 | Groceries 2025 | 2   | \$11,445.96 |
| 1   | 2024 | Fast 2024 | 1   | \$2,154.41 |
| 1   | 2025 | Fast 2025 | 2   | \$2,050.98 |
| 1   | 2024 | Snack 2024 | 1   | \$1,576.57 |
| 1   | 2025 | Snack 2025 | 2   | \$1,680.74 |
| 1   | 2024 | Other 2024 | 1   | \$513.48 |
| 1   | 2025 | Other 2025 | 2   | \$1,116.18 |

##

## Stacked Area Chart Representation

URL: _api/charts/render?chart=area&asn=Food&level=3&year=2024,2025

**Chart Index**: All bars are on the same chart.

**Area Labels**: Assignment only (**no** period)

**Area Ordering**: From bottom (Restaurant) to top (Other)

**Area Color**: By assignment

**Merging**: All value within the same period below global threshold are merged into "Other"

**X-Axis Labels**: Each period

## Stacked Area Chart Data

| Chart Index | Chart Title | Sum | Absolute Sum | Max | Threshold
| --- |-------------| --- | --- | --- | --- |
| 1 | asn=Food L3 | -54422 | 54442 | 12250 | 612

## Stacked Area Chart Element Data

| **Chart Index** | **X-Axis Label** | **Area Label** | **Area Color** | **Area Value** |
| --- |------------------| --- | --- | --- |
| 1   | 2024             | Restaurant | 1   | \$10,820.22 |
| 1   | 2024             | Groceries | 2   | \$10,813.72 |
| 1   | 2024             | Fast | 3   | \$2,154.41 |
| 1   | 2024             | Snack | 4   | \$1,576.57 |
| 1   | 2024             | Other | 5   | \$513.48 |
| 1   | 2025             | Restaurant | 1   | \$12,249.57 |
| 1   | 2025             | Groceries | 2   | \$11,445.96 |
| 1   | 2025             | Fast | 3   | \$2,050.98 |
| 1   | 2025             | Snack | 4   | \$1,680.74 |
| 1   | 2025             | Other | 5   | \$1,116.18 |