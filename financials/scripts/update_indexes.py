# financials/scripts/ensure_indexes.py
"""
Ensure MongoDB indexes exist for Financials collections.
This script can be safely run multiple times; MongoDB ignores duplicates.
"""

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
    trx.create_index([("source", 1), ("assignment", 1)])  # optional compound

    # ----------------------------------------------------------------------
    # transaction_assignments collection
    # ----------------------------------------------------------------------
    ta = db["transaction_assignments"]
    ta.create_index("transaction_id")
    ta.create_index("type")
    ta.create_index([("transaction_id", 1), ("timestamp", -1)])

    # ----------------------------------------------------------------------
    # assignment_rules collection
    # ----------------------------------------------------------------------
    rules = db["assignment_rules"]
    rules.create_index("priority")
    rules.create_index("active")
    rules.create_index([("priority", -1), ("active", 1)])

    print("✅ Index verification complete.")


if __name__ == "__main__":
    ensure_indexes()
