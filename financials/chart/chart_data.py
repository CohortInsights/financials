from pandas import DataFrame, Series, factorize, concat
import numpy as np

from financials.chart.chart_common import ChartConfigError

global_chart_types: dict = {
    "pie": "Compare relative percentages of assignments for a single or multiple data periods",
    "bar": "Simple and stacked bar charts of assignment amounts over single or multiple data periods",
    "area": "evolution of assignment amounts over time, with areas stacked on top of each other to show both individual trends and the total, cumulative trend"
}


def get_char_types() -> dict:
    """
    Get chart types dictionary
   :returns a dictionary of definitions keyed by char_type
    """
    return global_chart_types

def add_chart_indexes(chart_data: DataFrame, chart_type: str) -> DataFrame:
    """
    Adds the column that encodes a column named "chart_index" (1-n) for each intended chart instance
    :param chart_data: Filtered assignment data
    :return: The input data after adding the 'chart_index' column
    """
    split_columns = []
    sort_keys = ["chart_index","period"]

    if "area" in chart_type:
        split_columns = ["level"]
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

        # Stable sort by chart_index so charts are contiguous,
        # while preserving original order *within* each chart
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
    group_columns = ["chart_index","period"]
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
    Compute a "values" column derived from the "amount" column.

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

    # Extract raw values
    values = chart_data["amount"].values
    thresholds = chart_data["threshold"].values

    # Determine sign presence using threshold-aware logic
    has_positive_over_threshold = (values > thresholds).any()
    has_negative = (values < 0).any()

    # Apply sign normalization rules
    if has_negative:
        if not has_positive_over_threshold or not support_mixed_sign:
            values = abs(values)

    # Assign computed values column
    chart_data["values"] = values

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

        values = chart_data.loc[idx, "values"]
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

    return chart_data


def add_label_column(chart_data : DataFrame, chart_type : str) -> DataFrame:
    full_labels = chart_data["assignment"]
    label = full_labels.str.rsplit(".", n=1).str[-1]
    chart_data['label'] = label
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
        threshold = max_val * min_frac

        if mag > 0:
            percent = (abs_values * 100.0 / mag).round(1)
        else:
            percent = Series(0.0, index=abs_values.index)

        # Assign stats to rows in this group
        chart_data.loc[idx, "mag"] = round(mag, 2)
        chart_data.loc[idx, "percent"] = percent
        chart_data.loc[idx, "threshold"] = round(threshold, 2)

    return chart_data


def add_percent_column(chart_data : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    return chart_data

def add_title_column(chart_data : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    return chart_data

def add_color_column(chart_data : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    return chart_data


def compute_chart_data(source_data : DataFrame, chart_type : str, cfg : dict, render=False) -> DataFrame:
    """
        Computes chart.data consistent with the specified assignment source data and chart_type

    :param source_data: Filtered assignment data that is authoritative input
    :param chart_type: String denoting the type of chart
    :param cfg: Dictionary of confi parameters
    :param render: Whether to return chart data stripped to values relevant only to rendering
    :return:
    """
    if chart_type not in global_chart_types.keys():
        return ChartConfigError(f"Chart type {chart_type} not recognized")

    # Chart data starts as copy of input data
    chart_data = source_data.copy()
    # Add enriched chart data one column at a time
    add_chart_indexes(chart_data,chart_type)
    add_cluster_indexes(chart_data,chart_type)
    add_label_column(chart_data,chart_type)
    # Apply stats and merge values < threshold
    add_stats_columns(chart_data, chart_type, cfg)
    add_values_column(chart_data,chart_type, cfg)
    add_ignore_column(chart_data, cfg)
    merge_ignore_rows_into_other(chart_data, cfg)
    # Add final two presentation columns
    add_title_column(chart_data, chart_type, cfg)
    add_color_column(chart_data, chart_type, cfg)
    if render:
        pass
    return chart_data