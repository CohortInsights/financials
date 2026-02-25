# main_ingest.py

import argparse
from financials.ingest import run_ingestion

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest financial statements into MongoDB")
    parser.add_argument(
        "--year",
        type=str,
        help="Ingest only a single year (e.g. 2024). If omitted, all years are processed."
    )
    args = parser.parse_args()

    # Pass the year (may be None) into the ingestion routine
    run_ingestion(year=args.year)
