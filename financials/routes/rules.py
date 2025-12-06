from flask import jsonify, request, Response
from financials import db as db_module
from financials.web import app
from bson import ObjectId
import logging
import pandas as pd
from datetime import datetime, date

logger = logging.getLogger(__name__)


def parse_amount(value):
    """
    Convert incoming JSON value for min_amount/max_amount into a float or None.
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


def parse_date(value):
    """
    Convert incoming YYYY-MM-DD strings into datetime.datetime for Mongo storage.
    Returns None for blank, null, or malformed inputs.
    """
    if not value:
        return None
    try:
        # Mongo-friendly datetime (midnight UTC/local)
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
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

    # Convert ObjectId → string and datetime.date → ISO strings
    for rule in rules:
        rule["_id"] = str(rule["_id"])
        if isinstance(rule.get("start_date"), (datetime, date)):
            rule["start_date"] = rule["start_date"].strftime("%Y-%m-%d")
        if isinstance(rule.get("end_date"), (datetime, date)):
            rule["end_date"] = rule["end_date"].strftime("%Y-%m-%d")

    if fmt == "csv":
        df = pd.DataFrame(rules)
        csv_data = df.to_csv(index=False)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=assignment_rules.csv"}
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
        # ⭐ NEW DATE FIELDS
        "start_date": parse_date(data.get("start_date")),
        "end_date": parse_date(data.get("end_date")),
    }

    try:
        result = collection.insert_one(rule)
        logger.info("🟢 Added rule: %s", rule)

        # Incremental rule-application
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
        # ⭐ NEW DATE FIELDS
        "start_date": parse_date(data.get("start_date")),
        "end_date": parse_date(data.get("end_date")),
    }

    try:
        result = collection.update_one({"_id": ObjectId(rule_id)}, {"$set": update})
        success = result.modified_count > 0
        logger.info("✏️ Updated rule %s: %s", rule_id, update)

        # Incremental rule update
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

@app.route("/api/rules/<string:rule_id>", methods=["DELETE"])
def delete_rule(rule_id: str):
    collection = db_module.db["assignment_rules"]

    try:
        # Remove matches first
        result = rule_deleted_incremental(rule_id)

        # Delete rule from DB
        delete_result = collection.delete_one({"_id": ObjectId(rule_id)})

        if delete_result.deleted_count == 0:
            result["warning"] = "Rule not found in assignment_rules"
            return jsonify(result), 200

        return jsonify(result)

    except Exception as exc:
        logger.exception("❌ Rule deletion failed: %s", exc)
        return jsonify({"success": False, "message": str(exc)}), 500
