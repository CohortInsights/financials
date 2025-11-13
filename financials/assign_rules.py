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
import time
from financials import db as db_module
from datetime import datetime
from pymongo import UpdateOne

logger = logging.getLogger(__name__)


def assign_transactions_from_matches_bulk(txn_ids):
    """
    Given a list/set of auto-eligible transaction IDs, recompute their winning
    assignments based solely on the current state of rule_matches.

    This function performs all Mongo operations in bulk for speed:
      - Bulk aggregation to compute winners
      - Bulk deletion of old auto logs
      - Bulk insertion of new auto logs
      - Bulk updates of the transactions collection

    Returns:
        {
            "success": True,
            "count": <total txns processed>,
            "updated": <number assigned a rule>,
            "unspecified": <number assigned 'Unspecified'>,
            "winners": [
                {
                    "txn_id": str,
                    "rule_id": str,
                    "priority": int,
                    "assignment": str
                },
                ...
            ]
        }
    """
    t0 = time.perf_counter()

    # Normalize txn_ids to list
    if not txn_ids:
        return {
            "success": True,
            "count": 0,
            "updated": 0,
            "unspecified": 0,
            "winners": [],
        }

    if not isinstance(txn_ids, (list, tuple, set)):
        txn_ids = [txn_ids]
    txn_ids = list(txn_ids)

    db = db_module.db
    rm = db["rule_matches"]
    assignments_coll = db["transaction_assignments"]
    tx_coll = db["transactions"]

    try:
        # ------------------------------------------------------------------
        # 1️⃣ Find winners using one aggregation
        # ------------------------------------------------------------------

        pipeline = [
            {"$match": {"txn_id": {"$in": txn_ids}}},
            {"$sort": {"txn_id": 1, "priority": -1}},
            {"$group": {
                "_id": "$txn_id",
                "rule_id": {"$first": "$rule_id"},
                "priority": {"$first": "$priority"},
                "assignment": {"$first": "$assignment"}
            }},
        ]

        agg_results = list(rm.aggregate(pipeline))

        # Build winner maps
        winners = {
            doc["_id"]: doc["assignment"]
            for doc in agg_results
        }
        winner_txn_ids = set(winners.keys())
        loser_txn_ids = set(txn_ids) - winner_txn_ids

        # Full winner match docs to return
        winner_matches = [
            {
                "txn_id": doc["_id"],
                "rule_id": doc["rule_id"],
                "priority": doc["priority"],
                "assignment": doc["assignment"],
            }
            for doc in agg_results
        ]

        # ------------------------------------------------------------------
        # 2️⃣ Bulk delete old auto logs
        # ------------------------------------------------------------------

        assignments_coll.delete_many({
            "id": {"$in": txn_ids},
            "type": "auto"
        })

        # ------------------------------------------------------------------
        # 3️⃣ Bulk insert new auto logs (only winners)
        # ------------------------------------------------------------------

        if winner_txn_ids:
            now = datetime.utcnow()
            new_auto_logs = [
                {
                    "id": tid,
                    "assignment": winners[tid],
                    "type": "auto",
                    "timestamp": now,
                }
                for tid in winner_txn_ids
            ]
            assignments_coll.insert_many(new_auto_logs)

        # ------------------------------------------------------------------
        # 4️⃣ Bulk update the transactions table
        # ------------------------------------------------------------------

        bulk_ops = []

        # Winner updates
        for tid in winner_txn_ids:
            bulk_ops.append(
                UpdateOne({"id": tid},
                          {"$set": {"assignment": winners[tid]}})
            )

        # Loser updates (Unspecified)
        for tid in loser_txn_ids:
            bulk_ops.append(
                UpdateOne({"id": tid},
                          {"$set": {"assignment": "Unspecified"}})
            )

        if bulk_ops:
            tx_coll.bulk_write(bulk_ops)

        # ------------------------------------------------------------------
        # Results summary
        # ------------------------------------------------------------------

        return {
            "success": True,
            "count": len(txn_ids),
            "updated": len(winner_txn_ids),
            "unspecified": len(loser_txn_ids),
            "winners": winner_matches,
            "elapsed_sec": time.perf_counter() - t0,
        }

    except Exception as exc:
        logger.exception("❌ assign_transactions_from_matches_bulk failed: %s", exc)
        return {"success": False, "message": str(exc)}


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
# INCREMENTAL METHODS
# ----------------------------------------------------------------------

def rule_added_incremental(rule_id: str) -> dict:
    """
    Incrementally apply a newly created rule.

    Steps:
      1. Load rule from assignment_rules.
      2. Compute CURRENT_MATCHES (evaluate the new rule against all auto-eligible txns).
      3. Insert CURRENT_MATCHES into rule_matches.
      4. IMPACTED_TXNS = CURRENT_TXNS
      5. Recompute assignments for these transactions using the bulk helper.
    """
    import time
    from bson import ObjectId

    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        # 1️⃣ Load rule
        rule = db["assignment_rules"].find_one({"_id": ObjectId(rule_id)})
        if not rule:
            msg = f"Rule {rule_id} not found"
            logger.error(msg)
            return {"success": False, "message": msg}

        priority = rule.get("priority", 0)
        assignment = rule.get("assignment")

        # 2️⃣ Compute CURRENT_MATCHES
        all_txns = list(db["transactions"].find({}, {"_id": 0}))
        CURRENT_MATCHES = []
        for txn in all_txns:
            if _rule_matches_txn(txn, rule):
                CURRENT_MATCHES.append({
                    "rule_id": rule_id,
                    "txn_id": txn["id"],
                    "priority": priority,
                    "assignment": assignment,
                })

        CURRENT_TXNS = {m["txn_id"] for m in CURRENT_MATCHES}

        # 3️⃣ Insert rule_matches entries
        if CURRENT_MATCHES:
            rm.insert_many(CURRENT_MATCHES)

        # 4️⃣ IMPACTED_TXNS
        IMPACTED_TXNS = CURRENT_TXNS

        # 5️⃣ Re-assign winners
        result = assign_transactions_from_matches_bulk(IMPACTED_TXNS)

        logger.info(
            "✨ add_rule_incremental completed: %d matches, %d impacted txns",
            len(CURRENT_MATCHES), len(IMPACTED_TXNS)
        )

        return {
            "success": True,
            "current_matches": len(CURRENT_MATCHES),
            "impacted_txns": len(IMPACTED_TXNS),
            "assign_result": result,
        }

    except Exception as exc:
        logger.exception("❌ add_rule_incremental failed: %s", exc)
        return {"success": False, "message": str(exc)}


def rule_deleted_incremental(rule_id: str) -> dict:
    """
    Incrementally clean up after a rule is deleted from assignment_rules.

    Steps:
      1. PREVIOUS_MATCHES = all rule_matches for this rule.
      2. PREVIOUS_TXNS = unique txn_ids from PREVIOUS_MATCHES.
      3. Delete all matches for this rule_id from rule_matches.
      4. IMPACTED_TXNS = PREVIOUS_TXNS.
      5. Recompute winners for these transactions using bulk helper.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        # 1️⃣ PREVIOUS_MATCHES
        PREVIOUS_MATCHES = list(
            rm.find({"rule_id": rule_id},
                    {"_id": 0, "rule_id": 1, "txn_id": 1,
                     "priority": 1, "assignment": 1})
        )
        PREVIOUS_TXNS = {m["txn_id"] for m in PREVIOUS_MATCHES}

        # 2️⃣ Remove all matches for this rule
        rm.delete_many({"rule_id": rule_id})

        # 3️⃣ IMPACTED_TXNS
        IMPACTED_TXNS = PREVIOUS_TXNS

        # 4️⃣ Reassign winners
        result = assign_transactions_from_matches_bulk(IMPACTED_TXNS)

        logger.info(
            "🗑️ delete_rule_incremental completed: %d previous matches, %d impacted",
            len(PREVIOUS_MATCHES), len(IMPACTED_TXNS)
        )

        return {
            "success": True,
            "previous_matches": len(PREVIOUS_MATCHES),
            "impacted_txns": len(IMPACTED_TXNS),
            "assign_result": result,
        }

    except Exception as exc:
        logger.exception("❌ delete_rule_incremental failed: %s", exc)
        return {"success": False, "message": str(exc)}


def rule_updated_incremental(rule_id: str) -> dict:
    """
    Incrementally re-apply a rule after its fields (priority, source, description,
    min_amount, max_amount, assignment) have been edited.

    Steps:
      1. Load edited rule.
      2. PREVIOUS_MATCHES = rule_matches for this rule.
      3. CURRENT_MATCHES = recomputed matches for this rule.
      4. Replace old rows in rule_matches with CURRENT_MATCHES.
      5. IMPACTED_TXNS = PREVIOUS_TXNS ∪ CURRENT_TXNS.
      6. Recalculate winners using bulk helper.
    """
    import time
    from bson import ObjectId

    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        # 1️⃣ Load edited rule
        rule = db["assignment_rules"].find_one({"_id": ObjectId(rule_id)})
        if not rule:
            msg = f"Rule {rule_id} not found"
            logger.error(msg)
            return {"success": False, "message": msg}

        new_priority = rule.get("priority", 0)
        new_assignment = rule.get("assignment")

        # 2️⃣ PREVIOUS_MATCHES
        PREVIOUS_MATCHES = list(
            rm.find({"rule_id": rule_id},
                    {"_id": 0, "rule_id": 1, "txn_id": 1,
                     "priority": 1, "assignment": 1})
        )
        PREVIOUS_TXNS = {m["txn_id"] for m in PREVIOUS_MATCHES}

        # 3️⃣ CURRENT_MATCHES
        all_txns = list(db["transactions"].find({}, {"_id": 0}))
        CURRENT_MATCHES = []
        for txn in all_txns:
            if _rule_matches_txn(txn, rule):
                CURRENT_MATCHES.append({
                    "rule_id": rule_id,
                    "txn_id": txn["id"],
                    "priority": new_priority,
                    "assignment": new_assignment
                })
        CURRENT_TXNS = {m["txn_id"] for m in CURRENT_MATCHES}

        # 4️⃣ Replace rule_matches entries for this rule
        rm.delete_many({"rule_id": rule_id})
        if CURRENT_MATCHES:
            rm.insert_many(CURRENT_MATCHES)

        # 5️⃣ IMPACTED_TXNS
        IMPACTED_TXNS = PREVIOUS_TXNS.union(CURRENT_TXNS)

        # 6️⃣ Bulk reassignment
        result = assign_transactions_from_matches_bulk(IMPACTED_TXNS)

        logger.info(
            "✏️ edit_rule_incremental completed: %d previous, %d current, %d impacted",
            len(PREVIOUS_MATCHES), len(CURRENT_MATCHES), len(IMPACTED_TXNS)
        )

        return {
            "success": True,
            "previous_matches": len(PREVIOUS_MATCHES),
            "current_matches": len(CURRENT_MATCHES),
            "impacted_txns": len(IMPACTED_TXNS),
            "assign_result": result,
        }

    except Exception as exc:
        logger.exception("❌ edit_rule_incremental failed: %s", exc)
        return {"success": False, "message": str(exc)}
