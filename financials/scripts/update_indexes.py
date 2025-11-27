"""
Ensure MongoDB indexes exist for Financials collections.
Safe to run multiple times — MongoDB will skip duplicates.

This version includes performance-oriented indexes to support
auto-assignment, bulk updates, rule evaluation, and the new
rule_matches collection for incremental rule updates.
"""

import os
import csv
import argparse
import logging
from financials import db as db_module

logger = logging.getLogger(__name__)


def ensure_indexes():
    db = db_module.db
    logger.info("🔧 Ensuring indexes for Financials database...")

    # ----------------------------------------------------------------------
    # transactions collection
    # ----------------------------------------------------------------------
    trx = db["transactions"]

    trx.create_index("id", unique=True)
    trx.create_index("assignment")
    trx.create_index("date")
    trx.create_index("source")
    trx.create_index("amount")
    trx.create_index([("source", 1), ("assignment", 1)])

    # ----------------------------------------------------------------------
    # transaction_assignments collection
    # ----------------------------------------------------------------------
    ta = db["transaction_assignments"]
    ta.create_index("id")                    # lookup by transaction
    ta.create_index("type")                  # auto vs manual
    ta.create_index([("id", 1), ("timestamp", -1)])   # recency audit

    # ----------------------------------------------------------------------
    # assignment_rules collection
    # ----------------------------------------------------------------------
    rules = db["assignment_rules"]
    rules.create_index("priority")
    rules.create_index("source")
    rules.create_index("description")
    rules.create_index([("priority", -1), ("source", 1)])

    # ----------------------------------------------------------------------
    # rule_matches collection
    # ----------------------------------------------------------------------
    rm = db["rule_matches"]

    # Fast lookup of all transactions affected by a given rule
    rm.create_index("rule_id")

    # Fast lookup of the winner rule for a given transaction
    rm.create_index("txn_id")

    # Needed for computing “highest priority rule per txn”
    rm.create_index([("txn_id", 1), ("priority", -1)])

    # Efficient delete when rebuilding (rule edit/delete)
    rm.create_index([("rule_id", 1), ("txn_id", 1)])

    logger.info("✅ Index verification complete.")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    ensure_indexes()
