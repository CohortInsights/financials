from pandas import DataFrame, Series, factorize, concat

from financials.chart.chart_common import ChartConfigError, get_common_prefix

global_chart_types: dict = {
    "pie": "Compare relative percentages of assignments for a single or multiple data periods",
    "bar": "Simple and stacked bar charts of assignment amounts over single or multiple data periods",
    "stacked_area": "evolution of assignment amounts over time, with areas stacked on top of each other to show both individual trends and the total, cumulative trend"
}

bar_element_size = 30   # Thickness of any bar in a bar chart
area_element_size = 20 # Number of areas * this number equals height of stacked area plot
pie_slice_size = 50     # Number of slices * this number equals size of square pie area
min_frame_size = 750  # No dimension should be shorter than this size


def get_char_types() -> dict:
    """
    Get chart types dictionary
   :returns a dictionary of definitions keyed by char_type
    """
    return global_chart_types

def add_row_indexes(chart_data: DataFrame) -> DataFrame:
    # Insert at first column position a 1-based row id
    chart_data.insert(0, "row_id", range(1, len(chart_data) + 1))
    return chart_data

def add_chart_indexes(chart_data: DataFrame, chart_type: str) -> DataFrame:
    """
    Adds the column that encodes a column named "chart_index" (1-n) for each intended chart instance
    :param chart_data: Filtered assignment data
    :return: The input data after adding the 'chart_index' column
    """
    # Default is that all elements belong to the same chart
    split_columns = []
    sort_keys = ["chart_index","period"]

    # Area plot one level at a time chronologically across periods
    if "bar" in chart_type:
        level_count = chart_data["level"].nunique()
        if level_count > 2:
            # We cannot use segments for more than 2 levels
            # Just create separate bar charts if there are more than 2 levels (rare)
            split_columns = ["level"]
    elif "area" in chart_type:
        split_columns = ["level"]
    # Pie charts plot one level and period at a time
    elif "pie" in chart_type:
        split_columns = ["level", "period"]

    column_name = "chart_index"

    if split_columns:
        # Validate required columns
        for key in split_columns:
            if key not in chart_data.columns:
                raise ChartConfigError(
                    f"Chart type requires '{key}' column but it is missing"
                )

        # Initialize column
        chart_data[column_name] = 0

        chart_index = 1

        # IMPORTANT: sort=False to avoid implicit reordering
        groups = chart_data.groupby(split_columns, sort=False).groups

        for _, idx in groups.items():
            chart_data.loc[idx, column_name] = chart_index
            chart_index += 1

        # Stable sort according to sort_keys
        # Preserve original order *within* each chart
        chart_data.sort_values(
            by=sort_keys,
            kind="stable",
            inplace=True
        )

    else:
        # Single chart instance and don't change sorting
        chart_data[column_name] = 1

    return chart_data


def add_cluster_index_columns(chart_data: DataFrame, cluster_cols : list[str]):
    """
    Adds <cluster_col>_index columns (dense appearance-order rank)
    per chart_index group.
    """

    def add_cluster_index(parent_df: DataFrame, sub_df: DataFrame, cluster_col: str):
        values = sub_df[cluster_col]
        rank_map = {v: i for i, v in enumerate(values.drop_duplicates())}
        parent_df.loc[sub_df.index, f"{cluster_col}_index"] = values.map(rank_map)

    for _, sub_df in chart_data.groupby(by=["chart_index"], sort=False):
        for col in cluster_cols:
            add_cluster_index(chart_data, sub_df, col)

    return chart_data


def add_element_pos_column(chart_data: DataFrame, cluster_columns: list[str]):
    """
    Computes elem_pos using base row spacing and optional cluster offsets.
    """
    # Initialize spacing
    chart_data["elem_pos"] = (
        chart_data
        .groupby("chart_index", sort=False)
        .cumcount()
    )

    for col in cluster_columns:
        col_index = col + '_index'
        for index, sub_df in chart_data.groupby(by=['chart_index'], sort=False):
            s = sub_df[col_index]
            changes = (s != s.shift()).astype(int)
            n_unique = changes.nunique()
            if n_unique > 1:
                changes.iloc[0] = 0  # No change at first element
                cumulative_shift = changes.cumsum()
                chart_data.loc[sub_df.index,'elem_pos'] += cumulative_shift

    return chart_data


def add_time_pos_column(chart_data: DataFrame, chart_type : str):
    """
    Adds an index 0,1,2 that encodes the chronological time sequence. Accounts for time gaps between adjacent periods
    :param chart_data: Assignment data containing "sort_year" and "sort_period" columns
    :param chart_type:
    :return: DataFrame populated with the "time_pos" column
    """
    # Initialize to integer
    sort_years = chart_data["sort_year"].values
    sort_periods = chart_data["sort_period"]
    if sort_periods.min() == 1:
        sort_periods = sort_periods - 1

    start_year = sort_years.min()
    count_values = sort_periods.nunique()

    chart_data['time_pos'] = (sort_years - start_year) * count_values + sort_periods

    return chart_data

def add_values_column(chart_data: DataFrame, chart_type: str, cfg: dict) -> DataFrame:
    """
    Compute a "values" column derived from the "amount"  and stats columns.

    Policy for handling negative values depends on chart type:
    - Bar charts support mixed-sign data, so values are passed through unchanged
      *if there exists at least one positive value above threshold*.
    - Pie and stacked-area charts do NOT support mixed-sign data. For these charts,
      negative values must be handled by converting to all same-sign data.
    - If all values are negative (or no positive value exceeds threshold),
      values are converted to absolute magnitude.

    :param chart_data: Assignment data containing "amount" and "threshold" columns
    :param chart_type: String denoting the type of chart
    :param cfg: Chart configuration dictionary (currently unused)
    :return: DataFrame with added "values" column
    """
    # Bar charts can represent mixed positive and negative values directly
    support_mixed_sign = "bar" in chart_type

    # Extract raw values and ignore flags
    values = chart_data["amount"].values
    abs_values = abs(values)

    # Determine sign presence using ignore-aware logic
    if 'ignore' in chart_data:
        ignore = chart_data["ignore"].values
        has_relevant_positive = ((values > 0) & (ignore == 0)).any()
    else:
        has_relevant_positive = (values > 0).any()
    has_negative = (values < 0).any()

    # Apply sign normalization rules
    if has_negative:
        if not has_relevant_positive or not support_mixed_sign:
            values = abs_values

    # Assign computed values column
    chart_data["values"] = values
    max_abs_value = abs_values.max()
    # Need a scaled down version of values if they exceed 10,000
    if ( max_abs_value ) >= 1000:
        scaled_values = 0.001*values
        chart_data["scaled_values"] = scaled_values.round(3)
        if max_abs_value >= 10000:
            chart_data["scaled_values"] = scaled_values.round(2)

    return chart_data


def add_ignore_column(chart_data: DataFrame, chart_type: str) -> DataFrame:
    """
    Mark rows whose label is insignificant across ALL charts.

    Rules:
    - A label is ignored (ignore = 1) ONLY IF it is below threshold in every group
    - If a label exceeds threshold in ANY group, it is kept everywhere

    Grouping is performed by (label, level) to respect chart semantics.
    """

    # Per-row significance
    abs_values = chart_data["amount"].abs()
    chart_data['ignore'] = (abs_values < chart_data["threshold"]).astype(int)

    return chart_data


def drop_asn_rows_with_ignore(chart_data: DataFrame) -> DataFrame:
    """
    Drop all rows linked to an assignment where any row has ignore == 1
    """
    bad_assignments = (
        chart_data
        .groupby("assignment")["ignore"]
        .max()
        .loc[lambda s: s == 1]
        .index
    )
    return chart_data[~chart_data["assignment"].isin(bad_assignments)]


def merge_ignore_rows_into_other(chart_data: DataFrame, chart_type: str) -> DataFrame:
    """
    Merge rows marked ignore=1 into an 'Other' row per (chart_index, level).

    Strategy:
    - Accumulate values/counts from ignored rows
    - Reuse an existing 'Other' row if present
    - Otherwise repurpose the first ignored row as 'Other'
    - Recompute percent as values / mag
    - Finally drop all remaining ignore==1 rows
    """
    for (chart_index, level), idx in chart_data.groupby(
        ["chart_index", "level"], sort=False
    ).groups.items():

        group = chart_data.loc[idx]
        ignored = group[group["ignore"] == 1]

        if ignored.empty:
            continue

        sum_values = round(ignored["values"].sum(), 2)
        sum_count = ignored["count"].sum()

        if sum_values == 0 and sum_count == 0:
            continue

        # Case 1: existing "Other"
        other_rows = group[(group["label"] == "Other") & (group["ignore"] == 0)]

        if not other_rows.empty:
            other_idx = other_rows.index[0]
            mag = chart_data.loc[other_idx, "mag"]

            chart_data.loc[other_idx, "values"] += sum_values
            chart_data.loc[other_idx, "count"] += sum_count
            chart_data.loc[other_idx, "percent"] = (
                round(100.0 * chart_data.loc[other_idx, "values"] / mag, 1)
            )

        else:
            # Case 2: repurpose first ignored row (DataFrame order)
            first_ignored_idx = ignored.index[0]
            mag = chart_data.loc[first_ignored_idx, "mag"]
            percent = 100.0 * sum_values / mag
            percent = round(percent, 1)

            chart_data.loc[first_ignored_idx, "label"] = "Other"
            chart_data.loc[first_ignored_idx, "values"] = sum_values
            chart_data.loc[first_ignored_idx, "count"] = sum_count
            chart_data.loc[first_ignored_idx, "percent"] = percent
            chart_data.loc[first_ignored_idx, "ignore"] = 0

    # Final cleanup: drop any remaining ignored rows
    chart_data.drop(chart_data[chart_data["ignore"] == 1].index, inplace=True)
    chart_data.drop(chart_data[chart_data["percent"] < 1.0].index, inplace=True)
    chart_data.drop(columns=["ignore"], inplace=True)

    return chart_data


def add_label_column(chart_data : DataFrame, chart_type : str) -> DataFrame:
    full_labels = chart_data["assignment"]
    label = full_labels.str.rsplit(".", n=1).str[-1]
    chart_data['label'] = label
    return chart_data

def add_parent_column(chart_data: DataFrame, chart_type: str) -> DataFrame:
    # Only bar charts have a parent column
    if "bar" not in chart_type:
        return chart_data

    # Build lookup: (period, assignment) -> row_id
    lookup = {
        (row.period, row.assignment): row.row_id
        for row in chart_data.itertuples(index=False)
    }

    def resolve_parent(row):
        asn = row.assignment
        if "." not in asn:
            return None

        parent_asn = asn.rsplit(".", 1)[0]
        return lookup.get((row.period, parent_asn))

    chart_data["parent"] = (chart_data.apply(resolve_parent, axis=1)).astype("Int64")
    return chart_data


def add_stats_columns(chart_data: DataFrame, chart_type: str, cfg: dict) -> DataFrame:
    min_frac = cfg.get("min_frac", 0)

    # Initialize columns
    for name in ("mag", "percent", "threshold"):
        chart_data[name] = 0.0

    for (_, _, _), idx in chart_data.groupby(
        ["chart_index", "level", "period"], sort=False
    ).groups.items():

        values = chart_data.loc[idx, "amount"]
        abs_values = values.abs()

        sum = abs_values.sum()
        mag = abs_values.max()
        threshold = mag * min_frac

        if mag > 0:
            percent = (abs_values * 100.0 / sum).round(1)
        else:
            percent = Series(0.0, index=abs_values.index)

        # Assign stats to rows in this group
        chart_data.loc[idx, "mag"] = round(mag, 2)
        chart_data.loc[idx, "percent"] = percent
        chart_data.loc[idx, "threshold"] = round(threshold, 2)

    return chart_data

from pandas import factorize
import pandas as pd

def add_color_column(chart_data: DataFrame, chart_type: str, cfg: dict) -> DataFrame:
    """
    Assign a color index column to each chart element.
    - Same key (typically label) => same color index
    - Indices assigned in order of first encounter in the DataFrame
    """
    color_keys = ["label"]
    chart_data["color"] = 0

    # Build a single key per row (tuple when multiple keys)
    if len(color_keys) == 1:
        keys = chart_data[color_keys[0]]
    else:
        keys = chart_data[color_keys].astype(object).apply(tuple, axis=1)

    # factorize preserves first-seen order by default (sort=False)
    chart_data["color"] = (pd.factorize(keys, sort=False)[0] + 1).astype(int)

    return chart_data


def add_frame_dimensions(fig_data : DataFrame, chart_elements : DataFrame, chart_type : str) -> DataFrame:
    orientations = None
    fig_indexes = fig_data['fig_index'].values
    n_elements_array = fig_data['n_elements'].values
    if 'bar' in chart_type:
        orientations = fig_data['orientation'].values

    frame_width_list = []
    frame_height_list = []

    for index in fig_indexes:
        idx = index - 1 # Needed for array indexing
        frame_width, frame_height = (0,0)
        n_elements = n_elements_array[idx]
        elem_plot_size = n_elements * bar_element_size
        elem_plot_size = max(elem_plot_size, min_frame_size)
        # elem_plot_size = max(size1, min_frame_size)
        if 'area' in chart_type:
            frame_height = n_elements * area_element_size
            frame_width = max(min_frame_size, 0.7*frame_height)
        elif 'bar' in chart_type:
            orient = orientations[idx]
            if orient == "horizontal":
                frame_height = elem_plot_size
                frame_width = min_frame_size
            elif orient == "vertical":
                frame_width = elem_plot_size
                frame_height = min_frame_size
        elif 'pie' in chart_type:
            frame_width = n_elements * pie_slice_size
            frame_height = frame_width
        frame_width_list.append(frame_width)
        frame_height_list.append(frame_height)
    fig_data['frame_width'] = frame_width_list
    fig_data['frame_height'] = frame_height_list

    # Apply min_frame_size constraint to both dimensions
    fig_data['frame_width'] = fig_data['frame_width'].clip(lower=min_frame_size)
    fig_data['frame_height'] = fig_data['frame_height'].clip(lower=min_frame_size)

    fig_data['dpi'] = 150
    return fig_data


def add_fig_title_axes(fig_data : DataFrame, elements : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    c = 'fig_index'
    fig_indexes = fig_data[c].values
    titles = []
    duration_list = []
    time_point_list = []
    element_count_list = []
    orientation_list = []
    grid_period_list, grid_year_list = [], []
    segmented_list = []
    start_year = elements['sort_year'].min()
    max_value = elements['values'].max()

    for index in fig_indexes:
        index_elements = elements[elements['chart_index'] == index]
        period = index_elements["period"].values
        years = index_elements["sort_year"].values
        start_period = index_elements['sort_period'].values.min()
        y1,y2 = years.min(), years.max()
        p1,p2 = period.min(), period.max()
        t = get_common_prefix(elements['assignment'])
        duration = 'Annually'
        n_periods = 1
        segmented = False
        orientation = "vertical"

        if '-' in p1:
            duration = 'Monthly'
            n_periods = 12
            if 'Q' in p1:
                duration = 'Quarterly'
                n_periods = 4
        if y1 == y2:
            if p1 == p2:
                t += f" {p1}"
            else:
                t += f" {y1} {duration}"
        else:
            t += f" {y1}-{y2} {duration}"

        grid_year_list.append(y1 - start_year)
        grid_period_list.append((start_period-1) % n_periods)
        duration_list.append(duration)
        time_point_list.append((y2-y1+1)*n_periods)
        element_count_list.append(len(index_elements))
        if "bar" in chart_type:
            if 'parent' in index_elements:
                segmented = (
                        "parent" in index_elements.columns
                        and (index_elements["parent"] > 0).any()
                )
            orientation = "horizontal"
        segmented_list.append(segmented)
        orientation_list.append(orientation)
        titles.append(t)

    fig_data['title'] = titles
    fig_data['time_col'] = "period"
    fig_data['currency_col'] = "values"
    fig_data['currency_unit'] = "dollars"
    fig_data['currency_format'] = '${x:,.0f}'
    if 'scaled_values' in elements.columns:
        fig_data['currency_col'] = "scaled_values"
        fig_data['currency_unit'] = "dollars_thousands"
        if max_value >= 10000:
            fig_data['currency_format'] = '${x:,.0f}K'
        else:
            fig_data['currency_format'] = '${x:,.1f}K'
    orientation = orientation_list[0]
    if orientation == "horizontal":
        fig_data['x_axis'] = "currency"
        fig_data['y_axis'] = "time"
    else:
        fig_data['x_axis'] = "time"
        fig_data['y_axis'] = "currency"
    if "pie" in chart_type:
        fig_data['currency_col'] = "percent"
        fig_data['currency_unit'] = "percent"
        fig_data['currency_format'] = "%"
    fig_data['time_frequency'] = duration_list
    fig_data['n_time_points'] = time_point_list
    fig_data['n_elements'] = element_count_list
    fig_data["segments"] = segmented_list
    fig_data['orientation'] = orientation_list
    if 'pie' in chart_type:
        fig_data['grid_year'] = grid_year_list
        fig_data['grid_period'] = grid_period_list
    return fig_data


def compute_figure_data(chart_elements : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    fig_indexes = chart_elements["chart_index"].unique().tolist()
    fig_data = { 'fig_index' : fig_indexes }
    fig_df = DataFrame(data=fig_data)
    fig_df["chart_type"] = chart_type
    add_fig_title_axes(fig_df, chart_elements, chart_type, cfg)
    add_frame_dimensions(fig_df, chart_elements, chart_type)
    return fig_df

def remove_missing_area_assignments(chart_data: pd.DataFrame) -> pd.DataFrame:
    """
    Remove assignments that do not appear across all time_pos
    within each chart_index.

    - Preserves original row order
    - No sorting
    - Operates per chart_index
    """

    output_frames = []

    for chart_index, df in chart_data.groupby("chart_index", sort=False):

        # Authoritative time set
        time_positions = df["time_pos"].drop_duplicates()
        n_time_points = len(time_positions)

        # Count time occurrences per assignment
        counts = (
            df.groupby("assignment", sort=False)["time_pos"]
              .nunique()
        )

        # Keep only assignments that appear in all time points
        valid_assignments = counts[counts == n_time_points].index

        filtered_df = df[df["assignment"].isin(valid_assignments)]

        output_frames.append(filtered_df)

    return pd.concat(output_frames, ignore_index=True)


def fill_missing_assignments(chart_data: DataFrame) -> DataFrame:

    output_frames = []

    for _, sub_df in chart_data.groupby(["level"], sort=False):

        # --- Unique grid axes ---
        assignments = sub_df["assignment"].drop_duplicates()
        time_points = (
            sub_df[["sort_year", "sort_period", "period"]]
            .drop_duplicates()
        )

        # Build Cartesian product
        full_index = (
            time_points
            .assign(key=1)
            .merge(
                assignments.to_frame(name="assignment").assign(key=1),
                on="key",
            )
            .drop("key", axis=1)
        )

        # Merge existing data onto full grid
        merged = full_index.merge(
            sub_df,
            on=["assignment", "sort_year", "sort_period", "period"],
            how="left",
            suffixes=("", "_orig"),
        )

        # Fill numeric columns
        for col in ["count", "amount"]:
            if col in merged.columns:
                merged[col] = merged[col].fillna(0)

        output_frames.append(merged)

    return pd.concat(output_frames, ignore_index=True)


def compute_chart_elements(source_data : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    """
    Computes chart elements consistent with the specified assignment source data and chart_type

    :param source_data: Filtered assignment data that is authoritative input
    :param chart_type: String denoting the type of chart
    :param cfg: Dictionary of confi parameters
    :param render: Whether to return chart data stripped to values relevant only to rendering
    :return:
    """
    # Chart data starts as copy of input data
    chart_data = source_data.copy()
    if 'bar' in chart_type:
        chart_data = fill_missing_assignments(chart_data)
    # Add enriched chart data one column at a time
    # ----- Begin Adding Element Columns
    add_row_indexes(chart_data)
    add_chart_indexes(chart_data,chart_type)
    add_time_pos_column(chart_data, cfg)
    add_label_column(chart_data,chart_type)
    add_parent_column(chart_data, chart_type)
    add_stats_columns(chart_data, chart_type, cfg)
    add_ignore_column(chart_data, cfg)
    add_values_column(chart_data, chart_type, cfg)
    if 'pie' in chart_type:
        merge_ignore_rows_into_other(chart_data, cfg)
    if 'area' in chart_type:
        chart_data = remove_missing_area_assignments(chart_data)
    if 'bar' in chart_type:
        cluster_cols = ['sort_year', 'assignment', 'sort_period']
        add_cluster_index_columns(chart_data, cluster_cols)
        chart_data.sort_values(by=["sort_period","assignment_index","sort_year"], inplace=True)
        add_element_pos_column(chart_data, ['assignment','sort_period'])
    add_color_column(chart_data, chart_type, cfg)
    # ----- End Adding Element Columns
    return chart_data