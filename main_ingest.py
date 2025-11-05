# main_ingest.py

"""
Standalone entry point for ingestion.

Usage:
    poetry run python main_ingest.py
"""

from financials.ingest import run_ingestion

if __name__ == "__main__":
    run_ingestion()
