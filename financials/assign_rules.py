"""
Assignment Rules Module
------------------------
Handles manual and automatic assignment of transactions.

Collections involved:
- transactions
- transaction_assignments  (audit of manual/auto assignments)
- assignment_rules         (definition of automatic rules)
"""

import logging
from datetime import datetime
from financials import db as db_module

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# MANUAL ASSIGNMENT
# ----------------------------------------------------------------------

def set_transaction_assignment(transaction_id: str, assignment: str) -> dict:
    """
    Updates a transaction's 'assignment' field and logs it in the
    'transaction_assignments' collection as a manual assignment.

    Args:
        transaction_id (str): Unique logical ID (SHA-256 hash).
        assignment (str): Hierarchical label, e.g. 'Expense.Food.Restaurant'.

    Returns:
        dict: {"success": True} or {"success": False, "message": "..."}
    """
    try:
        transactions = db_module.db["transactions"]
        assignments = db_module.db["transaction_assignments"]

        update_result = transactions.update_one(
            {"id": transaction_id},
            {"$set": {"assignment": assignment}}
        )

        if update_result.matched_count == 0:
            return {"success": False, "message": f"No transaction found with ID {transaction_id}"}

        record = {
            "id": transaction_id,
            "assignment": assignment,
            "type": "manual",
            "timestamp": datetime.utcnow(),
        }
        assignments.insert_one(record)
        logger.info("📝 Manual assignment applied to %s → %s", transaction_id, assignment)
        return {"success": True}

    except Exception as e:
        logger.exception("❌ Manual assignment failed: %s", e)
        return {"success": False, "message": str(e)}


# ----------------------------------------------------------------------
# AUTOMATIC ASSIGNMENT (Full Implementation)
# ----------------------------------------------------------------------

def apply_all_rules() -> dict:
    """
    Reapply all assignment rules to all transactions.

    Steps:
      1. Load all rules and find manual assignment IDs.
      2. Delete prior auto-assignment logs.
      3. Clear 'assignment' for non-manual transactions only.
      4. Reload transactions to reflect cleared state.
      5. Re-evaluate each eligible transaction against sorted rules.
      6. Update 'transactions' and log auto assignments.

    Returns:
        dict: Summary counts, e.g. {"updated": 234, "unchanged": 8123}
    """
    try:
        db = db_module.db
        rules = list(db["assignment_rules"].find({}))
        manual_ids = {x["id"] for x in db["transaction_assignments"].find({"type": "manual"})}

        logger.info("🔁 Starting rule reapplication: %d rules", len(rules))

        # Step 1: Clear prior auto assignments (but preserve manual)
        db["transaction_assignments"].delete_many({"type": "auto"})
        db["transactions"].update_many(
            {"id": {"$nin": list(manual_ids)}},
            {"$set": {"assignment": None}}
        )

        # ✅ Step 2: Reload transactions to reflect cleared state
        txns = list(db["transactions"].find({}))
        logger.info("📦 Reloaded %d transactions after clearing", len(txns))

        # Step 3: Sort rules by priority and recency
        rules.sort(key=lambda r: (r.get("priority", 0), str(r["_id"])), reverse=True)
        updated = 0
        unchanged = 0

        # Step 4: Apply rules
        for txn in txns:
            txn_id = txn.get("id")
            if txn_id in manual_ids:
                continue  # skip manual transactions entirely

            best_assignment = find_best_assignment(txn, rules)
            if not best_assignment:
                continue  # no matching rule

            # Assign unconditionally (since cleared earlier)
            db["transactions"].update_one(
                {"_id": txn["_id"]},
                {"$set": {"assignment": best_assignment}}
            )
            db["transaction_assignments"].insert_one({
                "id": txn_id,
                "type": "auto",
                "assignment": best_assignment,
                "timestamp": datetime.utcnow(),
            })
            updated += 1

        summary = {"updated": updated, "unchanged": unchanged}
        logger.info("✅ Rule reapplication complete: %d assigned, %d unchanged", updated, unchanged)
        return summary

    except Exception as e:
        logger.exception("❌ Auto-assignment failed: %s", e)
        return {"success": False, "message": str(e)}


def find_best_assignment(txn: dict, rules: list) -> str | None:
    """Return the assignment from the highest-priority rule matching a transaction."""
    src = (txn.get("source") or "").lower()
    desc = (txn.get("description") or "").lower()
    amt = abs(float(txn.get("amount") or 0))

    for rule in rules:
        # Source match
        if rule.get("source"):
            sources = [s.strip().lower() for s in rule["source"].split(",") if s.strip()]
            if src not in sources:
                continue

        # Description match
        if rule.get("description"):
            rule_text = rule["description"].lower()
            if "," in rule_text:  # AND
                if not all(term.strip() in desc for term in rule_text.split(",")):
                    continue
            elif "|" in rule_text:  # OR
                if not any(term.strip() in desc for term in rule_text.split("|")):
                    continue
            elif rule_text.strip() not in desc:
                continue

        # Amount match
        min_amt = float(rule.get("min_amount") or 0)
        max_amt = float(rule.get("max_amount") or 0)
        if amt < min_amt:
            continue
        if max_amt and amt > max_amt:
            continue

        return rule.get("assignment")

    return None


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    summary = apply_all_rules()
    logger.info("Summary: %s", summary)
