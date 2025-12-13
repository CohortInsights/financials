from flask import request, jsonify
from financials.web import app
from financials.routes.api_transactions import compute_assignments
from financials.chart.chartlib import evaluate_eligibility

from flask import Response
from financials.chart.chartlib import (
    compute_chart,
    ChartNotAllowedError,
    ChartDataError,
    ChartConfigError,
)


@app.route("/api/charts/eligibility")
def api_chart_eligibility():
    chart_type = request.args.get("chart")
    if not chart_type:
        return jsonify({"error": "Missing chart parameter"}), 400

    filters = {
        "asn": request.args.get("asn"),
        "level": request.args.get("level"),
    }

    # Eligibility should see chart-normalized data
    df, meta = compute_assignments(
        request.args,
        filters=filters,
        zero_fill=True
    )

    result, chart_spec = evaluate_eligibility(chart_type=chart_type, meta=meta)

    eligible = result["eligible"]

    if eligible:
        return jsonify({
            "chart": chart_type,
            "eligible": eligible,
            "meta": meta   # keep for now; remove later if desired
        })
    else:
        return jsonify({
            "chart": chart_type,
            "eligible": eligible,
            "reasons": result["reasons"],
            "meta": meta   # keep for now; remove later if desired
        })


@app.route("/api/charts/render")
def api_chart_render():
    chart_type = request.args.get("chart")
    if not chart_type:
        return jsonify({"error": "Missing chart parameter"}), 400

    filters = {
        "asn": request.args.get("asn"),
        "level": request.args.get("level"),
    }

    try:
        png_bytes = compute_chart(
            chart_type=chart_type,
            args=request.args.to_dict(),
            filters=filters,
        )

        return Response(
            png_bytes,
            mimetype="image/png",
        )

    except ChartNotAllowedError as e:
        return jsonify({
            "chart": chart_type,
            "eligible": False,
            "reasons": e.eligibility_result.get("reasons", []),
        }), 400

    except ChartDataError as e:
        return jsonify({
            "chart": chart_type,
            "error": str(e),
        }), 400

    except ChartConfigError as e:
        return jsonify({
            "chart": chart_type,
            "error": str(e),
        }), 500
