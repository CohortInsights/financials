## Example C: Multi year, quarterly, multi assignment, single sign

### Query

| Key | Value                  |
| --- |------------------------|
| Asn | Restaurant,Groceries   |
| Level | 3                      |
| Duration | &lt;Annual&gt;         |

### Source Data (Filtered Assignments)
| **Period** | **Assignment** | **Count** | **Amount** | **Level** |
| --- | --- | --- | --- | --- |
| 2024-Q1 | Expense.Food.Restaurant | 63  | \-\$3,308.33 | 3   |
| 2025-Q1 | Expense.Food.Restaurant | 41  | \-\$3,177.83 | 3   |
| 2024-Q1 | Expense.Food.Groceries | 44  | \-\$2,711.49 | 3   |
| 2025-Q1 | Expense.Food.Groceries | 51  | \-\$2,967.43 | 3   |
| 2024-Q2 | Expense.Food.Restaurant | 54  | \-\$3,139.13 | 3   |
| 2025-Q2 | Expense.Food.Restaurant | 55  | \-\$2,698.58 | 3   |
| 2024-Q2 | Expense.Food.Groceries | 53  | \-\$2,675.07 | 3   |
| 2025-Q2 | Expense.Food.Groceries | 44  | \-\$2,198.52 | 3   |
| 2024-Q3 | Expense.Food.Restaurant | 64  | \-\$2,564.28 | 3   |
| 2025-Q3 | Expense.Food.Restaurant | 67  | \-\$3,802.34 | 3   |
| 2024-Q3 | Expense.Food.Groceries | 47  | \-\$2,526.50 | 3   |
| 2025-Q3 | Expense.Food.Groceries | 49  | \-\$2,777.03 | 3   |
| 2024-Q4 | Expense.Food.Restaurant | 37  | \-\$1,808.48 | 3   |
| 2025-Q4 | Expense.Food.Restaurant | 50  | \-\$2,570.82 | 3   |
| 2024-Q4 | Expense.Food.Groceries | 47  | \-\$2,900.66 | 3   |
| 2025-Q4 | Expense.Food.Groceries | 52  | \-\$3,502.98 | 3   |

## Source Meta Data

| major level | 3            |
| --- |--------------|
| minor_level | &lt;none&gt; |
| major_asignment_count | 2            |
| sort_year_count | 2            |
| sort_period_count | 4            |
| sign | negative     |
| Min Frac | 0.05         |
| Common Prefix | Expense.Food |

## Pie Chart Representation

URL: _api/charts/data?chart=pie&asn=Restaurant,Groceries&level=3&year=2024,2025

**Chart Index:** In multi period pie charts, charts are indexed by Period

**Slice Color**: By Assignment across all charts

**Slice Labels**: Assignment only (**no** period)

**Merging**: None (no values below threshol)

### Pie Chart Data
| **Chart Index** | **Period** | **Title** | **Sum** | **Max** | **Threshold** |
| --- | --- | --- | --- | --- | --- |
| 1   | 2024-Q1 | asn=Restaurant,Groceries L3 2024-Q1 | 6020 | 3308 | 165 |
| 2   | 2025-Q1 | asn=Restaurant,Groceries L3 2025-Q1 | 6145 | 3178 | 159 |
| 3   | 2024-Q2 | asn=Restaurant,Groceries L3 2024-Q2 | 5814 | 3139 | 157 |
| 4   | 2025-Q2 | asn=Restaurant,Groceries L3 2025-Q2 | 4897 | 2699 | 135 |
| 5   | 2024-Q3 | asn=Restaurant,Groceries L3 2024-Q3 | 5091 | 2564 | 128 |
| 6   | 2025-Q3 | asn=Restaurant,Groceries L3 2025-Q3 | 6579 | 3802 | 190 |
| 7   | 2024-Q4 | asn=Restaurant,Groceries L3 2024-Q4 | 4709 | 2901 | 145 |
| 8   | 2025-Q4 | asn=Restaurant,Groceries L3 2025-Q4 | 6074 | 3503 | 175 |

## Pie Chart Element Data

| **Chart Index** | **Period** | **Pie Label** | **Slice Value** | **Color Index** |
| --- | --- | --- | --- | --- |
| 1   | 2024-Q1 | Restaurant | \$3,308.33 | 1   |
| 1   | 2024-Q1 | Groceries | \$2,711.49 | 2   |
| 2   | 2025-Q1 | Restaurant | \$3,177.83 | 1   |
| 2   | 2025-Q1 | Groceries | \$2,967.43 | 2   |
| 3   | 2024-Q2 | Restaurant | \$3,139.13 | 1   |
| 3   | 2024-Q2 | Groceries | \$2,675.07 | 2   |
| 4   | 2025-Q2 | Restaurant | \$2,698.58 | 1   |
| 4   | 2025-Q2 | Groceries | \$2,198.52 | 2   |
| 5   | 2024-Q3 | Restaurant | \$2,564.28 | 1   |
| 5   | 2024-Q3 | Groceries | \$2,526.50 | 2   |
| 6   | 2025-Q3 | Restaurant | \$3,802.34 | 1   |
| 6   | 2025-Q3 | Groceries | \$2,777.03 | 2   |
| 7   | 2024-Q4 | Restaurant | \$1,808.48 | 1   |
| 7   | 2024-Q4 | Groceries | \$2,900.66 | 2   |
| 8   | 2025-Q4 | Restaurant | \$2,570.82 | 1   |
| 8   | 2025-Q4 | Groceries | \$3,502.98 | 2   |

## Bar Chart Representation

URL: _api/charts/render?chart=bar&asn=Restaurant,Groceries&level=3&year=2024,2025

**Chart Index**: All bars are on the same chart.

**Bar Color**: By year (2024,2025)

**Bar Labels**: **Include** the period with assignment

**Merging**: None (all values above threshold)

**X-Axis Labels**: None

## Bar Chart Data

| **Chart Index** | **Title** | **Max** | **Threshold** |
| --- | --- | --- | --- |
| 1   | asn=Restaurant,Groceries L3 | 3308 | 165 |

## Bar Chart Element Data

| **Period** | **Bar Label** | **Bar Value** | **Color Index** |
| --- | --- | --- | --- |
| 2024-Q1 | Restaurant 2024-Q1 | \$3,308.33 | 1   |
| 2025-Q1 | Restaurant 2025-Q1 | \$3,177.83 | 2   |
| 2024-Q1 | Groceries 2024-Q1 | \$2,711.49 | 1   |
| 2025-Q1 | Groceries 2025-Q1 | \$2,967.43 | 2   |
| 2024-Q2 | Restaurant 2024-Q2 | \$3,139.13 | 1   |
| 2025-Q2 | Restaurant 2025-Q2 | \$2,698.58 | 2   |
| 2024-Q2 | Groceries 2024-Q2 | \$2,675.07 | 1   |
| 2025-Q2 | Groceries 2025-Q2 | \$2,198.52 | 2   |
| 2024-Q3 | Restaurant 2024-Q3 | \$2,564.28 | 1   |
| 2025-Q3 | Restaurant 2025-Q3 | \$3,802.34 | 2   |
| 2024-Q3 | Groceries 2024-Q3 | \$2,526.50 | 1   |
| 2025-Q3 | Groceries 2025-Q3 | \$2,777.03 | 2   |
| 2024-Q4 | Restaurant 2024-Q4 | \$1,808.48 | 1   |
| 2025-Q4 | Restaurant 2025-Q4 | \$2,570.82 | 2   |
| 2024-Q4 | Groceries 2024-Q4 | \$2,900.66 | 1   |
| 2025-Q4 | Groceries 2025-Q4 | \$3,502.98 | 2   |

## Stacked Area Chart Representation

URL: _api/charts/render?chart=area&asn=Restaurant,Groceries&level=3&year=2024,2025

**Chart Index**: All stacked areas are on the same chart.

**Area Labels**: Assignment only (**no** period)

**Area Vertical Ordering**: From bottom (Restaurant) to top (Groceries)

**Area Color**: By assignment

**Merging**: None (all values above threshold)

**Area X-Axis Ordering**: Chronological (by Period)

**X-Axis Labels**: Each period

## Stacked Area Chart Data

| **Chart Index** | **Title** | **Max** | **Threshold** |
| --- | --- | --- | --- |
| 1   | asn=Restaurant,Groceries L3 | 3308 | 165 |

## Stacked Area Chart Element Data

| **Chart Index** | **Period** | **Area Label** | **Area Value** | **Color Index** |
| --- | --- | --- | --- | --- |
| 1   | 2024-Q1 | Restaurant | \$3,308.33 | 1   |
| 1   | 2024-Q1 | Groceries | \$2,711.49 | 2   |
| 1   | 2024-Q2 | Restaurant | \$3,139.13 | 1   |
| 1   | 2024-Q2 | Groceries | \$2,675.07 | 2   |
| 1   | 2024-Q3 | Restaurant | \$2,564.28 | 1   |
| 1   | 2024-Q3 | Groceries | \$2,526.50 | 2   |
| 1   | 2024-Q4 | Restaurant | \$1,808.48 | 1   |
| 1   | 2024-Q4 | Groceries | \$2,900.66 | 2   |
| 1   | 2025-Q1 | Restaurant | \$3,177.83 | 1   |
| 1   | 2025-Q1 | Groceries | \$2,967.43 | 2   |
| 1   | 2025-Q2 | Restaurant | \$2,698.58 | 1   |
| 1   | 2025-Q2 | Groceries | \$2,198.52 | 2   |
| 1   | 2025-Q3 | Restaurant | \$3,802.34 | 1   |
| 1   | 2025-Q3 | Groceries | \$2,777.03 | 2   |
| 1   | 2025-Q4 | Restaurant | \$2,570.82 | 1   |
| 1   | 2025-Q4 | Groceries | \$3,502.98 | 2   |
