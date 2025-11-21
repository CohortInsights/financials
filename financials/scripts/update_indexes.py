# financials/scripts/update_indexes.py
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
from financials import db as db_module


def ensure_indexes():
    db = db_module.db
    print("🔧 Ensuring indexes for Financials database...")

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
    # NEW: rule_matches collection
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

    print("✅ Index verification complete.")


def install_google_type_rules():
    """
    Install rules based on financials/cfg/google_types_to_expenses.csv.
    For each row:
        priority     = 2
        source       = ""
        description  = google_type
        assignment   = assignment from CSV
    """
    db = db_module.db
    rules = db["assignment_rules"]

    cfg_path = os.path.join(
        os.path.dirname(__file__), "..", "cfg", "google_types_to_expenses.csv"
    )
    cfg_path = os.path.abspath(cfg_path)

    if not os.path.exists(cfg_path):
        print(f"⚠️ google_types_to_expenses.csv not found: {cfg_path}")
        return

    print(f"📥 Installing Google-type rules from {cfg_path}...")

    count = 0
    with open(cfg_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            google_type = row.get("google_type")
            assignment = row.get("assignment")

            if not google_type:
                continue

            rules.update_one(
                {"source": "", "description": google_type},
                {
                    "$set": {
                        "source": "",
                        "description": google_type,
                        "assignment": assignment,
                        "priority": 2,
                    }
                },
                upsert=True,
            )
            count += 1

    print(f"✅ Installed/updated {count} Google-type rules.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", action="store_true",
                        help="Install Google-type assignment rules from CSV")

    args = parser.parse_args()

    ensure_indexes()

    if args.rules:
        install_google_type_rules()
