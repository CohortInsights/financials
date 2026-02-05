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
    - No inference, no sorting, no scaling heuristics
    """

    # ---- Figure geometry (authoritative singletons) ----
    frame_width  = figure_data.iloc[0]["frame_width"]
    frame_height = figure_data.iloc[0]["frame_height"]
    dpi          = figure_data.iloc[0]["dpi"]
    title_font_size = int(frame_height * 0.03)
    label_font_size = int(frame_height * 0.02)

    n_rows = figure_data["grid_year"].max() + 1
    n_cols = figure_data["grid_period"].max() + 1

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
    pad = 0  # normalized figure units

    # ---- Render each pie independently ----
    for _, fig_row in figure_data.iterrows():

        chart_index = fig_row["fig_index"]

        # Slice rows are authoritative and already ordered
        df = chart_elements[chart_elements["chart_index"] == chart_index]

        # Data column explicitly declared
        data_col = fig_row["currency_col"]
        values = df[data_col].values
        labels = df["label"].values

        # Convert 1-based color indices → 0-based
        color_idx = df["color"].values - 1
        colors = [palette[i] for i in color_idx]

        # ---- Explicit axes placement (fully independent) ----
        col = fig_row["grid_period"]
        row = fig_row["grid_year"]

        left   = col * tile_w + pad
        bottom = 1.0 - (row + 1) * tile_h + pad
        width  = tile_w - 2 * pad
        height = tile_h - 2 * pad

        ax = fig.add_axes([left, bottom, width, height])

        # ---- Geometry delegated entirely to Matplotlib ----
        ax.pie(
            values,
            colors=colors,
            labels=labels,
            labeldistance=0.70,  # pull labels inward
            textprops={
                "fontsize": 8,
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
