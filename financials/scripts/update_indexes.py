# financials/scripts/update_indexes.py
"""
Ensure MongoDB indexes exist for Financials collections.
Safe to run multiple times — MongoDB will skip duplicates.

This version includes performance-oriented indexes to support
auto-assignment, bulk updates, and rule evaluation.
"""

from financials import db as db_module


def ensure_indexes():
    db = db_module.db
    print("🔧 Ensuring indexes for Financials database...")

    # ----------------------------------------------------------------------
    # transactions collection
    # ----------------------------------------------------------------------
    trx = db["transactions"]

    # Unique identifier for each transaction
    trx.create_index("id", unique=True)

    # Frequently filtered or sorted fields
    trx.create_index("assignment")
    trx.create_index("date")
    trx.create_index("source")
    trx.create_index("amount")

    # Compound index for common dashboard queries (source + assignment)
    trx.create_index([("source", 1), ("assignment", 1)])

    # ----------------------------------------------------------------------
    # transaction_assignments collection
    # ----------------------------------------------------------------------
    ta = db["transaction_assignments"]

    # Use "id" to match transaction linkage (not "transaction_id")
    ta.create_index("id")

    # Allow fast deletions of all auto records
    ta.create_index("type")

    # Allow efficient sort by recency for audits
    ta.create_index([("id", 1), ("timestamp", -1)])

    # ----------------------------------------------------------------------
    # assignment_rules collection
    # ----------------------------------------------------------------------
    rules = db["assignment_rules"]

    # Priority determines rule precedence
    rules.create_index("priority")

    # Support quick filtering of rules by source or description text
    rules.create_index("source")
    rules.create_index("description")

    # Compound index used when sorting or combining filters
    rules.create_index([("priority", -1), ("source", 1)])

    print("✅ Index verification complete.")


if __name__ == "__main__":
    ensure_indexes()
