"""
Backfill script to populate `normalized_description` on all existing
transactions using the SAME logic defined in
financials.utils.helpers.normalize_description().

Safe to run multiple times.
"""

import logging
from financials import db as db_module
from financials.utils.helpers import normalize_description
from pymongo import UpdateOne

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run():
    db = db_module.db
    tx = db["transactions"]

    logger.info("🔍 Checking for transactions missing or corrupted normalized_description…")

    # We consider "corrupted" if normalized_description is an object instead of a string.
    query_missing = {"normalized_description": {"$exists": False}}
    query_corrupted = {"normalized_description": {"$type": "object"}}

    missing_count = tx.count_documents(query_missing)
    corrupted_count = tx.count_documents(query_corrupted)

    logger.info(f"Missing count:   {missing_count}")
    logger.info(f"Corrupted count: {corrupted_count}")

    if missing_count == 0 and corrupted_count == 0:
        logger.info("✅ Nothing to update — all rows already normalized.")
        return

    logger.info("⚙️ Normalizing descriptions in Python…")

    docs = list(
        tx.find(
            {
                "$or": [
                    query_missing,
                    query_corrupted
                ]
            },
            {"_id": 1, "description": 1}
        )
    )

    ops = []
    for d in docs:
        raw = d.get("description") or ""
        norm = normalize_description(raw)
        ops.append(
            UpdateOne(
                {"_id": d["_id"]},
                {"$set": {"normalized_description": norm}}
            )
        )

    if ops:
        result = tx.bulk_write(ops)
        logger.info(
            f"🎉 Update complete. Matched: {result.matched_count}, Modified: {result.modified_count}"
        )
    else:
        logger.info("No documents required updates.")


if __name__ == "__main__":
    run()
