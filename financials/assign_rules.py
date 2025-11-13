"""
Assignment Rules Module
------------------------
Handles manual and automatic assignment of transactions.

Collections involved:
- transactions
- transaction_assignments   (audit)
- assignment_rules          (definition of automatic rules)
- rule_matches              (precomputed rule-to-transaction matches)
"""

import logging
import pymongo
from datetime import datetime
from pymongo import UpdateOne
from financials import db as db_module

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# MANUAL ASSIGNMENT
# ----------------------------------------------------------------------

def set_transaction_assignment(transaction_id: str, assignment: str) -> dict:
    """Apply a manual assignment and log it."""
    try:
        db = db_module.db
        transactions = db["transactions"]
        assignments = db["transaction_assignments"]

        result = transactions.update_one(
            {"id": transaction_id},
            {"$set": {"assignment": assignment}}
        )

        if result.matched_count == 0:
            return {"success": False, "message": f"Transaction {transaction_id} not found"}

        assignments.insert_one({
            "id": transaction_id,
            "assignment": assignment,
            "type": "manual",
            "timestamp": datetime.utcnow()
        })

        logger.info("📝 Manual assignment applied to %s → %s", transaction_id, assignment)
        return {"success": True}

    except Exception as exc:
        logger.exception("❌ Manual assignment failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# RULE MATCH CHECKER  (must match find_best_assignment EXACTLY)
# ----------------------------------------------------------------------

def _rule_matches_txn(txn: dict, rule: dict) -> bool:
    """Determine if a rule matches a transaction."""
    src = (txn.get("source") or "").lower()
    desc = (txn.get("description") or "").lower()
    amt = float(txn.get("amount") or 0)

    # --- SOURCE ---
    if rule.get("source"):
        allowed = [s.strip().lower() for s in rule["source"].split(",") if s.strip()]
        if src not in allowed:
            return False

    # --- DESCRIPTION ---
    if rule.get("description"):
        text = rule["description"].lower()
        if "," in text:  # AND
            if not all(term.strip() in desc for term in text.split(",")):
                return False
        elif "|" in text:  # OR
            if not any(term.strip() in desc for term in text.split("|")):
                return False
        elif text.strip() not in desc:
            return False

    # --- AMOUNT ---
    min_amt = rule.get("min_amount")
    max_amt = rule.get("max_amount")

    if min_amt is not None:
        if amt < float(min_amt):
            return False

    if max_amt is not None:
        if amt > float(max_amt):
            return False

    return True


# ----------------------------------------------------------------------
# RULE SELECTION (top priority)
# ----------------------------------------------------------------------

def find_best_assignment(txn: dict, rules: list):
    """Return (assignment, rule_id, priority) or (None, None, None)."""
    src = (txn.get("source") or "").lower()
    desc = (txn.get("description") or "").lower()
    amt = float(txn.get("amount") or 0)

    for rule in rules:  # sorted by priority DESC
        # --- Source ---
        if rule.get("source"):
            allowed = [s.strip().lower() for s in rule["source"].split(",") if s.strip()]
            if src not in allowed:
                continue

        # --- Description ---
        if rule.get("description"):
            text = rule["description"].lower()
            if "," in text:
                if not all(term.strip() in desc for term in text.split(",")):
                    continue
            elif "|" in text:
                if not any(term.strip() in desc for term in text.split("|")):
                    continue
            elif text.strip() not in desc:
                continue

        # --- Amount ---
        min_amt = rule.get("min_amount")
        max_amt = rule.get("max_amount")
        if min_amt is not None and amt < float(min_amt):
            continue
        if max_amt is not None and amt > float(max_amt):
            continue

        return rule.get("assignment"), rule["_id"], rule.get("priority", 0)

    return None, None, None


# ----------------------------------------------------------------------
# FULL REBUILD (add/edit)
# ----------------------------------------------------------------------

def apply_all_rules() -> dict:
    """
    Full rebuild: clear auto assignments, reapply all rules,
    rebuild rule_matches completely.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db

    logger.info("🔁 Starting rule reapplication: detailed timing enabled")

    try:
        # 1️⃣ Load rules
        t = time.perf_counter()
        rules = list(db["assignment_rules"].find().sort("priority", -1))
        logger.info("📋 Loaded %d rules in %.3fs", len(rules), time.perf_counter() - t)

        # 2️⃣ Manual assignments
        t = time.perf_counter()
        manual_ids = {
            x["id"] for x in db["transaction_assignments"].find(
                {"type": "manual"}, {"id": 1})
        }
        logger.info("📎 Cached %d manual IDs in %.3fs",
                    len(manual_ids), time.perf_counter() - t)

        # 3️⃣ Clear old auto logs & assignments
        db["transaction_assignments"].delete_many({"type": "auto"})
        db["transactions"].update_many(
            {"id": {"$nin": list(manual_ids)}},
            {"$set": {"assignment": "Unspecified"}}
        )

        # 4️⃣ Load transactions
        t = time.perf_counter()
        txns = list(db["transactions"].find({}, {"_id": 0}))
        logger.info("📦 Loaded %d transactions in %.3fs",
                    len(txns), time.perf_counter() - t)

        # 5️⃣ Apply rules
        updates = []
        logs = []
        match_rows = []
        updated = 0
        unchanged = 0

        for txn in txns:
            tid = txn["id"]

            if tid in manual_ids:
                unchanged += 1
                continue

            assignment, rid, prio = find_best_assignment(txn, rules)

            if assignment:
                updated += 1
                updates.append(
                    UpdateOne({"id": tid}, {"$set": {"assignment": assignment}})
                )
                logs.append({
                    "id": tid,
                    "assignment": assignment,
                    "type": "auto",
                    "timestamp": datetime.utcnow()
                })

            # Build rule_matches entry for EVERY matching rule
            for rule in rules:
                if _rule_matches_txn(txn, rule):
                    match_rows.append({
                        "rule_id": str(rule["_id"]),  # store as string
                        "txn_id": tid,
                        "priority": rule.get("priority", 0),
                        "assignment": rule.get("assignment"),
                    })

        if updates:
            db["transactions"].bulk_write(updates)
        if logs:
            db["transaction_assignments"].insert_many(logs)

        # Replace rule_matches
        rm = db["rule_matches"]
        rm.delete_many({})
        if match_rows:
            rm.insert_many(match_rows)

        total = time.perf_counter() - t0
        logger.info("🔗 Rebuilt rule_matches with %d entries", len(match_rows))
        logger.info("⚙️ Updated %d transactions (%d unchanged) in %.3fs",
                    updated, unchanged, total)

        return {"success": True, "updated": updated, "unchanged": unchanged}

    except Exception as exc:
        logger.exception("❌ apply_all_rules failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# INCREMENTAL DELETE (fix reassignments)
# ----------------------------------------------------------------------

def delete_rule_incremental(rule_id: str) -> dict:
    """
    Incrementally clean up after a rule is deleted.
    Assumes rule was already removed from assignment_rules.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    logger.info("🧩 Incremental delete started for rule %s", rule_id)

    try:
        # 1️⃣ Find impacted transactions
        matches = list(rm.find({"rule_id": rule_id}, {"txn_id": 1, "_id": 0}))
        txn_ids = [m["txn_id"] for m in matches]

        logger.info("🔍 Found %d affected transactions", len(txn_ids))

        if not txn_ids:
            rm.delete_many({"rule_id": rule_id})
            return {"success": True, "updated": 0, "unchanged": 0}

        # 2️⃣ Manual assignments (never touched)
        manual_ids = {
            x["id"] for x in db["transaction_assignments"].find(
                {"type": "manual", "id": {"$in": txn_ids}},
                {"id": 1}
            )
        }

        auto_ids = [tid for tid in txn_ids if tid not in manual_ids]

        # 3️⃣ Clear auto logs + assignments
        db["transaction_assignments"].delete_many(
            {"type": "auto", "id": {"$in": auto_ids}}
        )
        db["transactions"].update_many(
            {"id": {"$in": auto_ids}},
            {"$set": {"assignment": "Unspecified"}}
        )

        # 4️⃣ Remove matches for deleted rule
        rm.delete_many({"rule_id": rule_id})

        # 5️⃣ Reassign using next-highest rules
        updates = []
        logs = []
        new_matches = []

        for tid in auto_ids:
            nxt = list(
                rm.find({"txn_id": tid})
                .sort("priority", -1)
                .limit(1)
            )

            if not nxt:
                continue  # stays Unspecified

            nr = nxt[0]
            assignment = nr["assignment"]

            updates.append(
                UpdateOne({"id": tid}, {"$set": {"assignment": assignment}})
            )

            logs.append({
                "id": tid,
                "assignment": assignment,
                "type": "auto",
                "timestamp": datetime.utcnow()
            })

            new_matches.append({
                "rule_id": str(nr["rule_id"]),  # ensure string
                "txn_id": tid,
                "priority": nr["priority"],
                "assignment": assignment,
            })

        if updates:
            db["transactions"].bulk_write(updates)
        if logs:
            db["transaction_assignments"].insert_many(logs)
        if new_matches:
            rm.insert_many(new_matches)

        logger.info("⚙️ Incrementally updated %d transactions", len(updates))
        logger.info("✅ Incremental delete complete in %.3fs",
                    time.perf_counter() - t0)

        return {"success": True,
                "updated": len(updates),
                "unchanged": len(manual_ids)}

    except Exception as exc:
        logger.exception("❌ Incremental delete failed: %s", exc)
        return {"success": False, "message": str(exc)}
