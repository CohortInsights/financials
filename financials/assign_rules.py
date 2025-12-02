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
# Helper: unified description key
# ----------------------------------------------------------------------

def _desc_key(txn: dict) -> str:
    """
    Unified lowercased key used for rule matching and primary_map lookup.
    """
    return (txn.get("normalized_description")
            or txn.get("description")
            or "").lower()


# ----------------------------------------------------------------------
# BULK APPLY WINNERS
# ----------------------------------------------------------------------

def assign_transactions_from_matches_bulk(txn_ids):
    """
    Given a list/set of auto-eligible transaction IDs, recompute their winning
    assignments based solely on the current state of rule_matches.
    """
    t0 = time.perf_counter()

    if not txn_ids:
        return {"success": True, "count": 0, "updated": 0,
                "unspecified": 0, "winners": []}

    if not isinstance(txn_ids, (list, tuple, set)):
        txn_ids = [txn_ids]
    txn_ids = list(txn_ids)

    db = db_module.db
    rm = db["rule_matches"]
    assignments_coll = db["transaction_assignments"]
    tx_coll = db["transactions"]

    try:
        pipeline = [
            {"$match": {"txn_id": {"$in": txn_ids}}},
            {"$sort": {"txn_id": 1, "priority": -1}},
            {"$group": {
                "_id": "$txn_id",
                "rule_id": {"$first": "$rule_id"},
                "priority": {"$first": "$priority"},
                "assignment": {"$first": "$assignment"},
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

        # Remove old auto logs
        assignments_coll.delete_many({"id": {"$in": txn_ids}, "type": "auto"})

        # Insert new logs
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

        # Update transactions
        bulk_ops = []
        for tid in winner_txn_ids:
            bulk_ops.append(
                UpdateOne({"id": tid},
                          {"$set": {"assignment": winners[tid]}})
            )
        for tid in loser_txn_ids:
            bulk_ops.append(
                UpdateOne({"id": tid},
                          {"$set": {"assignment": "Unspecified"}})
            )

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

        return {
            "success": True,
            "auto_logs_deleted": auto_del.deleted_count,
            "assignments_reset": reset_count,
            "rule_matches_cleared": rm_del.deleted_count,
            "elapsed_sec": elapsed,
        }

    except Exception as exc:
        logger.exception("❌ clear_assignments failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# NEW TRANSACTIONS
# ----------------------------------------------------------------------

def assign_new_transactions(new_ids: list[str]) -> dict:
    if not new_ids:
        return {"success": True, "updated": 0}

    db = db_module.db
    rm = db["rule_matches"]
    tx = db["transactions"]
    ta = db["transaction_assignments"]

    # Manual overrides remain untouched
    manual_ids = set(
        ta.distinct("id", {"type": "manual", "id": {"$in": new_ids}})
    )
    auto_ids = [tid for tid in new_ids if tid not in manual_ids]

    if not auto_ids:
        return {"success": True, "updated": 0,
                "unchanged": len(manual_ids)}

    rules = list(db["assignment_rules"].find().sort("priority", -1))
    txns = list(tx.find({"id": {"$in": auto_ids}}, {"_id": 0}))

    # Unified primary map
    desc_keys = [_desc_key(t) for t in txns]
    primary_map = get_primary_types_for_descriptions(desc_keys)

    new_match_rows = []

    for txn in txns:
        tid = txn["id"]
        key = _desc_key(txn)
        primary = primary_map.get(key)

        for rule in rules:
            if _rule_matches_txn(txn, rule, primary_type=primary):
                new_match_rows.append({
                    "rule_id": str(rule["_id"]),
                    "txn_id": tid,
                    "priority": rule.get("priority", 0),
                    "assignment": rule.get("assignment"),
                })

    if new_match_rows:
        rm.insert_many(new_match_rows)

    summary = assign_transactions_from_matches_bulk(auto_ids)

    return {
        "success": True,
        **summary,
        "manual_skipped": len(manual_ids),
    }


# ----------------------------------------------------------------------
# MANUAL ASSIGNMENT
# ----------------------------------------------------------------------

def set_transaction_assignment(transaction_id: str, assignment: str) -> dict:
    try:
        db = db_module.db
        tx = db["transactions"]
        ta = db["transaction_assignments"]

        result = tx.update_one(
            {"id": transaction_id},
            {"$set": {"assignment": assignment}}
        )

        if result.matched_count == 0:
            return {"success": False,
                    "message": f"Transaction {transaction_id} not found"}

        ta.insert_one({
            "id": transaction_id,
            "assignment": assignment,
            "type": "manual",
            "timestamp": datetime.utcnow(),
        })

        return {"success": True}

    except Exception as exc:
        logger.exception("❌ Manual assignment failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# RULE MATCHING
# ----------------------------------------------------------------------

def _rule_matches_txn(txn: dict, rule: dict, primary_type=None) -> bool:
    src = (txn.get("source") or "").lower()

    base_desc = _desc_key(txn)  # normalized via your helper
    desc = f"{base_desc} {primary_type.lower()}" if primary_type else base_desc

    amt = float(txn.get("amount") or 0)


    # ----- SOURCE FILTER -----
    if rule.get("source"):
        allowed = [s.strip().lower() for s in rule["source"].split(",") if s.strip()]
        if src not in allowed:
            return False

    # ----- DESCRIPTION FILTER -----
    if rule.get("description"):
        text = rule["description"].lower()

        if "," in text:
            terms = [t.strip() for t in text.split(",") if t.strip()]
            ok = all(term in desc for term in terms)
            if not ok:
                return False

        elif "|" in text:
            terms = [t.strip() for t in text.split("|") if t.strip()]
            ok = any(term in desc for term in terms)
            if not ok:
                return False

        else:
            needle = text.strip()
            ok = needle in desc
            if not ok:
                return False

    # ----- AMOUNT FILTERS -----
    min_amt = rule.get("min_amount")
    max_amt = rule.get("max_amount")

    if min_amt is not None and amt < float(min_amt):
        return False

    if max_amt is not None and amt > float(max_amt):
        return False

    return True


# ----------------------------------------------------------------------
# BEST RULE SELECTION
# ----------------------------------------------------------------------

def find_best_assignment(txn: dict, rules: list, primary_type=None):
    src = (txn.get("source") or "").lower()

    base_desc = _desc_key(txn)
    desc = f"{base_desc} {primary_type.lower()}" if primary_type else base_desc

    amt = float(txn.get("amount") or 0)

    for rule in rules:
        if rule.get("source"):
            allowed = [s.strip().lower() for s in
                       rule["source"].split(",") if s.strip()]
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
            rule.get("priority", 0),
        )

    return None, None, None


# ----------------------------------------------------------------------
# FULL REBUILD
# ----------------------------------------------------------------------

def apply_all_rules() -> dict:
    t0 = time.perf_counter()
    db = db_module.db

    tx = db["transactions"]
    rm = db["rule_matches"]
    ar = db["assignment_rules"]
    ta = db["transaction_assignments"]

    # ----------------------------------
    # Inner helper
    # ----------------------------------
    def __apply_winner_rows(winner_rows):
        if not winner_rows:
            return {"updated": 0, "logged": 0, "skipped": 0}

        txn_ids = [row["txn_id"] for row in winner_rows]

        current_map = {
            d["id"]: d.get("assignment")
            for d in tx.find({"id": {"$in": txn_ids}},
                             {"id": 1, "assignment": 1})
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
            return {"updated": 0, "logged": 0,
                    "skipped": skipped}

        updates = [
            UpdateOne({"id": row["txn_id"]},
                      {"$set": {"assignment": row["assignment"]}})
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
        # -------------------------
        # FAST PATH
        # -------------------------
        if rm.estimated_document_count() > 0:
            logger.info("⚡ apply_all_rules: fast path")

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

            return {
                "path": "fast",
                "success": True,
                **apply_result,
                "elapsed_sec": time.perf_counter() - t0,
            }

        # -------------------------
        # SLOW PATH: rebuild rule_matches
        # -------------------------
        logger.info("🐢 apply_all_rules: slow path (rebuild rule_matches)")

        rules = list(ar.find({}).sort("priority", -1))
        txns = list(tx.find({}, {"_id": 0}))

        desc_keys = [_desc_key(t) for t in txns]
        primary_map = get_primary_types_for_descriptions(desc_keys)

        match_rows = []
        winners = {}

        for txn in txns:
            tid = txn["id"]
            key = _desc_key(txn)
            primary = primary_map.get(key)

            for rule in rules:
                if _rule_matches_txn(txn, rule, primary_type=primary):
                    row = {
                        "rule_id": str(rule["_id"]),
                        "txn_id": tid,
                        "priority": rule.get("priority", 0),
                        "assignment": rule.get("assignment"),
                    }
                    match_rows.append(row)

                    if tid not in winners \
                       or row["priority"] > winners[tid]["priority"]:
                        winners[tid] = row

        if match_rows:
            rm.insert_many(match_rows)

        winner_rows = list(winners.values())
        apply_result = __apply_winner_rows(winner_rows)

        return {
            "path": "slow",
            "success": True,
            "matches": len(match_rows),
            **apply_result,
            "elapsed_sec": time.perf_counter() - t0,
        }

    except Exception as exc:
        logger.exception("❌ apply_all_rules failed: %s", exc)
        return {"success": False, "message": str(exc)}


# ----------------------------------------------------------------------
# INCREMENTAL RULE MGMT
# ----------------------------------------------------------------------

def rule_added_incremental(rule_id: str) -> dict:
    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        from bson import ObjectId
        rule = db["assignment_rules"].find_one({"_id": ObjectId(rule_id)})
        if not rule:
            return {"success": False,
                    "message": f"Rule {rule_id} not found"}

        priority = rule.get("priority", 0)
        assignment = rule.get("assignment")

        all_txns = list(db["transactions"].find({}, {"_id": 0}))

        desc_keys = [_desc_key(t) for t in all_txns]
        primary_map = get_primary_types_for_descriptions(desc_keys)

        CURRENT_MATCHES = []

        for txn in all_txns:
            key = _desc_key(txn)
            primary = primary_map.get(key)

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
    Incrementally handle deletion of a rule.
    Only rule_matches entries referencing this rule_id are removed.
    Then reassign affected transactions using the remaining rule_matches.

    IMPORTANT:
    rule_matches stores rule_id as a STRING, not ObjectId.
    So rule_id must always be cast to str() before performing lookups.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        # 🔥 CRITICAL FIX:
        # Ensure the rule_id matches the string stored in rule_matches
        rule_id = str(rule_id)

        # Find all transactions that were matched by this rule
        PREVIOUS_MATCHES = list(
            rm.find({"rule_id": rule_id}, {"_id": 0, "txn_id": 1})
        )
        PREVIOUS_TXNS = {m["txn_id"] for m in PREVIOUS_MATCHES}

        # Remove rule_matches entries for this rule
        rm.delete_many({"rule_id": rule_id})

        # Reassign these TXNs based on the remaining rule_matches
        result = assign_transactions_from_matches_bulk(PREVIOUS_TXNS)

        return {
            "success": True,
            "previous_matches": len(PREVIOUS_MATCHES),
            "impacted_txns": len(PREVIOUS_TXNS),
            "assign_result": result,
            "elapsed_sec": time.perf_counter() - t0,
        }

    except Exception as exc:
        logger.exception("❌ delete_rule_incremental failed: %s", exc)
        return {"success": False, "message": str(exc)}


def rule_updated_incremental(rule_id: str) -> dict:
    t0 = time.perf_counter()
    db = db_module.db
    rm = db["rule_matches"]

    try:
        from bson import ObjectId
        rule = db["assignment_rules"].find_one({"_id": ObjectId(rule_id)})
        if not rule:
            return {"success": False,
                    "message": f"Rule {rule_id} not found"}

        new_priority = rule.get("priority", 0)
        new_assignment = rule.get("assignment")

        PREVIOUS_MATCHES = list(
            rm.find({"rule_id": rule_id}, {"_id": 0, "txn_id": 1})
        )
        PREVIOUS_TXNS = {m["txn_id"] for m in PREVIOUS_MATCHES}

        all_txns = list(db["transactions"].find({}, {"_id": 0}))

        desc_keys = [_desc_key(t) for t in all_txns]
        primary_map = get_primary_types_for_descriptions(desc_keys)

        CURRENT_MATCHES = []
        for txn in all_txns:
            key = _desc_key(txn)
            primary = primary_map.get(key)

            if _rule_matches_txn(txn, rule, primary_type=primary):
                CURRENT_MATCHES.append({
                    "rule_id": rule_id,
                    "txn_id": txn["id"],
                    "priority": new_priority,
                    "assignment": new_assignment,
                })

        CURRENT_TXNS = {m["txn_id"] for m in CURRENT_MATCHES}

        rm.delete_many({"rule_id": rule_id})
        if CURRENT_MATCHES:
            rm.insert_many(CURRENT_MATCHES)

        IMPACTED = PREVIOUS_TXNS.union(CURRENT_TXNS)

        result = assign_transactions_from_matches_bulk(IMPACTED)

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


# ----------------------------------------------------------------------
# PATCH: REAPPLY RULES WHEN MERCHANT TYPES CHANGE
# ----------------------------------------------------------------------

def apply_rules_for_updated_descriptions(desc_keys: list[str]) -> dict:
    """
    Given a list of normalized descriptions whose merchant types changed,
    re-match and re-assign all affected transactions.
    """
    logger = logging.getLogger(__name__)

    if not desc_keys:
        logger.info("[assign_rules] No updated descriptions.")
        return {"success": True, "count": 0}

    desc_keys = list(set([dk.lower() for dk in desc_keys]))

    transactions = db_module.db["transactions"]

    cursor = transactions.find(
        {"normalized_description": {"$in": desc_keys}},
        {"_id": 0, "id": 1},
    )
    affected_ids = [d["id"] for d in cursor]

    if not affected_ids:
        logger.info("[assign_rules] No transactions affected.")
        return {"success": True, "count": 0}

    logger.info(
        f"[assign_rules] Updating {len(affected_ids)} transactions "
        f"matching {len(desc_keys)} updated descriptions."
    )

    return assign_transactions_from_matches_bulk(affected_ids)
