## Example A: Single year, annual, multi assignment, single sign

### Query

| Asn | Expense |
| --- | --- |
| Level | 2   |
| Duration | &lt;Annual&gt; |

### 

Source Data (Filtered Assignments)

| **Period** | **Assignment** | **Amount** | **Level** |
| --- | --- | --- | --- |
| 2025 | Expense.Tax | \-\$32,764.84 | 2   |
| 2025 | Expense.Food | \-\$28,543.43 | 2   |
| 2025 | [Expense.Travel](http://expense.travel) | \-\$27,308.36 | 2   |
| 2025 | Expense.Merchandise | \-\$19,225.61 | 2   |
| 2025 | Expense.Auto | \-\$16,630.59 | 2   |
| 2025 | Expense.Home | \-\$13,865.96 | 2   |
| 2025 | Expense.Utility | \-\$10,303.64 | 2   |
| 2025 | Expense.Entertainment | \-\$9,054.44 | 2   |
| 2025 | Expense.Services | \-\$7,102.75 | 2   |
| 2025 | Expense.PetCare | \-\$3,839.38 | 2   |
| 2025 | Expense.Subscription | \-\$3,551.63 | 2   |
| 2025 | Expense.Gift | \-\$2,732.56 | 2   |
| 2025 | Expense.Cash | \-\$820.00 | 2   |
| 2025 | Expense.Other | \-\$650.37 | 2   |
| 2025 | Expense.Unspecified | \-\$430.56 | 2   |
| 2025 | Expense.Health | \-\$321.69 | 2   |
| 2025 | Expense.Interest | \-\$163.32 | 2   |
| 2025 | Expense.Parking | \-\$5.00 | 2   |

### Source Meta Data

| major level | 2   |
| --- | --- |
| minor_level | &lt;none&gt; |
| major_asignment_count | 18  |
| sort_year_count | 1   |
| sort_period_count | 1   |
| sign | negative |
| Min Frac | 0.05 |
| Common prefix | Expense. |

**Chart Row Sequence:** Input order of chart data is authoritative. Renderer must preserve the sequence of chart elements (pie slices, bars, areas, etc.).

**Chart Sign Handling:** For single-sign negative datasets, all chart values are emitted as absolute magnitudes. Renderer must not apply sign inversion.

**Chart Row Merging**: All values < threshold are removed and merged into "Other". Threshold is the product of the min_fraction and max_value.

**Color Handling:** Chart data provides the complete color specification, including the palette and per-element color identity. The renderer must render colors exactly as provided and must not derive, remap, or substitute colors.

## Pie Chart Representation

URL: _api/charts/data?chart=pie&asn=Expense&level=2&year=2025_

**Chart Cardinality**: For this single period case, there is a single chart (index)

**Slice Percent**: Rendering should use Slice Percent column data and not re-compute it. Percent is computed from the sum of all values with the same chart index.

**Color by Assignment**: Each pie slice has a different color

**Color Palette**: 16 color palette is provided to the renderer. Color is derived from color index and palette.

### Pie Chart Data
| Chart Index | Chart Title | Sum | Absolute Sum | Max | Threshold
| --- |-------------| --- | --- | --- | --- |
| 1   | asn=Expense L2 2025 Sum $177314 | -177314.13 | 177314.13 | 32764.84 | 1638.42

### Pie Chart Element Data
| **Chart Index** | **Period** | **Slice Label** | **Slice Color** | **Slice Value** | **Slice Percent** | **Comment** |
| --- | --- | --- | --- | --- | --- | --- |
| 1   | 2025 | Tax | 1   | 32764.84 | 18.48% |     |
| 1   | 2025 | Food | 2   | 28543.43 | 16.10% |     |
| 1   | 2025 | [Travel](http://expense.travel) | 3   | 27308.36 | 15.40% |     |
| 1   | 2025 | Merchandise | 4   | 19225.61 | 10.84% |     |
| 1   | 2025 | Auto | 5   | 16630.59 | 9.38% |     |
| 1   | 2025 | Home | 6   | 13865.96 | 7.82% |     |
| 1   | 2025 | Utility | 7   | 10303.64 | 5.81% |     |
| 1   | 2025 | Entertainment | 8   | 9054.44 | 5.11% |     |
| 1   | 2025 | Services | 9   | 7102.75 | 4.01% |     |
| 1   | 2025 | PetCare | 10  | 3839.38 | 2.17% |     |
| 1   | 2025 | Subscription | 11  | 3551.63 | 2.00% |     |
| 1   | 2025 | Gift | 12  | 2732.56 | 1.54% |     |
| 1   | 2025 | Other | 13  | 2390.94 | 1.35% | Sum of all values < threshold |
|     | 2025 | Cash |     | 820 |     | Merged into Other |
|     | 2025 | Other |     | 650.37 |     | Merged into Other |
|     | 2025 | Unspecified |     | 430.56 |     | Merged into Other |
|     | 2025 | Health |     | 321.69 |     | Merged into Other |
|     | 2025 | Interest |     | 163.32 |     | Merged into Other |
|     | 2025 | Parking |     | 5   |     | Merged into Other |

## Bar Chart Representation

URL: _api/charts/render?chart=bar&asn=Expense&level=2&year=2025_

<br/>**Chart Cardinality**: Bar chart always has a single chart index

**Color**: 4 color palette is provided to the renderer. Color is derived from color index and palette. For this case, there is only a single bar color.

**A-Axis Labels** : None

### Bar Chart Data   

| Chart Index | Chart Title         | Sum | Absolute Sum | Max | Threshold
| --- |---------------------| --- | --- | --- | --- |
| 1   | asn=Expense L2 2025 | -177314.13 | 177314.13 | 32764.84 | 1638.42

### Bar Chart Element Data  

| **Chart Index** | **Period** | **Bar Label** | **Bar Color** | **Bar Value** | **Comment** |
| --- | --- | --- | --- | --- | --- |
| 1   | 2025 | Tax | 1   | 32764.84 |     |
| 1   | 2025 | Food | 1   | 28543.43 |     |
| 1   | 2025 | Travel | 1   | 27308.36 |     |
| 1   | 2025 | Merchandise | 1   | 19225.61 |     |
| 1   | 2025 | Auto | 1   | 16630.59 |     |
| 1   | 2025 | Home | 1   | 13865.96 |     |
| 1   | 2025 | Utility | 1   | 10303.64 |     |
| 1   | 2025 | Entertainment | 1   | 9054.44 |     |
| 1   | 2025 | Services | 1   | 7102.75 |     |
| 1   | 2025 | PetCare | 1   | 3839.38 |     |
| 1   | 2025 | Subscription | 1   | 3551.63 |     |
| 1   | 2025 | Gift | 1   | 2732.56 |     |
| 1   | 2025 | Other | 1   | 2390.94 | Sum of all values < threshold |

## Stacked Area Chart Representation

URL: _api/charts/render?chart=area&asn=Expense&level=2&year=2025_

<br/>**Chart Cardinality**: Stacked area chart always has a single chart index

**Color by Assignment**: Each stacked area has a different color

**A-Axis Labels** : One for single period (2025)

**Color Palette**: 16 color palette is provided to the renderer. Color is derived from color index and palette.

### Stacked Area Chart Data  

| Chart Index | Chart Title         | Sum | Absolute Sum | Max | Threshold
| --- |---------------------| --- | --- | --- | --- |
| 1   | asn=Expense L2 2025 | -177314.13 | 177314.13 | 32764.84 | 1638.42

### Stacked Area Chart Element Data 

| **Chart Index** | **Period** | **Area Label** | **Area Color** | **Area Value** | **Comment** |
| --- | --- | --- | --- | --- | --- |
| 1   | 2025 | Tax | 1   | 32764.84 |     |
| 1   | 2025 | Food | 2   | 28543.43 |     |
| 1   | 2025 | Travel | 3   | 27308.36 |     |
| 1   | 2025 | Merchandise | 4   | 19225.61 |     |
| 1   | 2025 | Auto | 5   | 16630.59 |     |
| 1   | 2025 | Home | 6   | 13865.96 |     |
| 1   | 2025 | Utility | 7   | 10303.64 |     |
| 1   | 2025 | Entertainment | 8   | 9054.44 |     |
| 1   | 2025 | Services | 9   | 7102.75 |     |
| 1   | 2025 | PetCare | 10  | 3839.38 |     |
| 1   | 2025 | Subscription | 11  | 3551.63 |     |
| 1   | 2025 | Gift | 12  | 2732.56 |     |
| 1   | 2025 | Other | 13  | 2390.94 | Sum of all values < threshold |