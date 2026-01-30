import json
from pathlib import Path
import pandas as pd
from financials.routes.api_transactions import compute_assignments


CFG_DIR = Path(__file__).resolve().parent / "cfg"


class ChartDataError(Exception):
    pass

class ChartConfigError(Exception):
    pass

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
    chart_spec["palettes"] = plots_spec.get("palettes", {})
    chart_spec["palette_defaults"] = plots_spec.get("palette_defaults", {})
    chart_spec["rendering"] = plots_spec["defaults"].get("rendering", {}).copy()

    return chart_spec


def _load_chart_data(args, filters, years):
    """
    Load canonical chart data and compute meta
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
