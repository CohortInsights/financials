from typing import Dict, Any, List, Optional
import io
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
        chart_spec=chart_spec,
    )

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

def _normalize_hierarchy(
    df: pd.DataFrame,
    *,
    chart_spec: dict,
) -> dict:
    """
    Normalize hierarchical structure from an ordered table.

    Rules:
    - Depth derived from assignment prefix
    - Drop levels with only one assignment
    - Retain at most two adjacent deepest levels
    - Preserve table order
    """

    if df.empty or "assignment" not in df.columns:
        return {"mode": "single_level", "rows": []}

    work = df.copy()
    work["_depth"] = work["assignment"].apply(lambda a: a.count(".") + 1)

    depth_counts = (
        work.groupby("_depth")["assignment"].nunique().to_dict()
    )

    valid_depths = [d for d, n in depth_counts.items() if n > 1]

    if not valid_depths:
        valid_depths = [work["_depth"].min()]

    valid_depths = sorted(valid_depths)

    if len(valid_depths) > 2:
        deepest = valid_depths[-1]
        candidate = deepest - 1
        valid_depths = (
            [candidate, deepest] if candidate in valid_depths else [deepest]
        )

    work = work[work["_depth"].isin(valid_depths)].copy()

    # ------------------------------------------------------------
    # Single-level
    # ------------------------------------------------------------
    if len(valid_depths) == 1:
        assignments = work["assignment"].tolist()
        prefix = _common_assignment_prefix(assignments)

        rows = []
        for _, row in work.iterrows():
            rows.append({
                "assignment": row["assignment"],
                "assignment_suffix": row["assignment"][len(prefix):].lstrip("."),
                "period": row.get("period"),
                "year": row.get("year"),
                "value": row["amount"],
                "role": "single",
                "parent_assignment": None,
            })

        return {"mode": "single_level", "rows": rows}

    # ------------------------------------------------------------
    # Two-level (stacked)
    # ------------------------------------------------------------
    parent_depth, child_depth = valid_depths

    parents = set(
        work.loc[work["_depth"] == parent_depth, "assignment"]
    )

    parent_prefix = _common_assignment_prefix(list(parents))
    child_assignments = work.loc[
        work["_depth"] == child_depth, "assignment"
    ].tolist()
    child_prefix = _common_assignment_prefix(child_assignments)

    rows = []

    for _, row in work.iterrows():
        assignment = row["assignment"]
        depth = row["_depth"]

        if depth == parent_depth:
            rows.append({
                "assignment": assignment,
                "assignment_suffix": assignment[len(parent_prefix):].lstrip("."),
                "period": row.get("period"),
                "year": row.get("year"),
                "value": row["amount"],
                "role": "parent",
                "parent_assignment": None,
            })
        else:
            parent = assignment.rsplit(".", 1)[0]
            rows.append({
                "assignment": assignment,
                "assignment_suffix": assignment[len(child_prefix):].lstrip("."),
                "period": row.get("period"),
                "year": row.get("year"),
                "value": row["amount"],
                "role": "child",
                "parent_assignment": parent,
            })

    return {"mode": "stacked", "rows": rows}


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
