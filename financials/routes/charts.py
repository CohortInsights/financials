from flask import request, jsonify

from financials.routes.api_transactions import compute_assignments
from financials.web import app
from pandas import DataFrame


from flask import Response
from financials.chart.chart_data import compute_chart_elements, compute_figure_data

from financials.chart.chart_common import (
    ChartDataError,
    ChartConfigError,
    figure_to_bytes
)

from financials.chart.chart_render import render_pies

def compute_chart_data(args: dict) -> DataFrame:
    chart_type = args.get("chart")
    if not chart_type:
        return jsonify({"error": "Missing chart parameter"}), 400

    filters = {
        "asn": args.get("asn"),
        "level": args.get("level"),
    }

    txn_args = args.copy()
    txn_args["expand"] = "1"

    source_data, meta = compute_assignments(args=txn_args, filters=filters)

    if not isinstance(source_data, DataFrame):
        raise ChartDataError("compute_assignments did not return DataFrame")

    cfg = {
        "min_frac": 0.05
    }

    chart_data: DataFrame = compute_chart_elements(
        source_data=source_data,
        chart_type=chart_type,
        cfg=cfg
    )
    return chart_data

@app.route("/api/charts/data")
def api_chart_data():
    try:
        args = request.args.to_dict()
        chart_data = compute_chart_data(args)

        return Response(
            chart_data.to_csv(index=False),
            mimetype="text/csv",
        )

    except ChartDataError as e:
        return jsonify({
            "chart": args.get("chart"),
            "error": str(e),
        }), 400

    except ChartConfigError as e:
        return jsonify({
            "chart": args,
            "error": str(e),
        }), 500


@app.route("/api/charts/figures")
def api_figure_data():
    try:
        args = request.args.to_dict()
        chart_data = compute_chart_data(args)
        figure_data = compute_figure_data(chart_data,args.get("chart"),cfg={})

        return Response(
            figure_data.to_csv(index=False),
            mimetype="text/csv",
        )

    except ChartDataError as e:
        return jsonify({
            "chart": args.get("chart"),
            "error": str(e),
        }), 400

    except ChartConfigError as e:
        return jsonify({
            "chart": args,
            "error": str(e),
        }), 500


@app.route("/api/charts/render")
def api_chart_render():
    figure = None

    def get_chart_name(args):
        name = ""
        key_list = ['chart','asn','years','duration']
        for key in key_list:
            if key in args:
                value = str(args[key])
                if len(name) > 0:
                    name += "_"
                name += value
        return name.lstrip("|")

    try:
        args = request.args.to_dict()
        chart_type = args.get("chart")

        chart_elements = compute_chart_data(args)
        fig_data = compute_figure_data(
            chart_elements=chart_elements,
            chart_type=chart_type,
            cfg={}
        )

        if "pie" in chart_type:
            figure = render_pies(
                chart_elements=chart_elements,
                figure_data=fig_data
            )

        if not figure:
            raise ChartDataError("compute_figure_data did not return a figure")

        png_bytes: bytes = figure_to_bytes(figure, format="png")

        # Optional download behavior
        download = args.get("download", "false").lower() == "true"

        headers = {}
        if download:
            filename = f"{get_chart_name(args)}.png"
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'

        return Response(
            png_bytes,
            mimetype="image/png",
            headers=headers,
        )

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
