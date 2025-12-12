from flask import request, jsonify
from financials.web import app
from financials.routes.api_transactions import compute_assignments
from financials.chart.chartlib import evaluate_eligibility


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
