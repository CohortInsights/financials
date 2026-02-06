from pandas import DataFrame, Series, factorize, concat

from financials.chart.chart_common import ChartConfigError

global_chart_types: dict = {
    "pie": "Compare relative percentages of assignments for a single or multiple data periods",
    "bar": "Simple and stacked bar charts of assignment amounts over single or multiple data periods",
    "stacked_area": "evolution of assignment amounts over time, with areas stacked on top of each other to show both individual trends and the total, cumulative trend"
}


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


def add_cluster_indexes(chart_data: DataFrame, chart_type: str) -> DataFrame:
    """
    Adds the column that encodes a "cluster" of values used when rendering a chart type
    :param chart_data: Filtered assignment data
    :return: The input data after adding the 'cluster' column
    """
    # By default we cluster elements within the same time chart and time period
    group_columns = ["chart_index","period"]
    # In bar charts we compare bars of the same assignment by clustering them across periods
    if "bar" in chart_type:
        group_columns = ["chart_index","assignment"]

    # Initialize column
    column_name = "cluster"
    chart_data[column_name] = 0

    # Aassign cluster id based on first encountered groups
    keys = chart_data[group_columns].apply(tuple, axis=1)
    chart_data["cluster"] = factorize(keys)[0] + 1

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
    ignore = chart_data["ignore"].values

    # Determine sign presence using ignore-aware logic
    has_relevant_positive = ((values > 0) & (ignore == 0)).any()
    has_negative = (values < 0).any()

    # Apply sign normalization rules
    if has_negative:
        if not has_relevant_positive or not support_mixed_sign:
            values = abs_values

    # Assign computed values column
    chart_data["values"] = values
    max_abs_value = abs_values.max()
    # Need a scaled down version of values if they exceed 10,000
    if ( max_abs_value ) >= 10000:
        scaled_values = 0.001*values
        chart_data["scaled_values"] = scaled_values.round(2)

    return chart_data


def add_ignore_column(chart_data: DataFrame, chart_type: str) -> DataFrame:
    """
    Mark rows whose absolute value falls below their threshold.

    Adds a column:
    - ignore = 1 if abs(values) < threshold
    - ignore = 0 otherwise

    Grouping is performed by (chart_index, level) to respect chart semantics.
    """
    # Initialize column to default (not dropped)
    chart_data["ignore"] = 0

    for (_, _), idx in chart_data.groupby(
        ["chart_index", "level"], sort=False
    ).groups.items():

        values = chart_data.loc[idx, "amount"]
        thresh = chart_data.loc[idx, "threshold"]

        abs_values = values.abs()

        # Mark rows below threshold
        chart_data.loc[idx, "ignore"] = (abs_values < thresh).astype(int)

    return chart_data


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

    chart_data["parent"] = chart_data.apply(resolve_parent, axis=1)
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

        mag = abs_values.sum()
        max_val = abs_values.max()
        threshold = mag * min_frac

        if mag > 0:
            percent = (abs_values * 100.0 / mag).round(1)
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

    if "bar" in chart_type:
        n_years = chart_data["sort_year"].nunique()
        if n_years > 1:
            color_keys = ["sort_year"]

    # Build a single key per row (tuple when multiple keys)
    if len(color_keys) == 1:
        keys = chart_data[color_keys[0]]
    else:
        keys = chart_data[color_keys].astype(object).apply(tuple, axis=1)

    # factorize preserves first-seen order by default (sort=False)
    chart_data["color"] = (pd.factorize(keys, sort=False)[0] + 1).astype(int)

    return chart_data


def add_frame_dimensions(fig_data : DataFrame, chart_type : str) -> DataFrame:
    orientations = None
    fig_indexes = fig_data['fig_index'].values
    n_elements_array = fig_data['n_elements'].values
    n_time_points_array = fig_data['n_time_points'].values
    if 'bar' in chart_type:
        orientations = fig_data['element_orientation'].values

    frame_width_list = []
    frame_height_list = []

    bar_element_size = 25
    area_element_size = 300
    pie_slice_size = 75
    fixed_frame_size = 750

    n_frames = len(fig_data)
    for index in fig_indexes:
        idx = index - 1 # Needed for array indexing
        frame_width, frame_height = (0,0)
        n_elements = n_elements_array[idx]
        n_time_points = n_time_points_array[idx]
        if 'area' in chart_type:
            frame_width = fixed_frame_size
            frame_height = n_elements * area_element_size
        elif 'bar' in chart_type:
            orient = orientations[idx]
            if orient == "horizontal":
                frame_height = n_elements * bar_element_size
                frame_width = fixed_frame_size
            elif orient == "vertical":
                frame_height = n_frames * fixed_frame_size
                frame_width = n_elements * bar_element_size
        elif 'pie' in chart_type:
            frame_width = n_elements * pie_slice_size
            frame_height = frame_width
        frame_width_list.append(frame_width)
        frame_height_list.append(frame_height)
    fig_data['frame_width'] = frame_width_list
    fig_data['frame_height'] = frame_height_list
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

    for index in fig_indexes:
        index_elements = elements[elements['chart_index'] == index]
        assignments = index_elements["assignment"].values
        asn : str = assignments[0]
        period = index_elements["period"].values
        years = index_elements["sort_year"].values
        start_period = index_elements['sort_period'].values.min()
        y1,y2 = years.min(), years.max()
        p1,p2 = period.min(), period.max()
        t = asn.rsplit(".", 1)[0]
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
    fig_data['x_axis'] = "time"
    fig_data['y_axis'] = "currency"
    fig_data['currency_col'] = "values"
    fig_data['currency_unit'] = "dollars"
    fig_data['currency_format'] = "$ {value:,.0f}"
    if 'scaled_values' in elements.columns:
        fig_data['currency_col'] = "scaled_values"
        fig_data['currency_unit'] = "dollars_thousands"
        fig_data['currency_format'] = "$ {value:,.1f}K"
    fig_data['currency_format'] = "$"
    fig_data['time_col'] = "period"
    orientation = orientation_list[0]
    if orientation == "horizontal":
        fig_data['x_axis'] = "currency"
        fig_data['y_axis'] = "time"
    if "pie" in chart_type:
        fig_data['currency_col'] = "percent"
        fig_data['currency_unit'] = "percent"
        fig_data['currency_format'] = "%"
    fig_data['time_frequency'] = duration_list
    fig_data['n_time_points'] = time_point_list
    fig_data['n_elements'] = element_count_list
    fig_data["segments"] = segmented_list
    fig_data['element_orientation'] = orientation_list
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
    add_frame_dimensions(fig_df, chart_type)
    return fig_df


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
    # Add enriched chart data one column at a time
    # ----- Begin Adding Element Columns
    add_row_indexes(chart_data)
    add_chart_indexes(chart_data,chart_type)
    add_cluster_indexes(chart_data,chart_type)
    add_label_column(chart_data,chart_type)
    add_parent_column(chart_data, chart_type)
    add_stats_columns(chart_data, chart_type, cfg)
    add_ignore_column(chart_data, cfg)
    add_values_column(chart_data,chart_type, cfg)
    merge_ignore_rows_into_other(chart_data, cfg)
    add_color_column(chart_data, chart_type, cfg)
    # ----- End Adding Element Columns
    return chart_data