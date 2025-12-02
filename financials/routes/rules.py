from flask import jsonify, request, Response
from financials import db as db_module
from financials.web import app
from bson import ObjectId
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def parse_amount(value):
    """
    Convert incoming JSON value for min_amount/max_amount into a float or None.

    Rules:
    - None, "", "null" (case-insensitive) -> None
    - numeric strings / numbers -> float(...)
    - anything else -> None
    """
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if v == "" or v.lower() == "null":
            return None
        try:
            return float(v)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------
# READ ALL RULES
# ----------------------------------------------------------------------
@app.route("/api/rules", methods=["GET"])
def get_rules():
    """Return all assignment rules."""
    fmt = request.args.get("format", "json")
    collection = db_module.db["assignment_rules"]
    rules = list(collection.find({}))

    # Convert ObjectId → string
    for rule in rules:
        rule["_id"] = str(rule["_id"])

    if fmt == "csv":
        df = pd.DataFrame(rules)
        csv_data = df.to_csv(index=False)

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=assignment_rules.csv"
            }
        )

    return jsonify(rules)


# ----------------------------------------------------------------------
# CREATE RULE
# ----------------------------------------------------------------------
@app.route("/api/rules", methods=["POST"])
def add_rule():
    """Insert a new rule into MongoDB and incrementally apply it."""
    collection = db_module.db["assignment_rules"]
    data = request.get_json() or {}

    rule = {
        "priority": int(data.get("priority", 0)),
        "source": data.get("source", "").strip(),
        "description": data.get("description", "").strip(),
        "min_amount": parse_amount(data.get("min_amount")),
        "max_amount": parse_amount(data.get("max_amount")),
        "assignment": data.get("assignment", "").strip(),
    }

    try:
        result = collection.insert_one(rule)
        logger.info("🟢 Added rule: %s", rule)

        # NEW — incremental create instead of full rebuild
        from financials.assign_rules import rule_added_incremental
        incremental = rule_added_incremental(str(result.inserted_id))

        return jsonify({
            "success": True,
            "id": str(result.inserted_id),
            "incremental": incremental
        })

    except Exception as exc:
        logger.exception("❌ Error adding rule")
        return jsonify({"success": False, "message": str(exc)}), 400


# ----------------------------------------------------------------------
# UPDATE RULE
# ----------------------------------------------------------------------
@app.route("/api/rules/<string:rule_id>", methods=["PUT"])
def update_rule(rule_id: str):
    """Update an existing rule by its Mongo _id, then incrementally reapply it."""
    collection = db_module.db["assignment_rules"]
    data = request.get_json() or {}

    update = {
        "priority": int(data.get("priority", 0)),
        "source": data.get("source", "").strip(),
        "description": data.get("description", "").strip(),
        "min_amount": parse_amount(data.get("min_amount")),
        "max_amount": parse_amount(data.get("max_amount")),
        "assignment": data.get("assignment", "").strip(),
    }

    try:
        result = collection.update_one({"_id": ObjectId(rule_id)}, {"$set": update})
        success = result.modified_count > 0
        logger.info("✏️ Updated rule %s: %s", rule_id, update)

        # NEW — incremental edit instead of full rebuild
        from financials.assign_rules import rule_updated_incremental
        incremental = rule_updated_incremental(rule_id)

        return jsonify({"success": success, "incremental": incremental})

    except Exception as exc:
        logger.exception("❌ Error updating rule %s", rule_id)
        return jsonify({"success": False, "message": str(exc)}), 400


# ----------------------------------------------------------------------
# DELETE RULE
# ----------------------------------------------------------------------
from financials.assign_rules import rule_deleted_incremental

from financials.assign_rules import rule_deleted_incremental

@app.route("/api/rules/<string:rule_id>", methods=["DELETE"])
def delete_rule(rule_id: str):
    import logging
    logger = logging.getLogger(__name__)
    collection = db_module.db["assignment_rules"]

    try:
        # 1️⃣ Perform incremental cleanup FIRST
        result = rule_deleted_incremental(rule_id)

        # 2️⃣ Delete the rule itself afterward
        delete_result = collection.delete_one({"_id": ObjectId(rule_id)})

        if delete_result.deleted_count == 0:
            logger.warning("⚠️ Tried to delete missing rule %s", rule_id)
            # The rule_matches cleanup was done; warn but don't fail
            result["warning"] = "Rule not found in assignment_rules"
            return jsonify(result), 200

        logger.info("🗑️ Deleted rule %s", rule_id)
        logger.info("🔁 Rules reapplied after deletion: %s", result)

        return jsonify(result)

    except Exception as exc:
        logger.exception("❌ Rule deletion failed: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500
