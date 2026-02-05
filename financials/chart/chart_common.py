from pathlib import Path
import io


CFG_DIR = Path(__file__).resolve().parent / "cfg"


class ChartDataError(Exception):
    pass

class ChartConfigError(Exception):
    pass


def figure_to_bytes(fig, *, format: str = "png") -> bytes:
    """
    Convert a Matplotlib figure to raw bytes.

    No inference. No defaults beyond format.
    """
    buf = io.BytesIO()
    fig.savefig(buf, format=format)
    buf.seek(0)
    return buf.read()


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