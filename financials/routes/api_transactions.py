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

    parts = period_str.split("-")
    if len(parts) == 2 and parts[1].isdigit():
        try:
            return int(parts[1])
        except Exception:
            return 0

    return 0


def _should_zero_fill(args) -> bool:
    """
    Return True if the caller requested zero-fill via ?zero-fill=true/1/yes.
    """
    val = args.get("zero-fill", "").strip().lower()
    return val in ("1", "true", "yes", "y")


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

        df = df.replace({np.nan: ""})

    return df


def compute_transaction_years() -> list[int]:
    """
    Return distinct transaction years, sorted descending.
    """
    transactions = db_module.db["transactions"]

    cursor = transactions.aggregate([
        {"$project": {"year": {"$year": "$date"}}},
        {"$group": {"_id": "$year"}},
        {"$sort": {"_id": -1}},
    ])

    return [doc["_id"] for doc in cursor if doc.get("_id") is not None]


def compute_assignment_meta(df):
    """
    Compute derived meta information from a filtered assignment table.
    """
    if df.empty:
        return {
            "major_level": None,
            "minor_levels": [],
            "major_assignment_count": 0,
            "sort_year_count": 0,
            "sort_period_count": 0,
            "sign": "none"
        }

    level_assignment_counts = (
        df.groupby("level")["assignment"]
        .nunique()
        .sort_index()
    )

    major_level = None
    for lvl, cnt in level_assignment_counts.items():
        if cnt > 1:
            major_level = lvl
            break

    minor_levels = []
    if major_level is not None:
        minor_levels = [
            lvl for lvl in level_assignment_counts.index
            if lvl > major_level
        ]

    if major_level is not None:
        major_assignment_count = (
            df[df["level"] == major_level]["assignment"].nunique()
        )
    else:
        major_assignment_count = df["assignment"].nunique()

    sort_year_count = df["sort_year"].nunique()
    sort_period_count = df["sort_period"].nunique()

    amounts = df["amount"]
    has_positive = (amounts > 0).any()
    has_negative = (amounts < 0).any()

    if has_positive and has_negative:
        sign = "mixed"
    elif has_positive:
        sign = "positive"
    elif has_negative:
        sign = "negative"
    else:
        sign = "zero"

    return {
        "major_level": major_level,
        "minor_levels": minor_levels,
        "major_assignment_count": major_assignment_count,
        "sort_year_count": sort_year_count,
        "sort_period_count": sort_period_count,
        "sign": sign
    }


def compute_assignments(args, *, filters=None, zero_fill=False) -> tuple[pd.DataFrame, dict]:
    """
    Compute the canonical assignment table and its derived metadata.
    """
    df = compute_transactions(args)
    df = group_by_assignment_time_period(df, args)

    if filters:
        asn = filters.get("asn")
        level = filters.get("level")

        if asn:
            tokens = [
                t.strip().lower()
                for t in asn.split(",")
                if t.strip()
            ]
            if tokens:
                df = df[
                    df["assignment"]
                    .str.lower()
                    .apply(lambda s: any(tok in s for tok in tokens))
                ]

        if level:
            levels = {
                int(t.strip())
                for t in level.split(",")
                if t.strip().isdigit()
            }
            if levels:
                df = df[df["level"].isin(levels)]

    # Meta must describe the FINAL dataset
    meta = compute_assignment_meta(df)

    # ---------------------------------------------
    # ZERO-FILL (explicit, chart-oriented)
    # ---------------------------------------------
    if zero_fill:
        df = zero_fill_assignment_periods(df, meta)

    return df, meta


def zero_fill_assignment_periods(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """
    Zero-fill missing (assignment, sort_year, sort_period) combinations
    for time-series data only.

    This is a view-normalization step intended for charting.
    """

    # -------------------------------------------------
    # EARLY EXIT: not a time series
    # -------------------------------------------------
    if (
            meta.get("sort_year_count", 0) <= 1
            and meta.get("sort_period_count", 0) <= 1
    ):
        return df

    if df.empty:
        return df

    # -------------------------------------------------
    # Build full index of expected combinations
    # -------------------------------------------------
    assignments = (
        df[["assignment", "level"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    periods = (
        df[["sort_year", "sort_period", "period"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    full_index = assignments.merge(periods, how="cross")

    # -------------------------------------------------
    # Merge existing data onto full index
    # -------------------------------------------------
    merged = full_index.merge(
        df,
        on=["assignment", "level", "sort_year", "sort_period", "period"],
        how="left",
    )

    # -------------------------------------------------
    # Fill missing values
    # -------------------------------------------------
    merged["count"] = merged["count"].fillna(0).astype(int)
    merged["amount"] = merged["amount"].fillna(0.0).astype(float)

    return merged


def _should_expand(args) -> bool:
    val = args.get("expand", "").strip().lower()
    return val in ("1", "true", "yes", "y")


def group_by_assignment_time_period(df: pd.DataFrame, args):
    """
    Group transactions by assignment and time period.
    """
    if df.empty:
        return df

    duration = args.get("duration", "year").lower()

    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if duration == "quarter":
        df["period"] = df["date"].dt.to_period("Q").astype(str)
        df["period"] = df["period"].str.replace("Q", "-Q", regex=False)
    elif duration == "month":
        df["period"] = df["date"].dt.to_period("M").astype(str)
    else:
        df["period"] = df["date"].dt.year.astype(str)

    grouped = (
        df.groupby(["period", "assignment"], dropna=False)
        .agg(
            count=("assignment", "size"),
            amount=("amount", "sum"),
        )
        .reset_index()
    )

    grouped["assignment"] = grouped["assignment"].fillna("")
    grouped["level"] = grouped["assignment"].apply(
        lambda a: a.count(".") + 1 if a else 1
    )
    grouped["amount"] = grouped["amount"].astype(float).round(2)

    if _should_expand(args):
        max_level = int(grouped["level"].max())
        for level in range(max_level, 1, -1):
            children = grouped[grouped["level"] == level].copy()
            if children.empty:
                continue

            children = children[children["assignment"].str.contains(r"\.")]
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
                mask = (
                        (grouped["period"] == row["period"]) &
                        (grouped["assignment"] == row["parent_assignment"])
                )
                if mask.any():
                    grouped.loc[mask, "count"] += row["count"]
                    grouped.loc[mask, "amount"] += row["amount"]
                else:
                    grouped = pd.concat([
                        grouped,
                        pd.DataFrame([{
                            "period": row["period"],
                            "assignment": row["parent_assignment"],
                            "count": row["count"],
                            "amount": row["amount"],
                            "level": row["parent_assignment"].count(".") + 1
                        }])
                    ], ignore_index=True)

        grouped["amount"] = grouped["amount"].astype(float).round(2)

    total_amount_by_assignment = (
        grouped.groupby("assignment")["amount"]
        .apply(lambda s: s.abs().sum())
    )
    grouped["assignment_amount_sum"] = grouped["assignment"].map(total_amount_by_assignment)

    # Canonical sort fields (persisted internally)
    grouped["sort_year"] = grouped["period"].apply(extract_year)
    grouped["sort_period"] = grouped["period"].apply(extract_period)

    grouped = grouped.sort_values(
        ["level","sort_period", "assignment_amount_sum", "sort_year"],
        ascending=[True, True, False, True]
    ).reset_index(drop=True)

    # Drop only non-canonical helper
    grouped = grouped.drop(columns=["assignment_amount_sum"])

    return grouped


@app.route("/api/transactions")
def api_transactions():
    df = compute_transactions(request.args)
    return respond_with_format(df, "transactions.csv")


@app.route("/api/assigned_transactions")
def assigned_transactions():
    df,meta = compute_assignments(request.args)
    df.drop(columns=["sort_year", "sort_period"], inplace=True, errors="ignore")

    return respond_with_format(df, "assigned_transactions.csv")


@app.route("/api/assignment_meta")
def api_assignment_meta():
    filters = {
        "asn": request.args.get("asn"),
        "level": request.args.get("level"),
    }

    df,meta = compute_assignments(
        request.args,
        filters=filters,
        zero_fill=False
    )

    return jsonify(meta)


@app.route("/api/filtered_assignments")
def api_filtered_assignments():
    filters = {
        "asn": request.args.get("asn"),
        "level": request.args.get("level"),
    }

    df,meta = compute_assignments(
        request.args,
        filters=filters,
        zero_fill=_should_zero_fill(request.args)
    )

    return respond_with_format(df, "filtered_assignments.csv")

@app.route("/api/transaction_years")
def api_transaction_years():
    years = compute_transaction_years()
    return jsonify({"years": years})

