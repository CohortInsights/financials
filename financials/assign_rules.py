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

from financials.utils.google_types import get_primary_types_for_descriptions

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# GOOGLE PRIMARY TYPE HELPER
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# BULK APPLY WINNERS
# ----------------------------------------------------------------------

def assign_transactions_from_matches_bulk(txn_ids):
    """
    Given a list/set of auto-eligible transaction IDs, recompute their winning
    assignments based solely on the current state of rule_matches.

    This function performs all Mongo operations in bulk for speed.
    """
    t0 = time.perf_counter()

    # Normalize txn_ids
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
        # 1️⃣ Aggregation: determine top winners
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

        winners = {doc["_id"]: doc["assignment"] for doc in agg_results}
        winner_txn_ids = set(winners.keys())
        loser_txn_ids = set(txn_ids) - winner_txn_ids

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
        # 2️⃣ Remove old auto logs
        # ------------------------------------------------------------------
        assignments_coll.delete_many({"id": {"$in": txn_ids}, "type": "auto"})

        # ------------------------------------------------------------------
        # 3️⃣ Insert auto logs only for winners
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
        # 4️⃣ Bulk update transactions
        # ------------------------------------------------------------------
        bulk_ops = []

        for tid in winner_txn_ids:
            bulk_ops.append(UpdateOne({"id": tid}, {"$set": {"assignment": winners[tid]}}))

        for tid in loser_txn_ids:
            bulk_ops.append(UpdateOne({"id": tid}, {"$set": {"assignment": "Unspecified"}}))

        if bulk_ops:
            tx_coll.bulk_write(bulk_ops)

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
# CLEAR
# ----------------------------------------------------------------------

def clear_assignments() -> dict:
    """
    Clear all automatic assignments and rule_matches.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db

    try:
        ta = db["transaction_assignments"]
        tx = db["transactions"]
        rm = db["rule_matches"]

        auto_ids = ta.distinct("id", {"type": "auto"})
        auto_del = ta.delete_many({"type": "auto"})

        reset_count = 0
        if auto_ids:
            result = tx.update_many(
                {"id": {"$in": auto_ids}},
                {"$set": {"assignment": "Unspecified"}}
            )
            reset_count = result.modified_count

        rm_del = rm.delete_many({})

        elapsed = time.perf_counter() - t0

        logger.info(
            "🧹 clear_assignments v3: auto_logs=%d, reset=%d, rule_matches=%d in %.3fs",
            auto_del.deleted_count, reset_count, rm_del.deleted_count, elapsed
        )

        return {
            "success": True,
            "auto_logs_deleted": auto_del.deleted_count,
            "assignments_reset": reset_count,
            "rule_matches_cleared": rm_del.deleted_count,
            "elapsed_sec": elapsed
        }

    except Exception as exc:
        logger.exception("❌ clear_assignments failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# NEW TXN ASSIGNMENT (incremental)
# ----------------------------------------------------------------------

def assign_new_transactions(new_ids: list[str]) -> dict:
    """
    Incrementally assign ONLY newly ingested transactions.
    """
    if not new_ids:
        return {"success": True, "updated": 0}

    db = db_module.db
    rm = db["rule_matches"]
    tx = db["transactions"]
    ta = db["transaction_assignments"]

    # 1. Filter manual
    manual_ids = set(ta.distinct("id", {"type": "manual", "id": {"$in": new_ids}}))
    auto_ids = [tid for tid in new_ids if tid not in manual_ids]

    if not auto_ids:
        return {"success": True, "updated": 0, "unchanged": len(manual_ids)}

    # 2. Load rules
    rules = list(db["assignment_rules"].find().sort("priority", -1))

    # 3. Load txns
    txns = list(tx.find({"id": {"$in": auto_ids}}, {"_id": 0}))

    # 3B. NEW — look up google primary types
    primary_map = get_primary_types_for_descriptions([t["description"] for t in txns])

    # 4. Compute matches
    new_match_rows = []
    for txn in txns:
        tid = txn["id"]
        primary = primary_map.get(txn["description"].lower())

        for rule in rules:
            if _rule_matches_txn(txn, rule, primary_type=primary):
                new_match_rows.append({
                    "rule_id": str(rule["_id"]),
                    "txn_id": tid,
                    "priority": rule.get("priority", 0),
                    "assignment": rule.get("assignment")
                })

    if new_match_rows:
        rm.insert_many(new_match_rows)

    # 5. Bulk winners
    summary = assign_transactions_from_matches_bulk(auto_ids)

    return {
        "success": True,
        **summary,
        "manual_skipped": len(manual_ids)
    }


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
# RULE MATCHING — UPDATED TO INCLUDE primary_type
# ----------------------------------------------------------------------

def _rule_matches_txn(txn: dict, rule: dict, primary_type=None) -> bool:
    """Determine if a rule matches a transaction."""
    src = (txn.get("source") or "").lower()
    base_desc = (txn.get("description") or "").lower()

    desc = base_desc
    if primary_type:
        desc = f"{base_desc} {primary_type.lower()}"

    amt = float(txn.get("amount") or 0)

    # SOURCE
    if rule.get("source"):
        allowed = [s.strip().lower() for s in rule["source"].split(",") if s.strip()]
        if src not in allowed:
            return False

    # DESCRIPTION
    if rule.get("description"):
        text = rule["description"].lower()
        if "," in text:
            if not all(term.strip() in desc for term in text.split(",")):
                return False
        elif "|" in text:
            if not any(term.strip() in desc for term in text.split("|")):
                return False
        elif text.strip() not in desc:
            return False

    # AMOUNT
    min_amt = rule.get("min_amount")
    max_amt = rule.get("max_amount")

    if min_amt is not None and amt < float(min_amt):
        return False
    if max_amt is not None and amt > float(max_amt):
        return False

    return True


# ----------------------------------------------------------------------
# BEST RULE SELECTION — UPDATED TO INCLUDE primary_type
# ----------------------------------------------------------------------

def find_best_assignment(txn: dict, rules: list, primary_type=None):
    """Return (assignment, rule_id, priority) or (None, None, None)."""
    src = (txn.get("source") or "").lower()
    base_desc = (txn.get("description") or "").lower()

    desc = base_desc
    if primary_type:
        desc = f"{base_desc} {primary_type.lower()}"

    amt = float(txn.get("amount") or 0)

    for rule in rules:
        if rule.get("source"):
            allowed = [s.strip().lower() for s in rule["source"].split(",") if s.strip()]
            if src not in allowed:
                continue

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

        min_amt = rule.get("min_amount")
        max_amt = rule.get("max_amount")

        if min_amt is not None and amt < float(min_amt):
            continue
        if max_amt is not None and amt > float(max_amt):
            continue

        return (
            rule.get("assignment"),
            rule["_id"],
            rule.get("priority", 0)
        )

    return None, None, None


# ----------------------------------------------------------------------
# FULL REBUILD — INCLUDES primary_type injection
# ----------------------------------------------------------------------

def apply_all_rules() -> dict:
    """
    Apply all rules to all transactions.
    Uses fast path if rule_matches exists, slow path otherwise.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db

    tx = db["transactions"]
    rm = db["rule_matches"]
    ar = db["assignment_rules"]
    ta = db["transaction_assignments"]

    # Internal helper for both fast+slow paths
    def __apply_winner_rows(winner_rows):
        if not winner_rows:
            return {"updated": 0, "logged": 0, "skipped": 0}

        txn_ids = [row["txn_id"] for row in winner_rows]

        current_map = {
            d["id"]: d.get("assignment")
            for d in tx.find({"id": {"$in": txn_ids}}, {"id": 1, "assignment": 1})
        }

        filtered_rows = []
        skipped = 0

        for row in winner_rows:
            tid = row["txn_id"]
            desired = row["assignment"]
            current = current_map.get(tid)

            if current == desired:
                skipped += 1
            else:
                filtered_rows.append(row)

        if not filtered_rows:
            return {"updated": 0, "logged": 0, "skipped": skipped}

        updates = [
            UpdateOne({"id": row["txn_id"]}, {"$set": {"assignment": row["assignment"]}})
            for row in filtered_rows
        ]

        timestamp = datetime.utcnow()
        logs = [
            {
                "id": row["txn_id"],
                "assignment": row["assignment"],
                "type": "auto",
                "timestamp": timestamp,
            }
            for row in filtered_rows
        ]

        tx.bulk_write(updates)
        ta.insert_many(logs)

        return {
            "updated": len(updates),
            "logged": len(logs),
            "skipped": skipped,
        }

    try:
        # FAST PATH
        if rm.estimated_document_count() > 0:
            logger.info("⚡ apply_all_rules: fast path (rule_matches present)")

            pipeline = [
                {"$sort": {"priority": -1}},
                {"$group": {
                    "_id": "$txn_id",
                    "rule_id": {"$first": "$rule_id"},
                    "assignment": {"$first": "$assignment"},
                    "priority": {"$first": "$priority"},
                }},
                {"$project": {
                    "_id": 0,
                    "txn_id": "$_id",
                    "rule_id": 1,
                    "assignment": 1,
                    "priority": 1,
                }},
            ]

            winner_rows = list(rm.aggregate(pipeline))
            apply_result = __apply_winner_rows(winner_rows)
            elapsed = time.perf_counter() - t0

            logger.info(
                "⚡ Fast path: updated=%d, skipped=%d in %.3fs",
                apply_result["updated"], apply_result["skipped"], elapsed
            )

            return {
                "path": "fast",
                "success": True,
                "updated": apply_result["updated"],
                "skipped": apply_result["skipped"],
                "elapsed_sec": elapsed,
            }

        # SLOW PATH — rebuild rule_matches
        logger.info("🐢 apply_all_rules: slow path (rebuilding rule_matches)")

        rules = list(ar.find({}).sort("priority", -1))
        txns = list(tx.find({}, {"_id": 0}))

        # NEW — load primary types
        primary_map = get_primary_types_for_descriptions([t["description"] for t in txns])

        match_rows = []
        winners = {}

        for txn in txns:
            tid = txn["id"]
            primary = primary_map.get(txn["description"].lower())

            for rule in rules:
                if _rule_matches_txn(txn, rule, primary_type=primary):
                    row = {
                        "rule_id": str(rule["_id"]),
                        "txn_id": tid,
                        "priority": rule.get("priority", 0),
                        "assignment": rule.get("assignment"),
                    }
                    match_rows.append(row)

                    if tid not in winners or row["priority"] > winners[tid]["priority"]:
                        winners[tid] = row

        if match_rows:
            rm.insert_many(match_rows)

        winner_rows = list(winners.values())
        apply_result = __apply_winner_rows(winner_rows)

        elapsed = time.perf_counter() - t0

        logger.info(
            "🐢 Slow rebuild: matches=%d, updated=%d, skipped=%d in %.3fs",
            len(match_rows), apply_result["updated"], apply_result["skipped"], elapsed
        )

        return {
            "path": "slow",
            "success": True,
            "updated": apply_result["updated"],
            "skipped": apply_result["skipped"],
            "matches": len(match_rows),
            "elapsed_sec": elapsed,
        }

    except Exception as exc:
        logger.exception("❌ apply_all_rules failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# INCREMENTAL RULE MGMT — all patched for primary_type
# ----------------------------------------------------------------------

def rule_added_incremental(rule_id: str) -> dict:
    """
    Incrementally apply a newly created rule.
    """
    import time
    from bson import ObjectId

    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        rule = db["assignment_rules"].find_one({"_id": ObjectId(rule_id)})
        if not rule:
            msg = f"Rule {rule_id} not found"
            logger.error(msg)
            return {"success": False, "message": msg}

        priority = rule.get("priority", 0)
        assignment = rule.get("assignment")

        all_txns = list(db["transactions"].find({}, {"_id": 0}))

        # NEW — add primary types
        primary_map = get_primary_types_for_descriptions([t["description"] for t in all_txns])

        CURRENT_MATCHES = []
        for txn in all_txns:
            primary = primary_map.get(txn["description"].lower())
            if _rule_matches_txn(txn, rule, primary_type=primary):
                CURRENT_MATCHES.append({
                    "rule_id": rule_id,
                    "txn_id": txn["id"],
                    "priority": priority,
                    "assignment": assignment,
                })

        CURRENT_TXNS = {m["txn_id"] for m in CURRENT_MATCHES}

        if CURRENT_MATCHES:
            rm.insert_many(CURRENT_MATCHES)

        result = assign_transactions_from_matches_bulk(CURRENT_TXNS)

        logger.info(
            "✨ add_rule_incremental completed: %d matches, %d impacted txns",
            len(CURRENT_MATCHES), len(CURRENT_TXNS)
        )

        return {
            "success": True,
            "current_matches": len(CURRENT_MATCHES),
            "impacted_txns": len(CURRENT_TXNS),
            "assign_result": result,
        }

    except Exception as exc:
        logger.exception("❌ add_rule_incremental failed: %s", exc)
        return {"success": False, "message": str(exc)}


def rule_deleted_incremental(rule_id: str) -> dict:
    """
    Clean up after a rule is deleted.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        PREVIOUS_MATCHES = list(
            rm.find({"rule_id": rule_id},
                    {"_id": 0, "rule_id": 1, "txn_id": 1,
                     "priority": 1, "assignment": 1})
        )
        PREVIOUS_TXNS = {m["txn_id"] for m in PREVIOUS_MATCHES}

        rm.delete_many({"rule_id": rule_id})

        result = assign_transactions_from_matches_bulk(PREVIOUS_TXNS)

        logger.info(
            "🗑️ delete_rule_incremental completed: %d previous matches, %d impacted",
            len(PREVIOUS_MATCHES), len(PREVIOUS_TXNS)
        )

        return {
            "success": True,
            "previous_matches": len(PREVIOUS_MATCHES),
            "impacted_txns": len(PREVIOUS_TXNS),
            "assign_result": result,
        }

    except Exception as exc:
        logger.exception("❌ delete_rule_incremental failed: %s", exc)
        return {"success": False, "message": str(exc)}


def rule_updated_incremental(rule_id: str) -> dict:
    """
    Re-apply a rule after edits.
    """
    import time
    from bson import ObjectId

    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        rule = db["assignment_rules"].find_one({"_id": ObjectId(rule_id)})
        if not rule:
            msg = f"Rule {rule_id} not found"
            logger.error(msg)
            return {"success": False, "message": msg}

        new_priority = rule.get("priority", 0)
        new_assignment = rule.get("assignment")

        PREVIOUS_MATCHES = list(
            rm.find({"rule_id": rule_id},
                    {"_id": 0, "rule_id": 1, "txn_id": 1,
                     "priority": 1, "assignment": 1})
        )
        PREVIOUS_TXNS = {m["txn_id"] for m in PREVIOUS_MATCHES}

        all_txns = list(db["transactions"].find({}, {"_id": 0}))

        # NEW primary types
        primary_map = get_primary_types_for_descriptions([t["description"] for t in all_txns])

        CURRENT_MATCHES = []
        for txn in all_txns:
            primary = primary_map.get(txn["description"].lower())
            if _rule_matches_txn(txn, rule, primary_type=primary):
                CURRENT_MATCHES.append({
                    "rule_id": rule_id,
                    "txn_id": txn["id"],
                    "priority": new_priority,
                    "assignment": new_assignment
                })
        CURRENT_TXNS = {m["txn_id"] for m in CURRENT_MATCHES}

        rm.delete_many({"rule_id": rule_id})
        if CURRENT_MATCHES:
            rm.insert_many(CURRENT_MATCHES)

        IMPACTED = PREVIOUS_TXNS.union(CURRENT_TXNS)

        result = assign_transactions_from_matches_bulk(IMPACTED)

        logger.info(
            "✏️ edit_rule_incremental completed: %d previous, %d current, %d impacted",
            len(PREVIOUS_MATCHES), len(CURRENT_MATCHES), len(IMPACTED)
        )

        return {
            "success": True,
            "previous_matches": len(PREVIOUS_MATCHES),
            "current_matches": len(CURRENT_MATCHES),
            "impacted_txns": len(IMPACTED),
            "assign_result": result,
        }

    except Exception as exc:
        logger.exception("❌ edit_rule_incremental failed: %s", exc)
        return {"success": False, "message": str(exc)}
