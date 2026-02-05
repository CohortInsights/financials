import json
from pathlib import Path
import pandas as pd
from financials.routes.api_transactions import compute_assignments


CFG_DIR = Path(__file__).resolve().parent / "cfg"


class ChartDataError(Exception):
    pass

class ChartConfigError(Exception):
    pass


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