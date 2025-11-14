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


def clear_assignments() -> dict:
    """
    Clear all automatic assignments and rule_matches.

    - Removes all type="auto" entries from transaction_assignments
    - Resets transactions.assignment="Unspecified" for all ids that had auto assignments
    - Deletes all rule_matches
    - Leaves manual assignments untouched
    - Leaves assignment_rules untouched
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db

    try:
        ta = db["transaction_assignments"]
        tx = db["transactions"]
        rm = db["rule_matches"]

        # 1️⃣ Get all transaction ids that have ever had auto assignments
        auto_ids = ta.distinct("id", {"type": "auto"})

        # 2️⃣ Delete all auto assignment logs
        auto_del = ta.delete_many({"type": "auto"})

        # 3️⃣ Reset assignments for those transactions (bulk update)
        reset_count = 0
        if auto_ids:
            result = tx.update_many(
                {"id": {"$in": auto_ids}},
                {"$set": {"assignment": "Unspecified"}}
            )
            reset_count = result.modified_count

        # 4️⃣ Clear rule_matches
        rm_del = rm.delete_many({})

        elapsed = time.perf_counter() - t0

        logger.info(
            "🧹 clear_assignments v3: auto_logs=%d, reset=%d, rule_matches=%d in %.3fs",
            auto_del.deleted_count,
            reset_count,
            rm_del.deleted_count,
            elapsed,
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


def assign_new_transactions(new_ids: list[str]) -> dict:
    """
    Incrementally assign ONLY newly ingested transactions.
    Uses rule_matches for everything else.

    Steps:
      - filter manual IDs
      - compute new rule_matches rows for these IDs
      - compute winners via aggregation pipeline
      - assign via assign_transactions_from_matches_bulk()
    """

    if not new_ids:
        return {"success": True, "updated": 0}

    db = db_module.db
    rm = db["rule_matches"]
    tx = db["transactions"]
    ta = db["transaction_assignments"]

    # ----------------------------------------------
    # 1. Filter out manual transactions
    # ----------------------------------------------
    manual_ids = set(
        ta.distinct("id", {"type": "manual", "id": {"$in": new_ids}})
    )
    auto_ids = [tid for tid in new_ids if tid not in manual_ids]

    if not auto_ids:
        return {"success": True, "updated": 0, "unchanged": len(manual_ids)}

    # ----------------------------------------------
    # 2. Load rules sorted by priority DESC
    # ----------------------------------------------
    rules = list(
        db["assignment_rules"].find().sort("priority", -1)
    )

    # ----------------------------------------------
    # 3. Load transactions for these auto_ids
    # ----------------------------------------------
    txns = list(
        tx.find({"id": {"$in": auto_ids}}, {"_id": 0})
    )

    # ----------------------------------------------
    # 4. Compute rule_matches rows for ONLY these txns
    # ----------------------------------------------
    new_match_rows = []
    for txn in txns:
        tid = txn["id"]
        for rule in rules:
            if _rule_matches_txn(txn, rule):
                new_match_rows.append({
                    "rule_id": str(rule["_id"]),
                    "txn_id": tid,
                    "priority": rule.get("priority", 0),
                    "assignment": rule.get("assignment")
                })

    if new_match_rows:
        rm.insert_many(new_match_rows)

    # ----------------------------------------------
    # 5. Winner selection for ONLY these txn_ids
    # ----------------------------------------------
    pipeline = [
        {"$match": {"txn_id": {"$in": auto_ids}}},
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
            "priority": 1
        }}
    ]

    winner_rows = list(rm.aggregate(pipeline))

    # ----------------------------------------------
    # 6. Apply assignments via the shared bulk helper
    # ----------------------------------------------
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
    Apply all rules to all transactions.

    Fast path:
        If rule_matches has content, use MongoDB aggregation to determine
        the highest-priority winner per txn_id and apply those assignments.
        Only transactions whose assignment actually changes are updated.

    Slow path:
        If rule_matches is empty, evaluate all rule × transaction combinations,
        rebuild rule_matches, then apply winners.
        Only transactions whose assignment actually changes are updated.

    All bulk updates & auto-log inserts are handled by a shared internal helper.
    """
    import time
    t0 = time.perf_counter()
    db = db_module.db

    tx = db["transactions"]
    rm = db["rule_matches"]
    ar = db["assignment_rules"]
    ta = db["transaction_assignments"]

    # --------------------------------------------------------------
    # Internal helper for both fast + slow paths
    # --------------------------------------------------------------
    def __apply_winner_rows(winner_rows):
        """
        Bulk-apply assignments based on winner_rows, but only for
        transactions whose assignment actually changes.

        winner_rows must contain dicts of:
            { "txn_id", "rule_id", "assignment", "priority" }
        """
        if not winner_rows:
            return {"updated": 0, "logged": 0, "skipped": 0}

        # Collect all txn_ids involved
        txn_ids = [row["txn_id"] for row in winner_rows]

        # Lookup current assignments in one query
        current_map = {}
        for doc in tx.find({"id": {"$in": txn_ids}}, {"id": 1, "assignment": 1}):
            current_map[doc["id"]] = doc.get("assignment")

        # Filter to only those rows where assignment changes
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

        # Build bulk updates for changed rows only
        updates = [
            UpdateOne(
                {"id": row["txn_id"]},
                {"$set": {"assignment": row["assignment"]}}
            )
            for row in filtered_rows
        ]

        # Build bulk auto logs only for changed rows
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

        # Execute bulk writes
        tx.bulk_write(updates)
        ta.insert_many(logs)

        return {
            "updated": len(updates),
            "logged": len(logs),
            "skipped": skipped,
        }

    try:
        # --------------------------------------------------------------
        # 1️⃣ FAST PATH — rule_matches already populated
        # --------------------------------------------------------------
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
                apply_result["updated"],
                apply_result["skipped"],
                elapsed,
            )

            return {
                "path": "fast",
                "success": True,
                "updated": apply_result["updated"],
                "skipped": apply_result["skipped"],
                "elapsed_sec": elapsed,
            }

        # --------------------------------------------------------------
        # 2️⃣ SLOW PATH — rule_matches empty → full rebuild
        # --------------------------------------------------------------
        logger.info("🐢 apply_all_rules: slow path (rebuilding rule_matches)")

        rules = list(ar.find({}).sort("priority", -1))
        txns = list(tx.find({}, {" _id": 0}))

        match_rows = []
        winners = {}  # txn_id → best match

        for txn in txns:
            tid = txn["id"]
            for rule in rules:
                if _rule_matches_txn(txn, rule):
                    row = {
                        "rule_id": str(rule["_id"]),
                        "txn_id": tid,
                        "priority": rule.get("priority", 0),
                        "assignment": rule.get("assignment"),
                    }
                    match_rows.append(row)

                    if tid not in winners or row["priority"] > winners[tid]["priority"]:
                        winners[tid] = row

        # Insert rule_matches
        if match_rows:
            rm.insert_many(match_rows)

        # Apply winners (using helper with delta-update)
        winner_rows = list(winners.values())
        apply_result = __apply_winner_rows(winner_rows)

        elapsed = time.perf_counter() - t0

        logger.info(
            "🐢 Slow rebuild: matches=%d, updated=%d, skipped=%d in %.3fs",
            len(match_rows),
            apply_result["updated"],
            apply_result["skipped"],
            elapsed,
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
