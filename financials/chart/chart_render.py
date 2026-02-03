from typing import Dict, Any, List, Optional
import io
import json
import pandas as pd
import matplotlib.pyplot as plt

# ------------------------------------------------------------------
# Imports from legacy chartlib (temporary)
# ------------------------------------------------------------------

from financials.chart.chart_common import (
    _normalize_args,
    _load_chart_data,
    load_chart_spec,
    render_warnings,
    ChartDataError,
    ChartConfigError,
)

# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

def compute_chart_v2(
    *,
    chart_type: str,
    args: dict,
    filters: dict | None = None,
) -> bytes:
    """
    Next-generation chart rendering pipeline.

    Design principles:
    - Table-driven semantics
    - Ordering is authoritative
    - No inference from incidental structure
    - Explicit, phase-based pipeline
    - General by construction

    Currently supported:
    - bar charts only (guarded)

    Returns:
        PNG image bytes
    """

    # ------------------------------------------------------------
    # 0. Guardrails (temporary)
    # ------------------------------------------------------------
    if chart_type != "bar":
        raise ChartConfigError(
            "compute_chart_v2 currently supports bar charts only"
        )

    # ------------------------------------------------------------
    # 1. Normalize args
    # ------------------------------------------------------------
    args, years = _normalize_args(args)

    # ------------------------------------------------------------
    # 2. Load data and chart specification
    # ------------------------------------------------------------
    df, meta = _load_chart_data(args, filters, years)
    chart_spec = load_chart_spec(chart_type)

    if df.empty:
        raise ChartDataError("No data available for chart")

    # ------------------------------------------------------------
    # 3. Establish render scope
    # ------------------------------------------------------------
    # Single chart per request; no implicit subplotting
    render_df = df.copy()

    # ------------------------------------------------------------
    # 4. Normalize hierarchy
    # ------------------------------------------------------------
    hierarchy = _normalize_hierarchy(
        render_df,
    )

    print (hierarchy)
    return hierarchy

    # ------------------------------------------------------------
    # 5. Apply fractional filtering (min_fraction)
    # ------------------------------------------------------------
    rows, warnings = _apply_fraction_filter(
        hierarchy["rows"],
        chart_spec=chart_spec,
    )

    if not rows:
        raise ChartDataError("No data remaining after filtering")

    # ------------------------------------------------------------
    # 6. Resolve value semantics (sign handling)
    # ------------------------------------------------------------
    value_semantics = _resolve_value_semantics(
        rows,
        meta=meta,
        chart_spec=chart_spec,
    )

    # ------------------------------------------------------------
    # 7. Assign visual encodings
    # ------------------------------------------------------------
    encodings = _assign_visual_encodings(
        rows,
        hierarchy=hierarchy,
        chart_spec=chart_spec,
    )

    # ------------------------------------------------------------
    # 8. Build render plan
    # ------------------------------------------------------------
    render_plan = _build_render_plan(
        rows,
        hierarchy=hierarchy,
        encodings=encodings,
        value_semantics=value_semantics,
        chart_spec=chart_spec,
    )

    # ------------------------------------------------------------
    # 9. Render
    # ------------------------------------------------------------
    fig, ax = _render(
        render_plan,
        value_semantics=value_semantics,
        chart_spec=chart_spec,
    )

    # ------------------------------------------------------------
    # 10. Finalize
    # ------------------------------------------------------------
    buf = io.BytesIO()
    plt.tight_layout()
    render_warnings(fig, warnings, chart_spec)
    fig.savefig(
        buf,
        format="png",
        dpi=chart_spec["rendering"].get("dpi", 150),
    )
    plt.close(fig)
    buf.seek(0)

    return buf.read()


# ------------------------------------------------------------------
# Hierarchy normalization
# ------------------------------------------------------------------

def _normalize_hierarchy(df: pd.DataFrame) -> dict:
    """
    Determine whether the chart should be rendered as single-level or hierarchical
    (parent/child), based strictly on ROW COUNT per level — not distinct assignments.

    Rules:
    - Compute depth from assignment prefix (x.y.z → depth 3).
    - Drop any depth that produces only ONE ROW in the render context.
    - From remaining depths, keep the deepest two.
    - If only one depth remains → single_level
    - If two depths remain → hierarchical (stacked)
    """

    work = df.copy()

    if "assignment" not in work.columns or work.empty:
        return {
            "mode": "single_level",
            "rows": []
        }

    # ------------------------------------------------------------------
    # 1. Compute depth from assignment prefix
    # ------------------------------------------------------------------
    work["_depth"] = work["assignment"].apply(lambda a: a.count(".") + 1)

    # ------------------------------------------------------------------
    # 2. Count ROWS per depth (not distinct assignments)
    # ------------------------------------------------------------------
    depth_row_counts = (
        work.groupby("_depth")
            .size()
            .to_dict()
    )

    # ------------------------------------------------------------------
    # 3. Keep only depths that contribute >1 row
    # ------------------------------------------------------------------
    valid_depths = sorted(
        d for d, n in depth_row_counts.items() if n > 1
    )

    # If nothing meaningful remains, fall back to single-level
    if not valid_depths:
        return {
            "mode": "single_level",
            "rows": []
        }

    # ------------------------------------------------------------------
    # 4. Keep at most the deepest two levels
    # ------------------------------------------------------------------
    kept_depths = valid_depths[-2:]

    # ------------------------------------------------------------------
    # 5. Filter rows to kept depths
    # ------------------------------------------------------------------
    work = work[work["_depth"].isin(kept_depths)].copy()

    # ------------------------------------------------------------------
    # 6. Decide mode
    # ------------------------------------------------------------------
    if len(kept_depths) == 1:
        return {
            "mode": "single_level",
            "rows": []
        }

    # ------------------------------------------------------------------
    # 7. Hierarchical case: identify parent/child roles
    # ------------------------------------------------------------------
    parent_depth, child_depth = kept_depths

    work["role"] = work["_depth"].apply(
        lambda d: "parent" if d == parent_depth else "child"
    )

    # Parent assignment is the prefix up to parent depth
    def parent_assignment(a: str, depth: int) -> str:
        parts = a.split(".")
        return ".".join(parts[:depth])

    work["parent_assignment"] = work.apply(
        lambda r: (
            None
            if r["role"] == "parent"
            else parent_assignment(r["assignment"], parent_depth)
        ),
        axis=1
    )

    return {
        "mode": "hierarchical",
        "rows": work
    }


def _common_assignment_prefix(assignments: List[str]) -> str:
    """
    Compute the longest common dotted prefix.
    """
    if not assignments:
        return ""

    parts = [a.split(".") for a in assignments]
    prefix = []

    for segments in zip(*parts):
        if all(seg == segments[0] for seg in segments):
            prefix.append(segments[0])
        else:
            break

    return ".".join(prefix)


# ------------------------------------------------------------------
# Fractional filtering (stub, to be implemented next)
# ------------------------------------------------------------------

def _apply_fraction_filter(
    rows: List[dict],
    *,
    chart_spec: dict,
) -> tuple[list[dict], list[dict]]:
    """
    Apply min_fraction filtering to rows.

    Semantics:
    - Drop rows, not categories
    - Preserve order
    - Emit warnings only

    STUB: currently no-op
    """
    return rows, []


# ------------------------------------------------------------------
# Value semantics (stub)
# ------------------------------------------------------------------

def _resolve_value_semantics(
    rows: List[dict],
    *,
    meta: dict,
    chart_spec: dict,
) -> dict:
    """
    Determine signed vs absolute value usage and zero-line behavior.

    STUB: returns mixed-sign defaults
    """
    return {
        "mode": "signed",
        "show_zero_line": True,
    }


# ------------------------------------------------------------------
# Visual encodings (stub)
# ------------------------------------------------------------------

def _assign_visual_encodings(
    rows: List[dict],
    *,
    hierarchy: dict,
    chart_spec: dict,
) -> dict:
    """
    Assign colors and other visual encodings.

    STUB
    """
    return {}


# ------------------------------------------------------------------
# Render plan (stub)
# ------------------------------------------------------------------

def _build_render_plan(
    rows: List[dict],
    *,
    hierarchy: dict,
    encodings: dict,
    value_semantics: dict,
    chart_spec: dict,
) -> list:
    """
    Build a renderer-ready plan from normalized rows.

    STUB
    """
    return []


# ------------------------------------------------------------------
# Rendering (stub)
# ------------------------------------------------------------------

def _render(
    render_plan: list,
    *,
    value_semantics: dict,
    chart_spec: dict,
):
    """
    Render a chart from a render plan.

    STUB
    """
    fig, ax = plt.subplots()
    ax.set_title("TODO")
    return fig, ax
