from flask import Blueprint, jsonify, request
from financials import db as db_module
from financials.web import app
from bson import ObjectId

@app.route("/api/rules", methods=["GET"])
def get_rules():
    """Return all assignment rules."""
    collection = db_module.db["assignment_rules"]
    rules = list(collection.find({}, {"_id": 0}))
    return jsonify(rules)

@app.route("/api/rules", methods=["POST"])
def add_rule():
    """Insert a new rule into MongoDB."""
    collection = db_module.db["assignment_rules"]
    data = request.get_json() or {}

    # Construct clean document
    rule = {
        "priority": int(data.get("priority", 0)),
        "source": data.get("source", "").strip(),
        "description": data.get("description", "").strip(),
        "min_amount": float(data.get("min_amount") or 0),
        "max_amount": float(data.get("max_amount") or 0),
        "assignment": data.get("assignment", "").strip(),
    }

    collection.insert_one(rule)
    print(f"🟢 Added rule: {rule}")
    return jsonify({"success": True})

@app.route("/api/rules/<string:rule_id>", methods=["DELETE"])
def delete_rule(rule_id: str):
    """Delete a rule by its Mongo _id."""
    collection = db_module.db["assignment_rules"]
    try:
        collection.delete_one({"_id": ObjectId(rule_id)})
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)})
