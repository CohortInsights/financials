from flask import jsonify, request, Response
from datetime import datetime
import pandas as pd
import numpy as np

from financials import db as db_module
from financials.web import app


def respond_with_format(df: pd.DataFrame, filename: str):
    """
    Return df as JSON or CSV depending on ?format= argument.
    filename controls the CSV download name.
    """
    fmt = request.args.get("format", "json").lower()

    if fmt == "csv":
        csv_data = df.to_csv(index=False)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # JSON response
    return jsonify(df.to_dict(orient="records"))


def compute_transactions(args):
    transactions = db_module.db["transactions"]
    years_param = args.get("years")
    year_param = args.get("year")

    query = {}
    if years_param:
        year_list = [int(y) for y in years_param.split(",") if y.strip().isdigit()]
        if year_list:
            query = {"$expr": {"$in": [{"$year": "$date"}, year_list]}}
    elif year_param and year_param.isdigit():
        start = datetime(int(year_param), 1, 1)
        end = datetime(int(year_param) + 1, 1, 1)
        query = {"date": {"$gte": start, "$lt": end}}
    else:
        current_year = datetime.now().year
        query = {"$expr": {"$in": [{"$year": "$date"}, [current_year]]}}

    cursor = transactions.find(query, {"_id": 0})
    df = pd.DataFrame(list(cursor))

    if not df.empty:
        if "date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        if "amount" in df.columns:
            df["amount"] = df["amount"].fillna(0)

        # Replace NaN with empty strings for JSON safety
        df = df.replace({np.nan: ""})

    return df


def group_by_assignment_time_period(df: pd.DataFrame, args):
    """
    Group transactions by assignment and time period.

    Returns DataFrame with:
        period, assignment, count, amount, level
    """

    if df.empty:
        return df  # nothing to group

    duration = args.get("duration", "year").lower()

    # Ensure date is datetime
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Build the period column depending on duration
    if duration == "quarter":
        df["period"] = df["date"].dt.to_period("Q").astype(str)
        df["period"] = df["period"].str.replace("Q", "-Q", regex=False)

    elif duration == "month":
        df["period"] = df["date"].dt.to_period("M").astype(str)

    else:  # duration == "year" (default)
        df["period"] = df["date"].dt.year.astype(str)

    # Group
    grouped = (
        df.groupby(["period", "assignment"], dropna=False)
        .agg(
            count=("assignment", "size"),
            amount=("amount", "sum"),
        )
        .reset_index()
    )

    # Replace NaN assignment with empty string
    grouped["assignment"] = grouped["assignment"].fillna("")

    # Format to two decimal places
    grouped["amount"] = grouped["amount"].astype(float).round(2)

    # ----------------------------------------------------
    # ✅ NEW COLUMN: Level = number of dots + 1
    # ----------------------------------------------------
    grouped["level"] = grouped["assignment"].apply(
        lambda a: a.count(".") + 1 if a else 1
    )

    return grouped


@app.route("/api/transactions")
def api_transactions():
    df = compute_transactions(request.args)
    return respond_with_format(df, "transactions.csv")


@app.route("/api/assigned_transactions")
def assigned_transactions():
    df = compute_transactions(request.args)
    df = group_by_assignment_time_period(df, request.args)
    return respond_with_format(df, "assigned_transactions.csv")
