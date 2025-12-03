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
import pandas as pd

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


def import_google_types_from_csv():
    base_dir = os.path.dirname(os.path.dirname(__file__))  # financials/
    csv_path = os.path.join(base_dir, "cfg", "google_types_to_expenses.csv")

    logger.info(f"[import] Loading CSV: {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    required = {"google_type", "score"}
    if not required.issubset(df.columns):
        raise RuntimeError(
            f"CSV missing required columns: {required - set(df.columns)}"
        )

    db = db_module.db
    coll = db["google_type_mappings"]

    logger.info("[import] Clearing google_type_mappings collection...")
    coll.delete_many({})

    records = []
    for _, row in df.iterrows():
        gt = str(row["google_type"]).strip()
        pr = int(row["score"])
        records.append({"google_type": gt, "priority": pr})

    if records:
        coll.insert_many(records)

    logger.info(f"[import] Loaded {len(records)} google type mappings.")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    import_google_types_from_csv()
    install_google_type_rules()
