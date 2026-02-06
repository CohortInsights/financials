import matplotlib.pyplot as plt
import pandas as pd

palettes = {
    4: [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728"
    ],
    8: [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f"
    ],
    16 : [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#aec7e8",
        "#ffbb78",
        "#98df8a",
        "#ff9896",
        "#c5b0d5",
        "#c49c94"
    ]
}

def get_color_palette(n_colors: int) -> list:
    size = 4

    while size < n_colors:
        size *= 2
        if size not in palettes:
            raise ValueError(f"No palette supported for {n_colors} colors")

    return palettes[size]


def render_pies(chart_elements: pd.DataFrame,
                figure_data: pd.DataFrame):
    """
    Deterministic pie renderer.

    - One composite Figure
    - One pie per fig_index / chart_index
    - Fully independent axes (no subplot grid)
    - All layout derived explicitly from figure_data
    - Grid auto-swaps so larger dimension runs horizontally
    - No inference, no sorting, no scaling heuristics
    """

    # ---- Figure geometry (authoritative singletons) ----
    frame_width  = figure_data.iloc[0]["frame_width"]
    frame_height = figure_data.iloc[0]["frame_height"]
    dpi          = figure_data.iloc[0]["dpi"]
    unit = figure_data.iloc[0]["currency_unit"]
    is_percent = "percent" in unit

    def scale_font(scaling, low, high):
        size = int(max(frame_width,frame_height) * scaling)
        if size < low:
            return low
        if size > high:
            return high
        return size

    title_font_size = scale_font(0.03,14,24)
    label_font_size = scale_font(0.02,12,16)

    # ---- Canonical grid extents ----
    year_rows   = figure_data["grid_year"].max() + 1
    period_cols = figure_data["grid_period"].max() + 1

    # ---- Auto-orient grid so larger dimension runs horizontally ----
    if year_rows <= period_cols:
        # Default: years vertical, periods horizontal
        row_field = "grid_year"
        col_field = "grid_period"
        n_rows = year_rows
        n_cols = period_cols
    else:
        # Swap: periods vertical, years horizontal
        row_field = "grid_period"
        col_field = "grid_year"
        n_rows = period_cols
        n_cols = year_rows

    # ---- Composite figure size ----
    fig_width_px  = n_cols * frame_width
    fig_height_px = n_rows * frame_height

    fig = plt.figure(
        figsize=(fig_width_px / dpi, fig_height_px / dpi),
        dpi=dpi,
    )

    # ---- Color palette (authoritative indices) ----
    color_count = chart_elements["color"].max()
    palette = get_color_palette(color_count)

    # ---- Normalized tile size (figure coordinates) ----
    tile_w = frame_width / fig_width_px
    tile_h = frame_height / fig_height_px

    # Small deterministic padding inside each tile
    pad = 0.0  # normalized figure units

    # ---- Render each pie independently ----
    for _, fig_row in figure_data.iterrows():

        chart_index = fig_row["fig_index"]

        # Slice rows are authoritative and already ordered
        df = chart_elements[chart_elements["chart_index"] == chart_index]

        # Data column explicitly declared
        data_col = fig_row["currency_col"]
        values = df[data_col].values
        labels = df["label"].values
        label_list = []
        n_labels = len(labels)
        for index in range(n_labels):
            new_label = labels[index] + "\n" + str(values[index])
            if is_percent:
                new_label += '%'
            label_list.append(new_label)

        # Convert 1-based color indices → 0-based
        color_idx = df["color"].values - 1
        colors = [palette[i] for i in color_idx]

        # ---- Explicit axes placement (closed universe) ----
        row = fig_row[row_field]
        col = fig_row[col_field]

        left   = col * tile_w + pad
        bottom = 1.0 - (row + 1) * tile_h + pad
        width  = tile_w - 2 * pad
        height = tile_h - 2 * pad

        ax = fig.add_axes([left, bottom, width, height])

        # ---- Geometry delegated entirely to Matplotlib ----
        ax.pie(
            values,
            colors=colors,
            labels=label_list,
            labeldistance=0.70,
            textprops={
                "fontsize": label_font_size,
                "ha": "center",
                "va": "center",
            },
        )

        ax.set_aspect("equal")
        ax.set_axis_off()

        # ---- Title: inside the axes (closed universe model) ----
        ax.set_title(
            fig_row["title"],
            fontsize=title_font_size,
            y=0.93,
            pad=0,
        )

    return fig
