from flask import jsonify, request
from datetime import datetime
import pandas as pd
import numpy as np
from financials import db as db_module
from financials.web import app


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
        df = df.replace({np.nan: ""})
    return df

def group_by_assignment_time_period(df: pd.DataFrame, args):
    """
    Group transactions by assignment and time period.

    Parameters
    ----------
    df : pd.DataFrame
        Transactions from compute_transactions (must contain 'date', 'assignment', 'amount')
    args : request.args
        Query parameters including 'year' and 'duration'

    Returns
    -------
    pd.DataFrame with columns:
        period, assignment, count, amount
    """

    if df.empty:
        return df  # nothing to group

    duration = args.get("duration", "year").lower()
    # year is useful for filtering but compute_transactions already did the filtering
    # we mostly need duration here

    # Ensure date is datetime
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Build the period column depending on duration
    if duration == "quarter":
        df["period"] = df["date"].dt.to_period("Q").astype(str)
        # converts to strings like "2025Q1" → convert to "2025-Q1"
        df["period"] = df["period"].str.replace("Q", "-Q", regex=False)

    elif duration == "month":
        df["period"] = df["date"].dt.to_period("M").astype(str)
        # Format becomes "2025-01", "2025-02", etc.

    else:  # duration == "year"  (default)
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

    # Replace NaN assignment with empty string for JSON safety
    grouped["assignment"] = grouped["assignment"].fillna("")

    return grouped


@app.route("/api/transactions")
def api_transactions():
    df = compute_transactions(request.args)
    return jsonify(df.to_dict(orient="records"))


@app.route("/api/assigned_transactions")
def assigned_transactions():
    df = compute_transactions(request.args)
    df = group_by_assignment_time_period(df, request.args)
    return jsonify(df.to_dict(orient="records"))
