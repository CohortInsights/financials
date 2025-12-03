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



# ------------------------y
# y
# -----------------------------------------------------
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

def assign_primary_and_apply_rules_for_query(source=None, year=None, description=None, live=False, force=False):
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
        # Get primary types mapped to the txn_id
        txn_merchant_map = get_types_for_query(
            query,
            projection=projection,
            live=True if force else live,
            interactive=True,
            force=force,
            primary=True,
        )

        # ----------------------------------------------------------
        # NEW: Extract updated normalized_descriptions and reapply rules
        # ----------------------------------------------------------
        try:
            if txn_merchant_map:
                from financials.assign_rules import assign_primary_and_apply_rules_for_transactions
                assign_primary_and_apply_rules_for_transactions(txn_merchant_map)

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

    assign_primary_and_apply_rules_for_query(
        source=args.source,
        year=args.year,
        description=args.description,
        live=args.live,
        force=args.force
    )
