from typing import Dict, Any, List
import json
from pathlib import Path

# ------------------------------------------------------------------
# Chart spec loading
# ------------------------------------------------------------------

CFG_DIR = Path(__file__).resolve().parent / "cfg"


def load_chart_spec(chart_type: str) -> dict:
    path = CFG_DIR / f"{chart_type}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown chart type: {chart_type}")
    with open(path, "r") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Eligibility evaluation
# ------------------------------------------------------------------

def evaluate_eligibility(
    *,
    chart_type: str,
    meta: Dict[str, Any],
) -> tuple[dict, dict]:
    """
    Evaluate eligibility rules for a chart type.

    Returns:
        allowed_result : dict
            {
              "chart_type": str,
              "eligible": bool,
              "reasons": [str, ...],     # only if not eligible
              "rule_keys": [str, ...]    # only if not eligible
            }
        chart_spec : dict
            Resolved chart configuration (JSON, later Mongo-overlaid)
    """

    chart_spec = load_chart_spec(chart_type)
    eligibility = chart_spec.get("eligibility", {})
    disallowed_map = chart_spec.get("disallowed_reasons", {})

    reasons: List[str] = []
    rule_keys: List[str] = []

    # ---- Rule: major level must exist (>=2 distinct assignments) ----
    if eligibility.get("requires_major_level"):
        if meta.get("major_assignment_count", 0) < 2:
            rule_keys.append("no_major_level")
            reasons.append(
                disallowed_map.get(
                    "no_major_level",
                    "Insufficient number of distinct assignments"
                )
            )

    # ---- Rule: forbid minor levels ----
    if eligibility.get("forbids_minor_levels"):
        if meta.get("minor_levels"):
            rule_keys.append("minor_levels_present")
            reasons.append(
                disallowed_map.get(
                    "minor_levels_present",
                    "Minor levels are present"
                )
            )

    # ---- Rule: exactly one year ----
    if eligibility.get("requires_single_year"):
        if meta.get("sort_year_count", 0) != 1:
            rule_keys.append("multiple_years")
            reasons.append(
                disallowed_map.get(
                    "multiple_years",
                    "Multiple years are present"
                )
            )

    # ---- Rule: exactly one period ----
    if eligibility.get("requires_single_period"):
        if meta.get("sort_period_count", 0) != 1:
            rule_keys.append("multiple_periods")
            reasons.append(
                disallowed_map.get(
                    "multiple_periods",
                    "Multiple periods are present"
                )
            )

    # ---- Rule: same-sign only ----
    if eligibility.get("requires_same_sign"):
        if meta.get("sign") == "mixed":
            rule_keys.append("mixed_sign")
            reasons.append(
                disallowed_map.get(
                    "mixed_sign",
                    "Mixed positive and negative values are present"
                )
            )

    allowed_result = {
        "chart_type": chart_type,
        "eligible": not reasons
    }

    if reasons:
        allowed_result["reasons"] = reasons
        allowed_result["rule_keys"] = rule_keys

    return allowed_result, chart_spec
