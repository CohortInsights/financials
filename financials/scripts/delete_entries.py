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


def main():
    parser = argparse.ArgumentParser(
        description="Delete all transactions from MongoDB for a specific source."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source name to delete (e.g., bmo, schwab, paypal, citi). Case-insensitive.",
    )
    # Optional dry-run flag (uncomment if desired later)
    # parser.add_argument("--dry-run", action="store_true", help="Preview records to be deleted without removing them.")
    args = parser.parse_args()
    source = args.source.strip()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("delete_entries")

    transactions = db_module.db["transactions"]

    # Find all matching documents (case-insensitive)
    match_filter = {"source": {"$regex": f"^{source}$", "$options": "i"}}
    match_count = transactions.count_documents(match_filter)

    if match_count == 0:
        logger.warning(f"⚠️  No records found where source='{source}'. Nothing to delete.")
        sys.exit(0)

    logger.info(f"🔍 Found {match_count} records with source='{source}'.")

    confirm = input(
        f"⚠️  This will permanently delete all {match_count} transactions where source='{source}'. Continue? (yes/no): "
    ).strip().lower()
    if confirm not in {"yes", "y"}:
        logger.info("Operation cancelled.")
        sys.exit(0)

    # Perform deletion
    result = transactions.delete_many(match_filter)
    deleted = result.deleted_count

    if deleted > 0:
        logger.info(f"🧹 Successfully deleted {deleted} '{source}' documents from collection 'transactions'.")
    else:
        logger.warning(f"⚠️  No documents deleted (possible concurrent change or mismatched case).")

    # Optionally, you could log what remains
    remaining = transactions.count_documents(match_filter)
    if remaining > 0:
        logger.warning(f"⚠️  {remaining} documents still remain for source='{source}'.")
    else:
        logger.info(f"✅ Verification passed: no remaining '{source}' records in collection.")


if __name__ == "__main__":
    main()
