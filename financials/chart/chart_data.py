from pandas import DataFrame, Series, factorize
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
    - Bar charts support mixed-sign data, so values are passed through unchanged.
    - Pie and stacked-area charts do NOT support mixed-sign data. For these charts,
      negative values must be handled by converting to all same sign data

    :param chart_data: Assignment data containing an "amount" column
    :param chart_type: String denoting the type of chart
    :param cfg: Chart configuration dictionary (expects optional "min_frac")
    :return: DataFrame with added "values" column and possibly filtered rows
    """
    # Bar charts can represent mixed positive and negative values directly
    support_mixed_sign = "bar" in chart_type

    # Extract raw amount values
    values = chart_data["amount"].values

    pos_values = values[values >= 0]
    neg_values = values[values < 0]
    # Only apply special logic if negative values exist
    if len(neg_values) > 0:
        if len(pos_values) == 0 or not support_mixed_sign:
            values = abs(values)

    # Assign the computed values column
    chart_data["values"] = values

    return chart_data

def add_label_column(chart_data : DataFrame, chart_type : str) -> DataFrame:
    full_labels = chart_data["assignment"]
    label = full_labels.str.rsplit(".", n=1).str[-1]
    chart_data['label'] = label
    return chart_data


from pandas import DataFrame, Series
import pandas as pd

from pandas import DataFrame, Series
import pandas as pd


from pandas import DataFrame, Series

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
    # Add final two presentation columns
    add_title_column(chart_data, chart_type, cfg)
    add_color_column(chart_data, chart_type, cfg)
    if render:
        pass
    return chart_data