import argparse
from datetime import datetime
from typing import List, Dict, Any


def normalize_description(desc: str) -> str:
    """
    Python-side normalization for descriptions.

    All normalized descriptions MUST be lowercase so they remain
    consistent with:
        - _desc_key(txn)
        - rule matching (lowercase comparisons)
        - Google merchant-type lookups
        - primary_map keys
    """
    if not desc:
        return ""
    # collapse whitespace + lowercase
    return " ".join(desc.split()).lower()


def mongo_normalize_description(field: str = "$description") -> dict:
    """
    MongoDB-side normalization expression that exactly mirrors the Python
    normalize_description() logic.

    Ensures migrations, updates, and lookups use the same lowercase key.
    """
    return {
        "$trim": {
            "input": {
                "$toLower": {
                    "$replaceAll": {
                        "input": {
                            "$trim": {"input": field}
                        },
                        "find": "  ",  # collapse double spaces
                        "replacement": " "
                    }
                }
            }
        }
    }


def build_txn_query(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Build a MongoDB query for the `transactions` collection based on CLI args.

    Filters:
    - --source: exact match on `source`
    - --year:   date range [year-01-01, (year+1)-01-01)
    - --desc:   case-insensitive substring match on `description`
    """
    query: Dict[str, Any] = {}

    if args.source:
        query["source"] = args.source

    if args.year is not None:
        start = datetime(args.year, 1, 1)
        end = datetime(args.year + 1, 1, 1)
        query["date"] = {"$gte": start, "$lt": end}

    if args.desc:
        # case-insensitive "contains" match on description
        query["description"] = {
            "$regex": args.desc,
            "$options": "i",
        }

    return query

Chec