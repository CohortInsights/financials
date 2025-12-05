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


def _should_expand(args) -> bool:
    """
    Return True if the caller requested hierarchical expansion via ?expand=true/1/yes.
    """
    val = args.get("expand", "").strip().lower()
    return val in ("1", "true", "yes", "y")


def group_by_assignment_time_period(df: pd.DataFrame, args):
    """
    Group transactions by assignment and time period.

    Returns DataFrame with:
        period, assignment, count, amount, level

    If ?expand=true is present, also adds hierarchical roll-up rows:
    - For each assignment like A.B.C (level 3), aggregates into parent A.B (level 2)
    - For each assignment like A.B (level 2), aggregates into parent A (level 1)
    - Stops at level 1 (no level-0 empty-assignment row)
    - If a parent already exists, child totals are ADDED to it
      (count += sum(children.count), amount += sum(children.amount))
    - If a parent does not exist, it is created.
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

    # Level = number of dots + 1; treat empty assignment as level 1
    grouped["level"] = grouped["assignment"].apply(
        lambda a: a.count(".") + 1 if a else 1
    )

    # Normalize amount to exactly 2 decimal places
    grouped["amount"] = grouped["amount"].astype(float).round(2)

    # ----------------------------------------------------
    # Optional hierarchical expansion: ?expand=true
    # ----------------------------------------------------
    if _should_expand(args):
        # Work from deepest level down to level 2, rolling up into parents
        max_level = int(grouped["level"].max())

        # We never generate level 0 parents; stop when we have produced level 1.
        for level in range(max_level, 1, -1):
            # Children at this level
            children = grouped[grouped["level"] == level].copy()
            if children.empty:
                continue

            # Derive parent assignment by stripping the last segment after '.'
            # e.g. "Expense.Auto.Fuel" -> "Expense.Auto"
            # Only rows that actually have a dot can produce parents
            mask_has_dot = children["assignment"].str.contains(r"\.")
            children = children[mask_has_dot].copy()
            if children.empty:
                continue

            children["parent_assignment"] = (
                children["assignment"]
                .str.rsplit(".", n=1, expand=True)
                .iloc[:, 0]
            )

            # Aggregate by (period, parent_assignment)
            parent_agg = (
                children.groupby(["period", "parent_assignment"], as_index=False)
                .agg(
                    count=("count", "sum"),
                    amount=("amount", "sum"),
                )
            )

            # For each parent, either update existing row or create a new one
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
                    # Add to existing parent
                    grouped.loc[existing_mask, "count"] = (
                        grouped.loc[existing_mask, "count"] + add_count
                    )
                    grouped.loc[existing_mask, "amount"] = (
                        grouped.loc[existing_mask, "amount"] + add_amount
                    )
                else:
                    # Create new parent row
                    parent_level = parent_assignment.count(".") + 1 if parent_assignment else 1
                    new_row = {
                        "period": period,
                        "assignment": parent_assignment,
                        "count": add_count,
                        "amount": add_amount,
                        "level": parent_level,
                    }
                    grouped = pd.concat(
                        [grouped, pd.DataFrame([new_row])],
                        ignore_index=True,
                    )

        # Re-normalize amount after roll-ups
        grouped["amount"] = grouped["amount"].astype(float).round(2)

    # Final sort: level (outer), then assignment (inner)
    grouped = grouped.sort_values(["level", "assignment"]).reset_index(drop=True)

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
