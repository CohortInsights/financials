from flask import jsonify, request, Response
from datetime import datetime
import pandas as pd
import numpy as np

from financials import db as db_module
from financials.web import app


# ------------------------------------------
# NEW HELPERS FOR PERIOD SORTING
# ------------------------------------------
def extract_year(period_str: str) -> int:
    """Extract numeric year from '2025', '2025-Q1', '2025-01'."""
    try:
        return int(period_str[:4])
    except Exception:
        return 0


def extract_period(period_str: str) -> int:
    """
    Convert quarter or month into sortable integer:
        Q1 → 1, Q2 → 2 ...
        2025-01 → 1, 2025-12 → 12
        Year-only (e.g. '2025') → 0
    """
    if "Q" in period_str:
        try:
            return int(period_str.split("Q")[1])
        except Exception:
            return 0

    # Monthly pattern YYYY-MM
    parts = period_str.split("-")
    if len(parts) == 2 and parts[1].isdigit():
        try:
            return int(parts[1])
        except Exception:
            return 0

    return 0


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


def _should_expand(args) -> bool:
    """
    Return True if the caller requested hierarchical expansion via ?expand=true/1/yes.
    """
    val = args.get("expand", "").strip().lower()
    return val in ("1", "true", "yes", "y")


def group_by_assignment_time_period(df: pd.DataFrame, args):
    """
    Group transactions by assignment and time period.
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

    else:  # duration == "year"
        df["period"] = df["date"].dt.year.astype(str)

    # Base grouping: period + assignment
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

    # Level = number of dots + 1; empty assignment → level 1
    grouped["level"] = grouped["assignment"].apply(
        lambda a: a.count(".") + 1 if a else 1
    )

    # Normalize amount
    grouped["amount"] = grouped["amount"].astype(float).round(2)

    # Hierarchical roll-up if expand=true
    if _should_expand(args):
        max_level = int(grouped["level"].max())

        for level in range(max_level, 1, -1):
            children = grouped[grouped["level"] == level].copy()
            if children.empty:
                continue

            mask_has_dot = children["assignment"].str.contains(r"\.")
            children = children[mask_has_dot].copy()
            if children.empty:
                continue

            children["parent_assignment"] = (
                children["assignment"]
                .str.rsplit(".", n=1, expand=True)
                .iloc[:, 0]
            )

            parent_agg = (
                children.groupby(["period", "parent_assignment"], as_index=False)
                .agg(
                    count=("count", "sum"),
                    amount=("amount", "sum"),
                )
            )

            for _, row in parent_agg.iterrows():
                period = row["period"]
                parent_assignment = row["parent_assignment"]
                add_count = row["count"]
                add_amount = float(row["amount"])

                existing_mask = (
                    (grouped["period"] == period)
                    & (grouped["assignment"] == parent_assignment)
                )

                if existing_mask.any():
                    grouped.loc[existing_mask, "count"] += add_count
                    grouped.loc[existing_mask, "amount"] += add_amount
                else:
                    parent_level = parent_assignment.count(".") + 1 if parent_assignment else 1
                    new_row = {
                        "period": period,
                        "assignment": parent_assignment,
                        "count": add_count,
                        "amount": add_amount,
                        "level": parent_level,
                    }
                    grouped = pd.concat([grouped, pd.DataFrame([new_row])], ignore_index=True)

        grouped["amount"] = grouped["amount"].astype(float).round(2)

    # ----------------------------------------------------
    # NEW LOGIC: compute assignment_amount_sum using ABS(amount)
    # ----------------------------------------------------
    total_amount_by_assignment = grouped.groupby("assignment")["amount"].apply(lambda s: s.abs().sum())
    grouped["assignment_amount_sum"] = grouped["assignment"].map(total_amount_by_assignment)

    # ----------------------------------------------------
    # Existing tmp_year / tmp_period logic
    # ----------------------------------------------------
    grouped["tmp_year"]   = grouped["period"].apply(extract_year)
    grouped["tmp_period"] = grouped["period"].apply(extract_period)

    # ----------------------------------------------------
    # FINAL SORT ORDER (your specification):
    #   tmp_period
    #   assignment_amount_sum (DESC)
    #   tmp_year
    # ----------------------------------------------------
    grouped = grouped.sort_values(
        ["tmp_period", "assignment_amount_sum", "tmp_year"],
        ascending=[True, False, True]
    ).reset_index(drop=True)

    # ----------------------------------------------------
    # Remove temporary columns
    # ----------------------------------------------------
    grouped = grouped.drop(columns=["assignment_amount_sum", "tmp_year", "tmp_period"])

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
