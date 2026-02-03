from pandas import DataFrame, Series

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

def add_chart_indexes(chart_data: DataFrame, chart_type: str) -> DataFrame:
    """
    Adds the column that encodes a column named "Chart_index" (1-n) for each intended chart instance
    :param chart_data: Filtered assignment data
    :return: The input data after adding the 'Chart_index' column
    """
    split_by_period: bool = ("pie" in chart_type)
    column_name = "Chart_index"

    if split_by_period:
        if "period" not in chart_data.columns:
            raise ChartConfigError("Chart type requires 'Period' column but it is missing")

        # Preserve first-seen order of distinct Period values
        distinct_periods = chart_data["period"].drop_duplicates().tolist()
        period_to_index = {p: i + 1 for i, p in enumerate(distinct_periods)}
        chart_data[column_name] = chart_data["period"].map(period_to_index)
        # Returned data is sorted by the chart index
        chart_data.sort_values(by=column_name, inplace=True, kind="stable")

    else:
        # Single chart instance
        chart_data[column_name] = 1

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

    if not support_mixed_sign:
        neg_values = values[values < 0]

        # Only apply special logic if negative values exist
        if len(neg_values) > 0:
            values = abs(values)

    # Assign the computed values column
    chart_data["values"] = values

    return chart_data


def add_label_column(chart_data : DataFrame, chart_type : str) -> DataFrame:
    return chart_data

def add_max_column(chart_data : DataFrame, chart_type : str) -> DataFrame:
    return chart_data

def add_sum_column(chart_data : DataFrame, chart_type : str) -> DataFrame:
    return chart_data

def add_threshold_column(chart_data : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    return chart_data

def add_percent_column(chart_data : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
    return chart_data

def apply_thresholds(chart_data : DataFrame, chart_type : str, cfg : dict) -> DataFrame:
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
    add_values_column(chart_data,chart_type, cfg)
    add_label_column(chart_data,chart_type)
    add_max_column(chart_data,chart_type)
    add_sum_column(chart_data,chart_type)
    add_percent_column(chart_data, chart_type, cfg)
    add_threshold_column(chart_data, chart_type, cfg)
    # Merges values below thresholds
    apply_thresholds(chart_data,chart_type,cfg)
    # Add final two presentation columns
    add_title_column(chart_data, chart_type, cfg)
    add_color_column(chart_data, chart_type, cfg)
    if render:
        pass
    return chart_data