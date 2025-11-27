"""
Update rules consistent with the merchant_google_types collection
Safe to run multiple times — MongoDB will skip duplicates.

This version includes performance-oriented indexes to support
auto-assignment, bulk updates, rule evaluation, and the new
rule_matches collection for incremental rule updates.
"""

import os
import csv
import logging
from financials import db as db_module

logger = logging.getLogger(__name__)


def install_google_type_rules():
    """
    Install rules based on financials/cfg/google_types_to_expenses.csv.
    For each row:
        priority     = 2
        source       = ""
        description  = google_type
        assignment   = assignment from CSV

    Matching rule for update/insert:
        priority == 2 AND source == "" AND description == google_type
    """
    db = db_module.db
    rules = db["assignment_rules"]

    cfg_path = os.path.join(
        os.path.dirname(__file__), "..", "cfg", "google_types_to_expenses.csv"
    )
    cfg_path = os.path.abspath(cfg_path)

    if not os.path.exists(cfg_path):
        logger.warning(f"⚠️ google_types_to_expenses.csv not found: {cfg_path}")
        return

    logger.info(f"📥 Installing Google-type rules from {cfg_path}...")

    inserted = 0
    updated = 0

    with open(cfg_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            google_type = row.get("google_type")
            assignment = row.get("assignment")

            if not google_type:
                continue

            result = rules.update_one(
                {"priority": 2, "source": "", "description": google_type},
                {
                    "$set": {
                        "source": "",
                        "description": google_type,
                        "assignment": assignment,
                        "priority": 2,
                    }
                },
                upsert=True,
            )

            if result.matched_count == 1:
                updated += 1
            else:
                inserted += 1

    logger.info(
        f"✅ Installed Google-type rules: {updated} updated, {inserted} inserted."
    )


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    install_google_type_rules()
