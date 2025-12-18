from typing import Dict, Any, List
import json
from pathlib import Path
import pandas as pd
import io

import matplotlib.pyplot as plt
from financials.routes.api_transactions import compute_assignments

# ------------------------------------------------------------------
# Chart spec loading
# ------------------------------------------------------------------

CFG_DIR = Path(__file__).resolve().parent / "cfg"


def render_warnings(fig, warnings, chart_spec, *, fontsize=8):
    if not warnings:
        return

    templates = chart_spec.get("warnings", {})
    lines = []

    for w in warnings:
        template = templates.get(w["code"])
        if template:
            lines.append(template.format(**w))

    if not lines:
        return

    fig.text(
        0.5,
        0.01,
        "\n".join(lines),
        ha="center",
        va="bottom",
        fontsize=fontsize,
        color="gray",
    )


def duration_to_label(duration: str) -> str:
    """
    Map duration to a human-readable label for chart titles.
    """
    return {
        "year": "",
        "quarter": "Quarterly",
        "month": "Monthly",
    }.get(duration, "")


def render_title(template: str, ctx: dict) -> str:
    """
    Render a title from a template and collapse extra whitespace.
    """
    title = template.format(**ctx)
    return " ".join(title.split())


def load_chart_spec(chart_type: str) -> dict:
    """
    Load and fully resolve a chart specification by merging:
      - plots.json (global defaults)
      - <chart_type>.json (chart-specific rules)

    Returns a resolved chart_spec suitable for rendering.
    """

    plots_path = CFG_DIR / "plots.json"
    if not plots_path.exists():
        raise FileNotFoundError("plots.json not found")

    with open(plots_path, "r") as f:
        plots_spec = json.load(f)

    chart_path = CFG_DIR / f"{chart_type}.json"
    if not chart_path.exists():
        raise FileNotFoundError(f"Unknown chart type: {chart_type}")

    with open(chart_path, "r") as f:
        chart_spec = json.load(f)

    resolved_params = {}
    for name, param_spec in chart_spec.get("parameters", {}).items():
        if "value" in param_spec:
            resolved_params[name] = param_spec["value"]
        elif "pctdistance" in param_spec:
            resolved_params[name] = param_spec["value"]
        else:
            source = param_spec.get("source")
            if not source or not source.startswith("plots.defaults."):
                raise ValueError(f"Invalid parameter source for '{name}'")

            key = source.replace("plots.defaults.", "")
            if plots_spec["defaults"][key]:
                resolved_params[name] = plots_spec["defaults"][key]

    chart_spec["parameters"] = resolved_params
    chart_spec["rendering"] = plots_spec["defaults"].get("rendering", {}).copy()

    return chart_spec


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------

class ChartNotAllowedError(Exception):
    def __init__(self, eligibility_result: dict):
        self.eligibility_result = eligibility_result
        super().__init__("Chart not allowed")


class ChartDataError(Exception):
    pass


class ChartConfigError(Exception):
    pass


# ------------------------------------------------------------------
# Row-level reducers
# ------------------------------------------------------------------

def reduce_mixed_sign(df):
    """
    Drop rows of the minority sign based on absolute summed value.
    Returns (df_reduced, warning | None)
    """

    pos = df[df["amount"] > 0]
    neg = df[df["amount"] < 0]

    if pos.empty or neg.empty:
        return df, None

    pos_sum = pos["amount"].sum()
    neg_sum = neg["amount"].abs().sum()

    if pos_sum >= neg_sum:
        kept = pos
        dropped = neg
        dropped_sign = "negative"
    else:
        kept = neg
        dropped = pos
        dropped_sign = "positive"

    warning = {
        "code": "mixed_sign_present",
        "rows": len(dropped),
        "amount": dropped["amount"].abs().sum(),
        "sign": dropped_sign,
    }

    return kept.copy(), warning


# ------------------------------------------------------------------
# Eligibility evaluation (legacy, partially retained)
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Chart rendering
# ------------------------------------------------------------------

def compute_pie(*, ax, labels, values, colors, title, chart_spec) -> None:
    parameters = chart_spec.get("parameters")
    pct_distance = parameters.get("pct_distance")
    ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        pctdistance=pct_distance,
        startangle=90,
    )
    ax.set_title(title)      # ← THIS must be here
    ax.axis("equal")


def _normalize_args(args: dict) -> tuple[dict, list[int] | None]:
    """
    Normalize query arguments.
    - Extract multi-year intent from year=2023,2024
    """
    args = args.copy()
    years = None

    year_arg = args.get("year")
    if isinstance(year_arg, str) and "," in year_arg:
        try:
            years = [int(y.strip()) for y in year_arg.split(",")]
            del args["year"]
        except ValueError:
            raise ChartConfigError(f"Invalid year filter: {year_arg}")

    return args, years


def _load_chart_data(args, filters, years):
    """
    Load canonical chart data.
    Expands multi-year requests into per-year fetches.
    """
    args = args.copy()
    args["expand"] = "1"

    if years:
        dfs = []
        meta = None

        for y in years:
            args_y = args.copy()
            args_y["year"] = str(y)

            df_y, meta_y = compute_assignments(
                args_y,
                filters=filters,
                zero_fill=False,
            )

            if not df_y.empty:
                dfs.append(df_y)
                meta = meta_y

        if not dfs:
            raise ChartDataError("No data available for chart")

        df = pd.concat(dfs, ignore_index=True)
        return df, meta

    df, meta = compute_assignments(
        args,
        filters=filters,
        zero_fill=False,
    )

    if df.empty:
        raise ChartDataError("No data available for chart")

    return df, meta


def _apply_row_reducers(df, meta, chart_type):
    warnings: list[dict] = []

    if chart_type == "pie" and meta.get("sign") == "mixed":
        df, warning = reduce_mixed_sign(df)
        if warning:
            warnings.append(warning)
        if df.empty:
            raise ChartDataError("No data remaining after mixed-sign reduction")

    if chart_type == "pie":
        df, warning = _reduce_minor_levels(df)   # data-driven depth drop
        if warning:
            warnings.append(warning)
        if df.empty:
            raise ChartDataError("No data remaining after minor-level reduction")

    return df, warnings


def _resolve_chart_context(chart_spec, args, meta, df):
    """
    Resolve duration, split dimension, titles, layout, and chart keys.
    """
    interpretation = chart_spec["interpretation"]
    eligibility_cfg = chart_spec.get("eligibility", {})
    layout_cfg = chart_spec["layout"]["multi_pie_behavior"]

    duration = args.get("duration", "year")

    duration_label = {
        "year": "",
        "quarter": "Quarterly",
        "month": "Monthly",
    }.get(duration, "")

    title_ctx = {
        "asn": args.get("asn", ""),
        "level": args.get("level", ""),
        "duration_label": duration_label,
    }

    title_template = chart_spec.get("title", {}).get("template", "")

    if duration == "year":
        dimension = "sort_year"
    else:
        dimension = interpretation.get("multi_chart_dimension", "period")

    if dimension not in df.columns:
        raise ChartConfigError(
            f"Required dimension '{dimension}' not found in DataFrame"
        )

    keys = list(dict.fromkeys(df[dimension].tolist()))

    max_charts = eligibility_cfg.get("max_periods")
    if max_charts is not None:
        keys = keys[:max_charts]

    return {
        "dimension": dimension,
        "keys": keys,
        "layout_cfg": layout_cfg,
        "title_ctx": title_ctx,
        "title_template": title_template,
        "duration": duration,
    }

def _reduce_minor_levels(df):
    """
    Drop rows deeper than the shallowest assignment level present.
    """
    if "assignment" not in df.columns or df.empty:
        return df, None

    depths = df["assignment"].apply(lambda a: a.count(".") + 1)
    major_depth = depths.min()

    mask = depths == major_depth
    dropped = int((~mask).sum())

    if dropped == 0:
        return df, None

    warning = {
        "code": "minor_levels_present",
        "rows": dropped,
    }

    return df[mask].copy(), warning

# ------------------------------------------------------------------
# Color assignment helper
# ------------------------------------------------------------------

def _build_assignment_color_map(
    df: pd.DataFrame,
    plots_spec: dict,
) -> tuple[dict[str, str], list[dict]]:
    """
    Build a deterministic assignment -> color map for a single rendering.

    Colors are assigned based on the distinct assignment order
    present in the base data table.

    Returns:
        (assignment_to_color, warnings)
    """

    warnings: list[dict] = []

    if "assignment" not in df.columns or df.empty:
        return {}, warnings

    # Preserve original distinct order
    assignments = list(dict.fromkeys(df["assignment"].tolist()))
    n = len(assignments)

    palettes = plots_spec.get("palettes", {})
    palette_defaults = plots_spec.get("palette_defaults", {})

    max_palette_size = int(palette_defaults.get("max_palette_size", 16))
    reuse_strategy = palette_defaults.get("reuse_strategy", "modulo")
    reuse_warning = palette_defaults.get("reuse_warning", False)
    reserved_colors = palette_defaults.get("reserved_colors", {})

    # Exclude reserved synthetic categories from palette assignment
    real_assignments = [
        a for a in assignments if a not in reserved_colors
    ]

    n_real = len(real_assignments)

    # Choose smallest palette >= n_real
    palette_sizes = sorted(int(k) for k in palettes.keys())
    selected_size = None

    for size in palette_sizes:
        if size >= n_real:
            selected_size = size
            break

    if selected_size is None:
        selected_size = max_palette_size

    palette = palettes.get(str(selected_size))
    if not palette:
        raise ChartConfigError(f"No palette defined for size {selected_size}")

    assignment_to_color: dict[str, str] = {}

    # Assign colors to real assignments
    for idx, assignment in enumerate(real_assignments):
        if idx < len(palette):
            color = palette[idx]
        else:
            if reuse_strategy == "modulo":
                color = palette[idx % len(palette)]
            else:
                raise ChartConfigError(f"Unknown palette reuse strategy: {reuse_strategy}")

        assignment_to_color[assignment] = color

    # Assign reserved colors (e.g. 'Other')
    for name, color in reserved_colors.items():
        assignment_to_color[name] = color

    # Emit a single reuse warning if applicable
    if reuse_warning and n_real > len(palette):
        warnings.append({
            "code": "palette_reuse",
            "assignments": n_real,
            "palette_size": len(palette),
        })

    return assignment_to_color, warnings

# ------------------------------------------------------------------
# Grid layout helper
# ------------------------------------------------------------------
def _compute_grid_layout(n: int) -> tuple[int, int]:
    """
    Compute a near-square grid layout for n charts.

    Returns:
        (rows, cols)

    Examples:
        n=12 -> (3, 4)
        n=8  -> (3, 3)
        n=6  -> (2, 3)
    """
    if n <= 0:
        return 0, 0

    # ceil(sqrt(n)) without importing math
    cols = int((n ** 0.5) + 0.9999)
    rows = (n + cols - 1) // cols

    return rows, cols


# ------------------------------------------------------------------
# Context-wide min_fraction helper
# ------------------------------------------------------------------

def _compute_global_min_fraction_assignments(
    df: pd.DataFrame,
    *,
    dimension: str,
    min_fraction: float,
    use_absolute: bool,
) -> set[str]:
    """
    Compute a global assignment inclusion set using average magnitude
    across all charts in the current rendering context.

    Returns a set of assignment names to KEEP.
    """

    if df.empty or "assignment" not in df.columns:
        return set()

    # Sum per (assignment, chart_key)
    grouped = (
        df
        .groupby(["assignment", dimension], as_index=False)["amount"]
        .sum()
    )

    if use_absolute:
        grouped["amount"] = grouped["amount"].abs()

    # Average per assignment across charts
    avg_by_assignment = (
        grouped
        .groupby("assignment", as_index=False)["amount"]
        .mean()
    )

    total = avg_by_assignment["amount"].sum()
    if total == 0:
        return set(avg_by_assignment["assignment"].tolist())

    keep = avg_by_assignment[
        (avg_by_assignment["amount"] / total) >= min_fraction
    ]["assignment"]

    return set(keep.tolist())


def compute_chart(
        *,
        chart_type: str,
        args: dict,
        filters: dict | None = None,
) -> bytes:
    """
    Full server-side charting pipeline.
    Returns PNG image bytes.
    """

    if chart_type != "pie":
        raise ChartConfigError(f"Unsupported chart type: {chart_type}")

    # ------------------------------------------------------------
    # 0. Normalize args
    # ------------------------------------------------------------
    args, years = _normalize_args(args)

    # ------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------
    df, meta = _load_chart_data(args, filters, years)

    # ------------------------------------------------------------
    # 2. Row-level reductions
    # ------------------------------------------------------------
    df, warnings = _apply_row_reducers(df, meta, chart_type)

    # ------------------------------------------------------------
    # 3. Load chart + plots specs
    # ------------------------------------------------------------
    chart_spec = load_chart_spec(chart_type)

    plots_path = CFG_DIR / "plots.json"
    with open(plots_path, "r") as f:
        plots_spec = json.load(f)

    assignment_colors, color_warnings = _build_assignment_color_map(df, plots_spec)
    warnings.extend(color_warnings)

    # ------------------------------------------------------------
    # 4. Resolve chart context
    # ------------------------------------------------------------
    ctx = _resolve_chart_context(chart_spec, args, meta, df)

    interpretation = chart_spec["interpretation"]
    other_cfg = chart_spec.get("other_slice", {})
    min_fraction = chart_spec["parameters"].get("min_fraction")

    rendering = chart_spec["rendering"]
    cell_inches = rendering.get("figure_inches", 5)
    dpi = rendering.get("dpi", 150)

    keys = ctx["keys"]
    dimension = ctx["dimension"]

    # ------------------------------------------------------------
    # 4a. Context-wide min_fraction (multi-chart only)
    # ------------------------------------------------------------
    global_keep_assignments = None

    if min_fraction is not None and len(keys) > 1:
        global_keep_assignments = _compute_global_min_fraction_assignments(
            df,
            dimension=dimension,
            min_fraction=min_fraction,
            use_absolute=interpretation.get("abs_for_negative_only", False),
        )

        warnings.append({
            "code": "min_fraction_applied_across_charts",
            "charts": len(keys),
        })

    # ------------------------------------------------------------
    # 5. Create figure
    # ------------------------------------------------------------
    use_grid = ctx["layout_cfg"].get("grid_layout", False)

    if use_grid and len(keys) > 1:
        rows, cols = _compute_grid_layout(len(keys))
        fig, axes = plt.subplots(
            rows,
            cols,
            figsize=(cell_inches * cols, cell_inches * rows),
        )
        axes = axes.flatten()
    else:
        fig, ax = plt.subplots(figsize=(cell_inches, cell_inches))
        axes = [ax]

    # ------------------------------------------------------------
    # 6. Render pies
    # ------------------------------------------------------------
    for idx, key in enumerate(keys):
        ax = axes[idx]
        df_part = df[df[dimension] == key]

        grouped = (
            df_part
            .groupby("assignment", as_index=False)["amount"]
            .sum()
        )

        values = grouped["amount"]
        if interpretation.get("abs_for_negative_only", False) and (values < 0).any():
            values = values.abs()

        assignments = grouped["assignment"].tolist()
        labels = [a.split(".")[-1] for a in assignments]
        colors = [assignment_colors.get(a) for a in assignments]

        if other_cfg.get("enabled") and min_fraction is not None:
            kept_labels, kept_values, kept_colors = [], [], []
            other_total = 0.0

            total = values.abs().sum() if values is not None else 0.0

            for asn, lbl, val, col in zip(assignments, labels, values, colors):
                if global_keep_assignments is not None:
                    keep = asn in global_keep_assignments
                else:
                    keep = abs(val) / total >= min_fraction if total else True

                if keep:
                    kept_labels.append(lbl)
                    kept_values.append(val)
                    kept_colors.append(col)
                else:
                    other_total += val

            if other_total != 0:
                kept_labels.append(other_cfg.get("label", "Other"))
                kept_values.append(other_total)
                kept_colors.append(assignment_colors.get("Other"))

            labels = kept_labels
            values = kept_values
            colors = kept_colors
        else:
            values = values.tolist()

        base_title = render_title(ctx["title_template"], ctx["title_ctx"])
        title = (
            f"{base_title} — {key}"
            if len(keys) > 1 and base_title
            else base_title or str(key)
        )

        compute_pie(
            ax=ax,
            labels=labels,
            values=values,
            colors=colors,
            title=title,
            chart_spec=chart_spec,
        )

    for j in range(len(keys), len(axes)):
        axes[j].axis("off")

    # ------------------------------------------------------------
    # 7. Finalize
    # ------------------------------------------------------------
    buf = io.BytesIO()
    plt.tight_layout()
    render_warnings(fig, warnings, chart_spec)
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    buf.seek(0)

    return buf.read()
