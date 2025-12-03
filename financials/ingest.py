# financials/ingest.py

import threading
import logging
from financials.drive import GoogleDrive

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def run_ingestion(year=None):
    """Fetch normalized statement data from Google Drive and save to MongoDB."""

    logger.info("🔄 Ingestion started… initializing clients")

    # Lazy imports to avoid circular imports
    from financials.calculator import FinancialsCalculator
    from financials.assign_rules import assign_new_transactions
    from financials import db as db_module

    # Drive + Calculator
    drive = GoogleDrive('roger_drive')
    logger.info("GoogleDrive client ready")

    calc = FinancialsCalculator(drive)
    logger.info("FinancialsCalculator ready")

    # DB
    transactions = db_module.db["transactions"]
    logger.info("MongoDB connection ready (collection: transactions)")

    # Determine which years to process
    year_list = calc.get_folder_names()
    if year is not None:
        year = str(year)
        if year not in year_list:
            logger.warning(f"⚠️ Year {year} not found in Drive folders {year_list}")
            year_list = []
        else:
            year_list = [year]

    logger.info(f"Discovered {len(year_list)} year folders to ingest: {year_list}")

    has_transaction_ids = hasattr(calc, "add_transaction_ids")
    all_new_ids = []      # collect IDs from all years

    for idx, yr in enumerate(year_list, start=1):
        logger.info(f"[{idx}/{len(year_list)}] Loading data for year {yr}")

        try:
            df = calc.load_year_data(yr, logger=logger)
            if df is None or df.empty:
                logger.info(f"No data found for {yr}, skipping")
                continue

            # Generate transaction IDs if needed
            if has_transaction_ids:
                df = calc.add_transaction_ids(df)

            # Insert into Mongo — now returns a list of inserted IDs
            inserted_ids = calc.save_to_collection(df, transactions, logger=logger)

            # Must be a list if using the updated save_to_collection
            if not isinstance(inserted_ids, list):
                raise TypeError(
                    "save_to_collection() must return a list of inserted IDs; "
                    f"got {type(inserted_ids)}"
                )

            # Add inserted IDs (if any)
            if inserted_ids:
                all_new_ids.extend(inserted_ids)

        except Exception as e:
            logger.error(f"Error processing year {yr}: {e}", exc_info=True)
            continue

    logger.info("Ingestion complete. Running incremental assignment…")

    # Perform incremental assignment for all new IDs
    if all_new_ids:
        from financials.utils.google_types import get_types_for_transactions
        # Load any new google_types associated with transactions
        # get_types_for_transactions(txns=all_new_ids, live=True, primary=True)
        # Update matching rules and perform assignments
        assign_summary = assign_new_transactions(all_new_ids)
        logger.info(f"🔧 Incremental assignment result: {assign_summary}")
    else:
        logger.info("No new transactions inserted — skipping assignment.")

    logger.info("✅ Ingestion fully complete.")


def start_background_ingestion():
    """Launch ingestion on a background thread (for Flask)."""
    t = threading.Thread(target=run_ingestion, daemon=True)
    t.start()
    return t
