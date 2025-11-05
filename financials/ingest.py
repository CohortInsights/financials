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


def run_ingestion():
    """Fetch normalized statement data from Google Drive and save to MongoDB."""
    logger.info("🔄 Ingestion started… initializing clients")

    # Lazy imports to avoid circular imports
    from financials.calculator import FinancialsCalculator
    from financials import db as db_module

    # Drive + Calculator
    drive = GoogleDrive('roger_drive')
    logger.info("GoogleDrive client ready")

    calc = FinancialsCalculator(drive)
    logger.info("FinancialsCalculator ready")

    # DB
    transactions = db_module.db["transactions"]
    logger.info("MongoDB connection ready (collection: transactions)")

    # Loop over all year folders
    year_list = calc.get_folder_names()
    logger.info(f"Discovered {len(year_list)} year folders: {year_list}")

    has_transaction_ids = hasattr(calc, "add_transaction_ids")
    for idx, year in enumerate(year_list, start=1):
        logger.info(f"[{idx}/{len(year_list)}] Loading data for year {year}")
        try:
            df = calc.load_year_data(year, logger=logger)
            if df is None or df.empty:
                logger.info(f"No data found for {year}, skipping")
                continue

            # Add transaction IDs if supported
            if has_transaction_ids:
                df = calc.add_transaction_ids(df)

            # Insert into Mongo (dedup via unique index)
            inserted = calc.save_to_collection(df, transactions, logger=logger)

        except Exception as e:
            logger.error(f"Error processing year {year}: {e}", exc_info=True)
            continue

    logger.info("✅ Ingestion complete.")


def start_background_ingestion():
    """Launch ingestion on a background thread (for Flask)."""
    t = threading.Thread(target=run_ingestion, daemon=True)
    t.start()
    return t
