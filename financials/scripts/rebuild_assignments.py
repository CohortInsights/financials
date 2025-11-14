# main_rebuild_assignments.py
"""
Assignment Rebuild Script

This script operates in two modes:

Default mode:
    poetry run python main_rebuild_assignments.py
    → Runs apply_all_rules() only.
    → Fast-path (uses rule_matches) or slow-path depending on state.

Full rebuild mode:
    poetry run python main_rebuild_assignments.py --clear
    → Clears all auto assignments & rule_matches, then
      runs apply_all_rules() to rebuild everything from scratch.

Usage:
    --clear      Optional flag to wipe auto state before rebuilding
"""

import argparse
import logging
from financials.assign_rules import clear_assignments, apply_all_rules

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_rebuild_assignments")


def main():
    parser = argparse.ArgumentParser(description="Rebuild assignment engine state")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all auto assignments and rule_matches before rebuilding"
    )

    args = parser.parse_args()

    if args.clear:
        logger.info("🧹 --clear flag detected: clearing auto assignments and rule_matches...")
        clear_result = clear_assignments()
        logger.info("🧹 Clear complete: %s", clear_result)
    else:
        logger.info("ℹ️ No --clear flag detected: keeping existing rule_matches and manual assignments.")

    logger.info("🔁 Applying all rules...")
    apply_result = apply_all_rules()
    logger.info("🔁 Done: %s", apply_result)

    logger.info("✅ Assignment rebuild process complete.")


if __name__ == "__main__":
    main()
