# financials/routes/assign.py

from flask import jsonify, request
from financials.web import app
from financials.assign_rules import set_transaction_assignment


@app.route("/assign_transaction", methods=["POST"])
def assign_transaction():
    """
    Assigns or updates a transaction's 'assignment' field manually from the dashboard.

    Expected JSON body:
        {
            "transaction_id": "<sha256-id>",
            "assignment": "Expense.Food.Restaurant"
        }
    """
    try:
        data = request.get_json(force=True)
        transaction_id = data.get("transaction_id")
        assignment = data.get("assignment")

        if not transaction_id or not assignment:
            app.logger.warning(
                "Invalid /assign_transaction request — missing transaction_id or assignment"
            )
            return (
                jsonify({"success": False, "message": "Missing transaction_id or assignment"}),
                400,
            )

        result = set_transaction_assignment(transaction_id, assignment)

        if result.get("success"):
            app.logger.info(
                "Transaction %s manually assigned to %s", transaction_id, assignment
            )
            return jsonify({"success": True})
        else:
            message = result.get("message", "Unknown error")
            app.logger.warning(
                "Assignment failed for %s: %s", transaction_id, message
            )
            return jsonify(result), 500

    except Exception as e:
        app.logger.error("Error in /assign_transaction: %s", e, exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 500
