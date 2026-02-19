import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

import pandas as pd
import numpy as np

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
    ],
    32: [
        # Strong primaries, alternating warm/cool
        "#1f77b4",  # blue
        "#ff7f0e",  # orange
        "#2ca02c",  # green
        "#d62728",  # red
        "#9467bd",  # purple
        "#8c564b",  # brown
        "#17becf",  # cyan
        "#e377c2",  # pink

        # Muted / neutral breakers
        "#7f7f7f",  # gray
        "#bcbd22",  # olive

        # Light companions, again alternating hue
        "#aec7e8",  # light blue
        "#ffbb78",  # light orange
        "#98df8a",  # light green
        "#ff9896",  # light red
        "#c5b0d5",  # light purple
        "#c49c94",  # light brown

        # Dark companions, spaced far apart
        "#1a5f8a",  # dark blue
        "#cc660b",  # dark orange
        "#207a3a",  # dark green
        "#a61e22",  # dark red
        "#6f4fa0",  # dark purple
        "#6b4235",  # dark brown

        # Remaining contrast fillers
        "#128c8c",  # dark cyan
        "#b85c9e",  # dark pink
        "#5f5f5f",  # dark gray
        "#8f9019",  # dark olive
        "#89aed6",  # pale blue
        "#d99a5e",  # muted orange
        "#78b87a",  # muted green
        "#a07f72"   # muted brown
    ]
}

def get_color_palette(n_colors: int) -> list:
    """
    Get smallest pallette(4,5,16) that will have at least n_colors
    :param n_colors: Minimum size of palette
    :return:    Palette suitable for n_colors
    """
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

    title_font_size = 12
    label_font_size = 10

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
        wedges,texts = ax.pie(
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

        for pct, text in zip(values, texts):
            if pct < 3:
                text.set_fontsize(label_font_size - 3)
            elif pct < 5:
                text.set_fontsize(label_font_size - 1)

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


def adjust_margin(fig, ax, orientation: str):
    """
    Adjusts axes of plot to accommodate labels and titles
    using pixel-stable spacing so dynamic figure height
    does not inflate top margins.
    """

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    dpi = fig.dpi
    fig_width_pixels  = fig.get_figwidth() * dpi
    fig_height_pixels = fig.get_figheight() * dpi

    # ---------------------------------------------------------
    # 1) Shrink title font if it exceeds available figure width
    # ---------------------------------------------------------
    title = ax.title
    if title.get_text():

        max_title_width = fig_width_pixels * 0.95

        title_bbox = title.get_window_extent(renderer=renderer)
        title_width = title_bbox.width

        if title_width > max_title_width:
            scale = max_title_width / title_width
            new_size = max(6, title.get_fontsize() * scale)
            title.set_fontsize(new_size)
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()

    # ---------------------------------------------------------
    # 2) Adjust margins based on orientation
    # ---------------------------------------------------------
    fixed_top_padding_px = 60
    top_fraction = 1 - (fixed_top_padding_px / fig_height_pixels)

    if orientation == "horizontal":

        # ----- LEFT MARGIN (based on Y tick labels) -----
        labels = ax.get_yticklabels()
        max_pixels = max(
            label.get_window_extent(renderer=renderer).width
            for label in labels
        ) if labels else 0

        left = (max_pixels + 16) / fig_width_pixels
        bottom = 0.05

        ax.set_position([
            left,
            bottom,
            0.95 - left,
            top_fraction - bottom
        ])

    else:

        # ----- BOTTOM MARGIN (based on X tick labels) -----
        labels = ax.get_xticklabels()
        max_pixels = max(
            label.get_window_extent(renderer=renderer).height
            for label in labels
        ) if labels else 0

        bottom = (max_pixels + 16) / fig_height_pixels

        ax_pos = ax.get_position()

        ax.set_position([
            ax_pos.x0,
            bottom,
            ax_pos.width,
            top_fraction - bottom
        ])

    fig.subplots_adjust(top=top_fraction)

    # ---------------------------------------------------------
    # 3) Stabilize title spacing relative to axes (pixel-based)
    # ---------------------------------------------------------
    title = ax.title
    if title.get_text():

        fixed_title_gap_px = 14
        title_offset = fixed_title_gap_px / fig_height_pixels

        # Place title slightly above axes top (axes coordinates)
        title.set_y(1.0 + title_offset)


def adjust_margin_area(fig, ax, legend):
    """
    Adjust figure to accommodate:
    - Title width (shrink if needed)
    - Y-axis label width (left margin)
    - Legend placed outside right

    frame_width defines plot width.
    Figure expands; plot width remains constant.
    """

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    dpi = fig.dpi

    # ---------------------------------------------------------
    # 1) Current figure size
    # ---------------------------------------------------------
    fig_width_px  = fig.get_figwidth() * dpi
    fig_height_px = fig.get_figheight() * dpi

    ax_pos = ax.get_position()

    # Pixel width of plot area (preserve this)
    plot_width_px = ax_pos.width * fig_width_px

    # ---------------------------------------------------------
    # 2) Shrink title if needed
    # ---------------------------------------------------------
    title = ax.title
    if title.get_text():

        max_title_width = fig_width_px * 0.95
        title_bbox = title.get_window_extent(renderer=renderer)
        title_width = title_bbox.width

        if title_width > max_title_width:
            scale = max_title_width / title_width
            new_size = max(6, title.get_fontsize() * scale)
            title.set_fontsize(new_size)
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()

    # ---------------------------------------------------------
    # 3) Measure Y-axis label width (left margin)
    # ---------------------------------------------------------
    y_labels = ax.get_yticklabels()

    if y_labels:
        max_y_label_px = max(
            label.get_window_extent(renderer=renderer).width
            for label in y_labels
        )
    else:
        max_y_label_px = 0

    left_padding_px = 16
    left_margin_px = max_y_label_px + left_padding_px

    # ---------------------------------------------------------
    # 4) Measure legend width (right margin)
    # ---------------------------------------------------------
    legend_bbox = legend.get_window_extent(renderer=renderer)
    legend_width_px = legend_bbox.width

    right_padding_px = 12
    right_margin_px = legend_width_px + right_padding_px

    # ---------------------------------------------------------
    # 5) Compute new figure width
    # ---------------------------------------------------------
    new_fig_width_px = left_margin_px + plot_width_px + right_margin_px
    new_fig_width_in = new_fig_width_px / dpi

    fig.set_size_inches(new_fig_width_in, fig.get_figheight(), forward=True)
    fig.canvas.draw()

    # ---------------------------------------------------------
    # 6) Recalculate normalized axes position
    # ---------------------------------------------------------
    new_left_fraction = left_margin_px / new_fig_width_px
    new_width_fraction = plot_width_px / new_fig_width_px

    ax.set_position([
        new_left_fraction,
        ax_pos.y0,
        new_width_fraction,
        ax_pos.height
    ])

    fig.canvas.draw()


def render_bars(chart_elements: pd.DataFrame,
                figure_data: pd.DataFrame) -> plt.figure:

    frame_width  = figure_data.iloc[0]["frame_width"]
    frame_height = figure_data.iloc[0]["frame_height"]
    orientation  = figure_data.iloc[0]["orientation"]
    dpi          = figure_data.iloc[0]["dpi"]

    period_labels = chart_elements['period']
    assignments   = chart_elements['assignment']
    has_multi_periods = period_labels.nunique() > 1
    has_multi_asn     = assignments.nunique() > 1

    title_font_size       = 11
    major_label_font_size = 8

    fig = plt.figure(
        figsize=(frame_width / dpi, frame_height / dpi),
        dpi=dpi,
    )

    color_count = chart_elements["color"].max()
    palette = get_color_palette(color_count)

    # ---- Render each bar chart independently ----
    for _, fig_row in figure_data.iterrows():

        chart_index = fig_row["fig_index"]
        df = chart_elements[chart_elements["chart_index"] == chart_index]

        data_col        = fig_row["currency_col"]
        currency_format = fig_row["currency_format"]

        values = df[data_col].values

        if has_multi_asn:
            main_bar_labels = df["label"].astype(str).values
        else:
            main_bar_labels = None

        if has_multi_periods:
            if has_multi_asn:
                main_bar_labels = (
                    df["label"].astype(str) + " " + df["period"].astype(str)
                ).values
            else:
                main_bar_labels = df["period"].astype(str).values

        color_idx = df["color"].values - 1
        colors = [palette[i] for i in color_idx]

        # Temporary full-area axes, overriden below by adjust_margin
        ax = fig.add_axes([0.05, 0.05, 0.90, 0.90])
        ax.tick_params(labelsize=major_label_font_size)

        positions = df["elem_pos"].values

        if orientation == "horizontal":
            ax.barh(positions, values, color=colors)
            ax.xaxis.set_major_formatter(StrMethodFormatter(currency_format))

            ax.set_yticks(positions)
            ax.set_yticklabels(main_bar_labels, fontsize=major_label_font_size)

            ax.margins(y=0)
            ax.invert_yaxis()

        else:
            ax.bar(positions, values, color=colors, align="center")
            ax.yaxis.set_major_formatter(StrMethodFormatter(currency_format))

            ax.set_xticks(positions)
            ax.set_xticklabels(
                main_bar_labels,
                rotation=90,
                fontsize=major_label_font_size
            )
            ax.margins(x=0)

        ax.tick_params(axis="both", which="both", length=4)

        ax.set_title(
            fig_row["title"],
            fontsize=title_font_size,
            y=1.01,
            pad=0,
        )

        # ---- Precise margin adjustment ----
        adjust_margin(fig, ax, orientation)

    return fig

def render_area(chart_elements: pd.DataFrame,
                figure_data: pd.DataFrame) -> plt.figure:

    frame_width  = figure_data.iloc[0]["frame_width"]
    frame_height = figure_data.iloc[0]["frame_height"]
    dpi          = figure_data.iloc[0]["dpi"]

    title_font_size       = 11
    major_label_font_size = 8
    legend_font_size      = major_label_font_size - 1

    fig = plt.figure(
        figsize=(frame_width / dpi, frame_height / dpi),
        dpi=dpi,
    )

    color_count = chart_elements["color"].max()
    palette = get_color_palette(color_count)

    for _, fig_row in figure_data.iterrows():

        chart_index = fig_row["fig_index"]
        df = chart_elements[chart_elements["chart_index"] == chart_index]

        data_col        = fig_row["currency_col"]
        currency_format = fig_row["currency_format"]

        # ---- X axis (time) ----
        time_positions = df["time_pos"].drop_duplicates().values
        time_labels    = df["period"].drop_duplicates().values

        # ---- Series order (stack order) ----
        assignments = df["assignment"].drop_duplicates().values

        # ---- Build stacked series vectors ----
        stack_values = []
        stack_labels = []
        stack_colors = []

        for asn in assignments:
            series_df = df[df["assignment"] == asn]
            y = series_df[data_col].values
            stack_values.append(y)

            stack_labels.append(series_df["label"].iloc[0])

            color_index = series_df["color"].iloc[0] - 1
            stack_colors.append(palette[color_index])

        # ---- Temporary full-width axes ----
        ax = fig.add_axes([0.05, 0.05, 0.90, 0.90])
        ax.tick_params(labelsize=major_label_font_size)

        # ---- Stackplot (capture polys) ----
        polys = ax.stackplot(
            time_positions,
            stack_values,
            colors=stack_colors,
        )

        # ---- Axis formatting ----
        ax.set_xticks(time_positions)
        ax.set_xticklabels(time_labels, fontsize=major_label_font_size)

        ax.yaxis.set_major_formatter(StrMethodFormatter(currency_format))

        ax.margins(x=0)
        ax.tick_params(axis="both", which="both", length=4)

        ax.set_title(
            fig_row["title"],
            fontsize=title_font_size,
            y=1.01,
            pad=0,
        )

        # ---- Legend (outside right, reversed to match visual stack) ----
        legend = ax.legend(
            polys[::-1],
            stack_labels[::-1],
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            fontsize=legend_font_size,
            frameon=False,
        )

        # ---- Dynamic right margin adjustment ----
        adjust_margin_area(fig, ax, legend)

    return fig

