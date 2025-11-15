#!/usr/bin/env python3
"""
delete_entries.py — safely remove all transactions for a given source.

Usage:
    poetry run python -m financials.scripts.delete_entries --source bmo
"""

import argparse
import logging
import sys
from financials import db as db_module


def delete_source_transactions(source: str) -> tuple[int, int]:
    """
    Deletes all transactions for the given source (case-insensitive)
    and deletes associated entries in transaction_assignments.

    Returns:
        (deleted_transactions_count, deleted_assignments_count)
    """
    transactions = db_module.db["transactions"]
    assignments = db_module.db["transaction_assignments"]

    # Find all matching transaction IDs
    match_filter = {"source": {"$regex": f"^{source}$", "$options": "i"}}
    txn_ids = [doc["_id"] for doc in transactions.find(match_filter, {"_id": 1})]
    if not txn_ids:
        return (0, 0)

    # Delete transactions
    txn_delete_result = transactions.delete_many({"_id": {"$in": txn_ids}})
    deleted_txn_count = txn_delete_result.deleted_count

    # Delete associated assignment records
    # IMPORTANT: field name is "id", not "transaction_id"
    assign_delete_result = assignments.delete_many({"id": {"$in": txn_ids}})
    deleted_assign_count = assign_delete_result.deleted_count

    return (deleted_txn_count, deleted_assign_count)


def main():
    parser = argparse.ArgumentParser(
        description="Delete all transactions and assignment history for a specific source."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source name to delete (e.g., bmo, schwab, paypal, citi). Case-insensitive.",
    )
    args = parser.parse_args()
    source = args.source.strip()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("delete_entries")

    transactions = db_module.db["transactions"]

    # Count matching documents (case-insensitive)
    match_filter = {"source": {"$regex": f"^{source}$", "$options": "i"}}
    match_count = transactions.count_documents(match_filter)

    if match_count == 0:
        logger.warning(f"⚠️  No records found where source='{source}'. Nothing to delete.")
        sys.exit(0)

    logger.info(f"🔍 Found {match_count} transactions with source='{source}'.")

    confirm = input(
        f"⚠️  This will permanently delete all {match_count} transactions AND their assignment history. Continue? (yes/no): "
    ).strip().lower()
    if confirm not in {"yes", "y"}:
        logger.info("Operation cancelled.")
        sys.exit(0)

    # Perform deletion
    deleted_txn_count, deleted_assign_count = delete_source_transactions(source)

    logger.info(f"🧹 Deleted {deleted_txn_count} transactions for source '{source}'.")
    logger.info(f"🧽 Deleted {deleted_assign_count} associated assignment records.")

    # Verify nothing remains
    remaining = transactions.count_documents(match_filter)
    if remaining > 0:
        logger.warning(f"⚠️  {remaining} transaction records still remain for source='{source}'.")
    else:
        logger.info(f"✅ Verification passed: no remaining '{source}' transactions.")


if __name__ == "__main__":
    main()
