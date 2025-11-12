# financials/assign_rules.py

"""
Assignment Rules Module
------------------------
Handles manual and automatic assignment of transactions.

Collections involved:
- transactions
- transaction_assignments  (audit of manual/auto assignments)
- assignment_rules         (definition of automatic rules)
"""

from datetime import datetime
from financials import db as db_module


# ----------------------------------------------------------------------
# MANUAL ASSIGNMENT
# ----------------------------------------------------------------------

def set_transaction_assignment(transaction_id: str, assignment: str) -> dict:
    """
    Updates a transaction's 'assignment' field and logs it in the
    'transaction_assignments' collection as a manual assignment.

    Args:
        transaction_id (str): Unique ID for the transaction (SHA-256 hash).
        assignment (str): Hierarchical assignment label, e.g. 'Expense.Food.Restaurant'.

    Returns:
        dict: {"success": True} or {"success": False, "message": "..."}
    """
    try:
        transactions = db_module.db["transactions"]
        assignments = db_module.db["transaction_assignments"]

        # --- Step 1: Update the transaction itself ---
        update_result = transactions.update_one(
            {"id": transaction_id},
            {"$set": {"assignment": assignment}}
        )

        if update_result.matched_count == 0:
            return {"success": False, "message": f"No transaction found with ID {transaction_id}"}

        # --- Step 2: Log the assignment action ---
        record = {
            "id": transaction_id,
            "assignment": assignment,
            "type": "manual",
            "timestamp": datetime.utcnow()
        }
        assignments.insert_one(record)

        return {"success": True}

    except Exception as e:
        return {"success": False, "message": str(e)}


# ----------------------------------------------------------------------
# AUTOMATIC ASSIGNMENT (Future Implementation Placeholder)
# ----------------------------------------------------------------------

def apply_all_rules() -> dict:
    """
    Applies all assignment rules from the 'assignment_rules' collection
    to all transactions that have a blank or 'Unspecified' assignment.

    (Placeholder — full implementation will follow once rule schema and
    UI for rule management are defined.)
    """
    try:
        # Just a stub for now — no logic yet.
        return {"success": True, "message": "Auto-assignment logic not yet implemented."}
    except Exception as e:
        return {"success": False, "message": str(e)}
