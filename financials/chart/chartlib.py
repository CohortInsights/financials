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

def render_warnings(fig, warnings, *, fontsize=8):
    """
    Render warning footnotes at the bottom of the figure.
    """
    if not warnings:
        return

    lines = []
    for w in warnings:
        if w["code"] == "mixed_sign_present":
            amount = f"${w['amount']:,.0f}"
            rows = w["rows"]
            sign = w["sign"]
            lines.append(f"* {amount} ({rows} rows) of {sign} values were ignored")

    if not lines:
        return

    text = "\n".join(lines)

    fig.text(
        0.5,
        0.01,
        text,
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
        else:
            source = param_spec.get("source")
            if not source or not source.startswith("plots.defaults."):
                raise ValueError(f"Invalid parameter source for '{name}'")

            key = source.replace("plots.defaults.", "")
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

def evaluate_eligibility(*, chart_type: str, meta: Dict[str, Any]) -> tuple[dict, dict]:
    """
    Evaluate remaining eligibility rules for a chart type.
    Mixed-sign is no longer disqualifying.
    """

    chart_spec = load_chart_spec(chart_type)
    eligibility = chart_spec.get("eligibility", {})
    disallowed_map = chart_spec.get("disallowed_reasons", {})

    reasons: List[str] = []
    rule_keys: List[str] = []

    if eligibility.get("requires_major_level"):
        if meta.get("major_assignment_count", 0) < 2:
            rule_keys.append("no_major_level")
            reasons.append(disallowed_map.get(
                "no_major_level",
                "Insufficient number of distinct assignments"
            ))

    if eligibility.get("forbids_minor_levels"):
        if meta.get("minor_levels"):
            rule_keys.append("minor_levels_present")
            reasons.append(disallowed_map.get(
                "minor_levels_present",
                "Minor levels are present"
            ))

    if eligibility.get("requires_single_year"):
        if meta.get("sort_year_count", 0) != 1:
            rule_keys.append("multiple_years")
            reasons.append(disallowed_map.get(
                "multiple_years",
                "Multiple years are present"
            ))

    if eligibility.get("requires_single_period"):
        if meta.get("sort_period_count", 0) != 1:
            rule_keys.append("multiple_periods")
            reasons.append(disallowed_map.get(
                "multiple_periods",
                "Multiple periods are present"
            ))

    allowed_result = {
        "chart_type": chart_type,
        "eligible": not reasons
    }

    if reasons:
        allowed_result["reasons"] = reasons
        allowed_result["rule_keys"] = rule_keys

    return allowed_result, chart_spec


# ------------------------------------------------------------------
# Chart rendering
# ------------------------------------------------------------------

def compute_pie(*, ax, labels, values, title, chart_spec) -> None:
    ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
    )
    ax.set_title(title)
    ax.axis("equal")

def _normalize_args(args: dict) -> tuple[dict, list[int] | None]:
    args = args.copy()

    year_arg = args.get("year")
    years = None

    if isinstance(year_arg, str) and "," in year_arg:
        try:
            years = [int(y.strip()) for y in year_arg.split(",")]
            del args["year"]   # IMPORTANT
        except ValueError:
            raise ChartConfigError(f"Invalid year filter: {year_arg}")

    return args, years

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

    # ------------------------------------------------------------
    # 0. Normalize arguments (extract multi-year intent)
    # ------------------------------------------------------------
    args = args.copy()

    year_arg = args.get("year")
    years = None

    if isinstance(year_arg, str) and "," in year_arg:
        try:
            years = [int(y.strip()) for y in year_arg.split(",")]
            del args["year"]   # IMPORTANT: do not pass list downstream
        except ValueError:
            raise ChartConfigError(f"Invalid year filter: {year_arg}")

    # ------------------------------------------------------------
    # 1. Acquire canonical data + metadata
    # ------------------------------------------------------------
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
                meta = meta_y   # metadata shape is consistent

        if not dfs:
            raise ChartDataError("No data available for chart")

        df = pd.concat(dfs, ignore_index=True)

    else:
        df, meta = compute_assignments(
            args,
            filters=filters,
            zero_fill=False,
        )

        if df.empty:
            raise ChartDataError("No data available for chart")

    warnings: list[dict] = []

    # ------------------------------------------------------------
    # 2. Row-level reductions (BEFORE grouping / Other)
    # ------------------------------------------------------------
    if meta.get("sign") == "mixed":
        df, warning = reduce_mixed_sign(df)
        if warning:
            warnings.append(warning)

        if df.empty:
            raise ChartDataError("No data remaining after mixed-sign reduction")

    # ------------------------------------------------------------
    # 3. Eligibility evaluation (legacy rules still apply)
    # ------------------------------------------------------------
    allowed_result, chart_spec = evaluate_eligibility(
        chart_type=chart_type,
        meta=meta,
    )

    if not allowed_result["eligible"]:
        raise ChartNotAllowedError(allowed_result)

    if chart_type != "pie":
        raise ChartConfigError(f"Unsupported chart type: {chart_type}")

    # ------------------------------------------------------------
    # 4. Extract resolved spec components
    # ------------------------------------------------------------
    interpretation = chart_spec["interpretation"]
    other_cfg = chart_spec.get("other_slice", {})
    eligibility_cfg = chart_spec.get("eligibility", {})
    layout_cfg = chart_spec["layout"]["multi_pie_behavior"]

    min_fraction = chart_spec["parameters"].get("min_fraction")

    rendering = chart_spec["rendering"]
    cell_inches = rendering.get("figure_inches", 5)
    dpi = rendering.get("dpi", 150)

    # ------------------------------------------------------------
    # 5. Title context (intent-based, from query args)
    # ------------------------------------------------------------
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

    title_cfg = chart_spec.get("title", {})
    title_template = title_cfg.get("template", "")

    def render_title(template: str, ctx: dict) -> str:
        title = template.format(**ctx)
        return " ".join(title.split())

    # ------------------------------------------------------------
    # 6. Determine split dimension strictly from duration
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # 7. Create figure + axes
    # ------------------------------------------------------------
    use_grid = layout_cfg.get("grid_layout", False)

    if use_grid and len(keys) > 1:
        max_columns = 2
        cols = min(max_columns, len(keys))
        rows = (len(keys) + cols - 1) // cols

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
    # 8. Render each pie
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

        if interpretation.get("abs_for_negative_only", False):
            if (values < 0).any():
                values = values.abs()

        labels = [
            a.split(".")[-1]
            for a in grouped["assignment"].tolist()
        ]

        # ---- Other slice logic (AFTER reductions) ----
        if other_cfg.get("enabled") and min_fraction is not None:
            total = values.abs().sum()
            if total > 0:
                kept_labels = []
                kept_values = []
                other_total = 0.0

                for lbl, val in zip(labels, values):
                    if abs(val) / total < min_fraction:
                        other_total += val
                    else:
                        kept_labels.append(lbl)
                        kept_values.append(val)

                if other_total != 0:
                    kept_labels.append(other_cfg.get("label", "Other"))
                    kept_values.append(other_total)

                labels = kept_labels
                values = kept_values
            else:
                values = values.tolist()
        else:
            values = values.tolist()

        base_title = render_title(title_template, title_ctx)

        if len(keys) > 1:
            title = f"{base_title} — {key}" if base_title else str(key)
        else:
            title = base_title or str(key)

        compute_pie(
            ax=ax,
            labels=labels,
            values=values,
            title=title,
            chart_spec=chart_spec,
        )

    for j in range(len(keys), len(axes)):
        axes[j].axis("off")

    # ------------------------------------------------------------
    # 9. Encode PNG (with warnings rendered)
    # ------------------------------------------------------------
    buf = io.BytesIO()
    plt.tight_layout()

    render_warnings(fig, warnings)

    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    buf.seek(0)

    return buf.read()
