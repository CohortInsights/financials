#!/usr/bin/env python3
"""
delete_entries.py — safely remove transactions for a given source,
optionally restricted to a specific year.

Usage:
    poetry run python -m financials.scripts.delete_entries --source bmo
    poetry run python -m financials.scripts.delete_entries --source paypal --year 2026
"""

import argparse
import logging
import sys
from datetime import datetime
from financials import db as db_module


def build_match_filter(source: str, year: int | None) -> dict:
    """
    Build a MongoDB match filter for source and optional year.
    Assumes transactions have a 'date' field of type datetime.
    """
    match_filter = {
        "source": {"$regex": f"^{source}$", "$options": "i"}
    }

    if year is not None:
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        match_filter["date"] = {"$gte": start, "$lt": end}

    return match_filter


def delete_transactions(match_filter: dict) -> tuple[int, int]:
    """
    Deletes matching transactions and associated entries
    in transaction_assignments.

    Returns:
        (deleted_transactions_count, deleted_assignments_count)
    """
    transactions = db_module.db["transactions"]
    assignments = db_module.db["transaction_assignments"]

    txn_ids = [
        doc["_id"]
        for doc in transactions.find(match_filter, {"_id": 1})
    ]

    if not txn_ids:
        return (0, 0)

    txn_delete_result = transactions.delete_many({"_id": {"$in": txn_ids}})
    deleted_txn_count = txn_delete_result.deleted_count

    # IMPORTANT: field name is "id", not "transaction_id"
    assign_delete_result = assignments.delete_many({"id": {"$in": txn_ids}})
    deleted_assign_count = assign_delete_result.deleted_count

    return (deleted_txn_count, deleted_assign_count)


def main():
    parser = argparse.ArgumentParser(
        description="Delete transactions and assignment history for a specific source, optionally by year."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source name to delete (e.g., bmo, schwab, paypal, citi). Case-insensitive.",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Restrict deletion to a specific calendar year (e.g., 2026).",
    )
    args = parser.parse_args()

    source = args.source.strip()
    year = args.year

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logger = logging.getLogger("delete_entries")

    transactions = db_module.db["transactions"]

    match_filter = build_match_filter(source, year)
    match_count = transactions.count_documents(match_filter)

    if match_count == 0:
        if year:
            logger.warning(
                f"⚠️  No records found for source='{source}' in year {year}. Nothing to delete."
            )
        else:
            logger.warning(
                f"⚠️  No records found where source='{source}'. Nothing to delete."
            )
        sys.exit(0)

    scope_desc = (
        f"source='{source}', year={year}"
        if year
        else f"source='{source}' (all years)"
    )

    logger.info(f"🔍 Found {match_count} transactions for {scope_desc}.")

    confirm = input(
        f"⚠️  This will permanently delete {match_count} transactions "
        f"AND their assignment history for {scope_desc}. Continue? (yes/no): "
    ).strip().lower()

    if confirm not in {"yes", "y"}:
        logger.info("Operation cancelled.")
        sys.exit(0)

    deleted_txn_count, deleted_assign_count = delete_transactions(match_filter)

    logger.info(f"🧹 Deleted {deleted_txn_count} transactions.")
    logger.info(f"🧽 Deleted {deleted_assign_count} associated assignment records.")

    remaining = transactions.count_documents(match_filter)
    if remaining > 0:
        logger.warning(
            f"⚠️  {remaining} transaction records still remain for {scope_desc}."
        )
    else:
        logger.info(f"✅ Verification passed: no remaining transactions for {scope_desc}.")


if __name__ == "__main__":
    main()
