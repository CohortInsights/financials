"""
remove_transactions.py

Delete transactions (and their related rule_matches / transaction_assignments)
based on CLI filters for source, year, and description substring.
"""

import argparse
import logging
from typing import List, Dict, Any
from financials.utils.helpers import build_txn_query

from financials import db as db_module


logger = logging.getLogger(__name__)


def remove_transactions_from_collections(txn_ids: List[str]) -> Dict[str, int]:
    """
    Given a list of transaction IDs (the `id` field in `transactions`),
    remove them from:

    - transactions             (field: id)
    - rule_matches             (field: txn_id)
    - transaction_assignments  (field: txn_id)

    Returns a dict of deleted counts per collection.
    """
    db = db_module.db

    results: Dict[str, int] = {}

    if not txn_ids:
        logger.info("No transaction IDs provided; nothing to delete.")
        return results

    # transactions
    tx_coll = db["transactions"]
    res_tx = tx_coll.delete_many({"id": {"$in": txn_ids}})
    results["transactions"] = res_tx.deleted_count
    logger.info("Deleted %d documents from 'transactions'.", res_tx.deleted_count)

    # rule_matches
    rm_coll = db["rule_matches"]
    res_rm = rm_coll.delete_many({"txn_id": {"$in": txn_ids}})
    results["rule_matches"] = res_rm.deleted_count
    logger.info("Deleted %d documents from 'rule_matches'.", res_rm.deleted_count)

    # transaction_assignments
    ta_coll = db["transaction_assignments"]
    res_ta = ta_coll.delete_many({"id": {"$in": txn_ids}})
    results["transaction_assignments"] = res_ta.deleted_count
    logger.info(
        "Deleted %d documents from 'transaction_assignments'.",
        res_ta.deleted_count,
    )

    return results


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove transactions (and related rule_matches / transaction_assignments) "
            "by source/year/description."
        )
    )

    parser.add_argument(
        "--source",
        help="Filter by transactions.source (exact match).",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Filter by transaction date year (e.g., 2025).",
    )
    parser.add_argument(
        "--desc",
        help="Case-insensitive substring match on transactions.description.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matching transactions but do not delete anything.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Apply to ALL transactions (unsafe unless intentional).",
    )

    args = parser.parse_args()
    return args


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    args = _parse_args()
    db = db_module.db
    tx_coll = db["transactions"]

    query = build_txn_query(args)

    # Allow empty query ONLY if --all is specified
    if not query and not args.all:
        logger.error(
            "Refusing to run with an empty query. "
            "Use --all to operate on ALL transactions."
        )
        return

    if args.all:
        logger.warning("⚠️  --all specified: operating on ALL transactions!")
        # If --all is set, ignore any filters that might have been built?
        # Current behavior: if filters were provided, they still apply.
        # If you want --all to truly mean ALL, uncomment the next line:
        # query = {}

    logger.info("Querying transactions with filter: %s", query)

    # Pull a small projection so we can show what's being deleted
    cursor = tx_coll.find(
        query,
        {
            "id": 1,
            "date": 1,
            "source": 1,
            "description": 1,
            "amount": 1,
        },
    )

    matches = list(cursor)
    if not matches:
        logger.info("No matching transactions found. Nothing to do.")
        return

    logger.info("Found %d matching transactions:", len(matches))
    for doc in matches:
        logger.info(
            "  id=%s | date=%s | source=%s | amount=%s | desc=%s",
            doc.get("id"),
            doc.get("date"),
            doc.get("source"),
            doc.get("amount"),
            doc.get("description"),
        )

    txn_ids = [doc.get("id") for doc in matches if doc.get("id") is not None]
    if not txn_ids:
        logger.warning(
            "Matching documents did not contain 'id' fields. "
            "Aborting to avoid deleting by _id incorrectly."
        )
        return

    logger.info("Collected %d transaction IDs for deletion.", len(txn_ids))

    if args.dry_run:
        logger.info(
            "Dry run enabled. No deletions performed. "
            "Re-run without --dry-run to actually delete."
        )
        return

    logger.info("Deleting transactions and related documents...")
    results = remove_transactions_from_collections(txn_ids)

    logger.info("Deletion summary: %s", results)


if __name__ == "__main__":
    main()
