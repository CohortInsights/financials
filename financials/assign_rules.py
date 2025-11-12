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

import time
import logging
from datetime import datetime
from financials import db as db_module

logger = logging.getLogger(__name__)

def apply_all_rules() -> dict:
    """
    Applies all assignment rules from the 'assignment_rules' collection
    to all transactions that have no manual assignment.
    Clears prior auto-assignments, reapplies all rules by priority,
    and logs detailed timings for each stage.
    """
    t0 = time.perf_counter()
    db = db_module.db
    logger.info("🔁 Starting rule reapplication: detailed timing enabled")

    try:
        # ---------------------------------------------------------------
        # 1️⃣ Load all rules
        # ---------------------------------------------------------------
        t_rules_start = time.perf_counter()
        rules = list(db["assignment_rules"].find().sort("priority", -1))
        t_rules = time.perf_counter() - t_rules_start
        logger.info(f"📋 Loaded {len(rules)} rules in {t_rules:.3f}s")

        # ---------------------------------------------------------------
        # 2️⃣ Cache manual assignment IDs
        # ---------------------------------------------------------------
        t_manual_start = time.perf_counter()
        manual_ids = {
            x["id"] for x in db["transaction_assignments"].find({"type": "manual"}, {"id": 1})
        }
        t_manual = time.perf_counter() - t_manual_start
        logger.info(f"📎 Cached {len(manual_ids)} manual assignment IDs in {t_manual:.3f}s")

        # ---------------------------------------------------------------
        # 3️⃣ Clear prior auto assignments
        # ---------------------------------------------------------------
        t_clear_start = time.perf_counter()
        cleared_logs = db["transaction_assignments"].delete_many({"type": "auto"}).deleted_count
        t_clear_logs = time.perf_counter() - t_clear_start
        logger.info(f"🗑️ Cleared {cleared_logs} prior auto assignment logs in {t_clear_logs:.3f}s")

        t_clear_txn_start = time.perf_counter()
        cleared_txn = db["transactions"].update_many(
            {"id": {"$nin": list(manual_ids)}, "assignment": {"$ne": "Unspecified"}},
            {"$set": {"assignment": "Unspecified"}}
        ).modified_count
        t_clear_txn = time.perf_counter() - t_clear_txn_start
        logger.info(f"🧹 Cleared {cleared_txn} auto-assigned transactions in {t_clear_txn:.3f}s")

        # ---------------------------------------------------------------
        # 4️⃣ Reload transactions
        # ---------------------------------------------------------------
        t_load_start = time.perf_counter()
        transactions = list(db["transactions"].find({}, {"_id": 0}))
        t_load = time.perf_counter() - t_load_start
        logger.info(f"📦 Reloaded {len(transactions)} transactions after clearing in {t_load:.3f}s")

        # ---------------------------------------------------------------
        # 5️⃣ Apply rules
        # ---------------------------------------------------------------
        t_apply_start = time.perf_counter()
        updated, unchanged = 0, 0

        for txn in transactions:
            if txn["id"] in manual_ids:
                unchanged += 1
                continue

            assignment = find_best_assignment(txn, rules)
            if assignment:
                db["transactions"].update_one(
                    {"id": txn["id"]}, {"$set": {"assignment": assignment}}
                )
                db["transaction_assignments"].insert_one({
                    "id": txn["id"],
                    "assignment": assignment,
                    "type": "auto",
                    "timestamp": datetime.utcnow()
                })
                updated += 1

        t_apply = time.perf_counter() - t_apply_start
        logger.info(f"⚙️ Applied rules to {updated} transactions ({unchanged} unchanged) in {t_apply:.3f}s")

        # ---------------------------------------------------------------
        # 6️⃣ Summary
        # ---------------------------------------------------------------
        total = time.perf_counter() - t0
        logger.info(
            f"✅ Rule reapplication complete in {total:.3f}s "
            f"(rules={t_rules:.3f}s, manual={t_manual:.3f}s, clear_logs={t_clear_logs:.3f}s, "
            f"clear_txn={t_clear_txn:.3f}s, load={t_load:.3f}s, apply={t_apply:.3f}s)"
        )
        return {"success": True, "updated": updated, "unchanged": unchanged}

    except Exception as e:
        logger.exception(f"❌ Auto-assignment failed: {e}")
        return {"success": False, "message": str(e)}


def find_best_assignment(txn: dict, rules: list) -> str | None:
    """Return the assignment from the highest-priority rule matching a transaction."""
    src = (txn.get("source") or "").lower()
    desc = (txn.get("description") or "").lower()
    amt = float(txn.get("amount") or 0)

    for rule in rules:
        # --- Source match ---
        if rule.get("source"):
            sources = [s.strip().lower() for s in rule["source"].split(",") if s.strip()]
            if src not in sources:
                continue

        # --- Description match ---
        if rule.get("description"):
            rule_text = rule["description"].lower()
            if "," in rule_text:  # AND logic
                if not all(term.strip() in desc for term in rule_text.split(",")):
                    continue
            elif "|" in rule_text:  # OR logic
                if not any(term.strip() in desc for term in rule_text.split("|")):
                    continue
            elif rule_text.strip() not in desc:
                continue

        # --- Amount match ---
        min_amt = rule.get("min_amount")
        max_amt = rule.get("max_amount")

        # Interpret None as "no limit"
        if min_amt is not None:
            try:
                if amt < float(min_amt):
                    continue
            except (ValueError, TypeError):
                continue  # skip malformed min_amt

        if max_amt is not None:
            try:
                if amt > float(max_amt):
                    continue
            except (ValueError, TypeError):
                continue  # skip malformed max_amt

        # --- If all filters pass, rule matches ---
        return rule.get("assignment")

    return None


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    summary = apply_all_rules()
    logger.info("Summary: %s", summary)
