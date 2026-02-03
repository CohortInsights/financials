from flask import request, jsonify

from financials.routes.api_transactions import compute_assignments
from financials.web import app
from pandas import DataFrame


from flask import Response
from financials.chart.chart_data import compute_chart_data
from financials.chart.chartlib import (
    compute_chart,
    ChartNotAllowedError,
    ChartDataError,
    ChartConfigError,
)

@app.route("/api/charts/data")
def api_chart_data():
    args = request.args.to_dict()

    chart_type = args.get("chart")
    if not chart_type:
        return jsonify({"error": "Missing chart parameter"}), 400

    filters = {
        "asn": args.get("asn"),
        "level": args.get("level"),
    }

    try:
        txn_args = args.copy()
        txn_args["expand"] = "1"

        source_data, meta = compute_assignments(args=txn_args, filters=filters)

        if not isinstance(source_data, DataFrame):
            raise ChartDataError("compute_assignments did not return DataFrame")

        cfg = {
            "min_frac" : 0.05
        }

        chart_data: DataFrame = compute_chart_data(
            source_data=source_data,
            chart_type=chart_type,
            cfg=cfg
        )

        return Response(
            chart_data.to_csv(index=False),
            mimetype="text/csv",
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
