from typing import Dict, Any, List
import json
from pathlib import Path
import io

import matplotlib.pyplot as plt
from financials.routes.api_transactions import compute_assignments

# ------------------------------------------------------------------
# Chart spec loading
# ------------------------------------------------------------------

CFG_DIR = Path(__file__).resolve().parent / "cfg"


def load_chart_spec(chart_type: str) -> dict:
    """
    Load and fully resolve a chart specification by merging:
      - plots.json (global defaults)
      - <chart_type>.json (chart-specific rules)

    Returns a resolved chart_spec suitable for rendering.
    """

    # Load plots.json
    plots_path = CFG_DIR / "plots.json"
    if not plots_path.exists():
        raise FileNotFoundError("plots.json not found")

    with open(plots_path, "r") as f:
        plots_spec = json.load(f)

    # Load chart-specific spec
    chart_path = CFG_DIR / f"{chart_type}.json"
    if not chart_path.exists():
        raise FileNotFoundError(f"Unknown chart type: {chart_type}")

    with open(chart_path, "r") as f:
        chart_spec = json.load(f)

    # Resolve parameters
    resolved_params = {}
    for name, param_spec in chart_spec.get("parameters", {}).items():
        if "value" in param_spec:
            resolved_params[name] = param_spec["value"]
        else:
            source = param_spec.get("source")
            if not source or not source.startswith("plots.defaults."):
                raise ValueError(f"Invalid parameter source for '{name}'")

            key = source.replace("plots.defaults.", "")
            try:
                resolved_params[name] = plots_spec["defaults"][key]
            except KeyError:
                raise KeyError(f"plots.defaults.{key} not found")

    chart_spec["parameters"] = resolved_params

    # Inject rendering defaults
    chart_spec["rendering"] = plots_spec["defaults"].get("rendering", {}).copy()

    return chart_spec


# ------------------------------------------------------------------
# Domain-specific exceptions
# ------------------------------------------------------------------

class ChartNotAllowedError(Exception):
    """
    Raised when a chart fails eligibility rules.
    Carries the full eligibility result payload.
    """
    def __init__(self, eligibility_result: dict):
        self.eligibility_result = eligibility_result
        super().__init__("Chart not allowed")


class ChartDataError(Exception):
    """Raised when there is no data available to render a chart."""
    pass


class ChartConfigError(Exception):
    """Raised when chart configuration or schema is invalid."""
    pass


# ------------------------------------------------------------------
# Eligibility evaluation (unchanged logic)
# ------------------------------------------------------------------

def evaluate_eligibility(
    *,
    chart_type: str,
    meta: Dict[str, Any],
) -> tuple[dict, dict]:
    """
    Evaluate eligibility rules for a chart type.
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

    if eligibility.get("requires_same_sign"):
        if meta.get("sign") == "mixed":
            rule_keys.append("mixed_sign")
            reasons.append(disallowed_map.get(
                "mixed_sign",
                "Mixed positive and negative values are present"
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

def compute_pie(
    *,
    ax,
    labels: list[str],
    values: list[float],
    title: str,
    chart_spec: dict,
) -> None:
    """
    Render a single pie chart onto the provided matplotlib axis.
    """

    ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
    )
    ax.set_title(title)
    ax.axis("equal")


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
    # 1. Acquire canonical data + metadata
    # ------------------------------------------------------------
    args["expand"] = "1"    # Data set is always expanded. The JS client sets this explicitly anyway
    df, meta = compute_assignments(
        args,
        filters=filters,
        zero_fill=False,
    )

    if df.empty:
        raise ChartDataError("No data available for chart")

    # ------------------------------------------------------------
    # 2. Eligibility evaluation (loads resolved chart_spec)
    # ------------------------------------------------------------
    allowed_result, chart_spec = evaluate_eligibility(
        chart_type=chart_type,
        meta=meta,
    )

    if not allowed_result["eligible"]:
        raise ChartNotAllowedError(allowed_result)

    # ------------------------------------------------------------
    # 3. Dispatch by chart type
    # ------------------------------------------------------------
    if chart_type == "pie":
        pass
    else:
        raise ChartConfigError(f"Unsupported chart type: {chart_type}")

    # ------------------------------------------------------------
    # 4. Extract resolved spec components
    # ------------------------------------------------------------
    interpretation = chart_spec["interpretation"]
    labeling_cfg = chart_spec["labeling"]
    other_cfg = chart_spec.get("other_slice", {})
    eligibility_cfg = chart_spec["eligibility"]
    layout_cfg = chart_spec["layout"]["multi_pie_behavior"]

    min_fraction = chart_spec["parameters"].get("min_fraction")

    rendering = chart_spec["rendering"]
    cell_inches = rendering.get("figure_inches", 5)
    dpi = rendering.get("dpi", 150)

    # ------------------------------------------------------------
    # 5. Determine split dimension
    # ------------------------------------------------------------
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
    # 6. Create figure + axes
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
    # 7. Render each chart (generic loop)
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
        print("values 1", values)

        if interpretation.get("abs_for_negative_only", False):
            if (values < 0).any():
                values = values.abs()

        print("values 2", values)

        labels = [
            a.split(".")[-1]
            for a in grouped["assignment"].tolist()
        ]

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

        if chart_type == "pie":
            compute_pie(
                ax=ax,
                labels=labels,
                values=values,
                title=str(key),
                chart_spec=chart_spec,
            )

    for j in range(len(keys), len(axes)):
        axes[j].axis("off")

    # ------------------------------------------------------------
    # 8. Encode PNG
    # ------------------------------------------------------------
    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    buf.seek(0)

    return buf.read()
