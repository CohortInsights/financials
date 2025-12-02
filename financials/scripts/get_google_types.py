# financials/scripts/get_google_types.py

"""
Google Merchant-Type Enrichment Tool

This script runs the merchant-centric Google Places enrichment pipeline
from financials.utils.google_types.

It is intentionally separate from update_indexes.py so that:
- index management stays clean,
- enrichment logic can grow independently with its own CLI flags.
"""
from dotenv import load_dotenv
load_dotenv()

import argparse
import logging
import datetime
import pandas as pd
import os

from financials.utils.google_types import get_types_for_query
from financials import db as db_module

# ------------------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)


# ------------------------------------------------------------------------------
# CSV Importer (kept for reference; not exposed via CLI)
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# Query builder
# ------------------------------------------------------------------------------

def build_query(source=None, year=None, description=None):
    query = {}

    if source:
        query["source"] = source

    if year:
        y = int(year)
        start = datetime.datetime(y, 1, 1)
        end = datetime.datetime(y + 1, 1, 1)
        query["date"] = {"$gte": start, "$lt": end}

    if description:
        query["description"] = {"$regex": description, "$options": "i"}
        logger.info(f"[get_google_types] Applying description filter: {description!r}")

    return query


# ------------------------------------------------------------------------------
# Operations
# ------------------------------------------------------------------------------

def enrich_filtered_transactions(source=None, year=None, description=None, live=False, force=False):
    """
    Enrich merchant types for transactions restricted by source/year/description.
    After enrichment, reapply rule matching + assignments for updated descriptions.
    """
    query = build_query(source=source, year=year, description=description)

    if query:
        logger.info(f"[get_google_types] Enriching transactions with filter: {query}")
    else:
        logger.info("[get_google_types] Enriching ALL transactions (no filters provided)")

    projection = {"_id": 0, "id": 1, "description": 1}

    try:
        # Get results including merchant updates
        result = get_types_for_query(
            query,
            projection=projection,
            apply=False,
            live=True if force else live,
            interactive=True,
            force=force,
        )

        merchant_updates = result.get("merchant_updates", [])

        # ----------------------------------------------------------
        # NEW: Extract updated normalized_descriptions and reapply rules
        # ----------------------------------------------------------
        try:
            if merchant_updates:
                from financials.assign_rules import apply_rules_for_updated_descriptions

                updated_keys = []
                for upd in merchant_updates:
                    flt = getattr(upd, "_filter", {})
                    if isinstance(flt, dict) and "normalized_description" in flt:
                        updated_keys.append(flt["normalized_description"])

                if updated_keys:
                    logger.info(
                        f"[get_google_types] Re-applying rules for {len(updated_keys)} updated descriptions..."
                    )
                    apply_rules_for_updated_descriptions(updated_keys)

        except Exception as e:
            logger.error(
                f"[get_google_types] Failed to apply rules for updated descriptions: {e}",
                exc_info=True
            )

        logger.info("[get_google_types] Enrichment complete.")

    except RuntimeError as e:
        logger.info(f"[get_google_types] Enrichment aborted: {e}")


# ------------------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Google merchant-type enrichment tool"
    )

    parser.add_argument("--source", type=str,
                        help="Restrict enrichment to a given transaction source (e.g. BMO, Citi, Schwab)")

    parser.add_argument("--year", type=int,
                        help="Restrict enrichment to a specific year of transactions")

    parser.add_argument("--live", action="store_true",
                        help="Perform LIVE Google Places lookups (only for missing merchants).")

    parser.add_argument("--force", action="store_true",
                        help="Force live lookups for ALL merchants, overwriting cached results.")

    parser.add_argument("--description", type=str,
                        help="Case-insensitive substring to filter transactions by description")

    args = parser.parse_args()

    enrich_filtered_transactions(
        source=args.source,
        year=args.year,
        description=args.description,
        live=args.live,
        force=args.force
    )
