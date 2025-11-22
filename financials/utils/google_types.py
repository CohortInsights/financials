from dotenv import load_dotenv
load_dotenv()

import logging
import datetime
import os
import json
import time
from urllib import request, error
from pymongo import UpdateOne

from financials import db as db_module

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MERCHANT_COLL = "google_merchant_types"

# Approximate blended cost per merchant (search + details) in USD
# searchText ≈ $2/1000, getPlace ≈ $17/1000 → $19/1000
ESTIMATED_COST_PER_MERCHANT = 19.0 / 1000.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_types_for_descriptions(descriptions, live=False, interactive=False):
    """
    Core method.

    Accepts a list of raw description strings.
    - Normalizes and deduplicates them.
    - Ensures merchant index exists.
    - Loads cached merchant records from google_merchant_types.
    - If live=False:
        - Returns only cached types (status == "ok"); never calls Google.
    - If live=True:
        - Computes which merchants need lookup (no record or status != "ok").
        - If interactive=True:
            - Shows count + estimated cost + sample descriptions.
            - Prompts user to confirm before calling Google.
        - Performs Google lookups for missing merchants.
        - Writes results to merchant collection.
    Returns:
        dict[str, list[str]]  # { normalized_description_key: [google_types] }
    """
    if not descriptions:
        return {}

    db = db_module.db
    merchant = db[MERCHANT_COLL]
    _ensure_merchant_index(merchant)

    type_map_coll = db["google_type_mappings"]

    # 1. Normalize & dedupe descriptions
    normalized = [_normalize_description(d) for d in descriptions]
    unique_desc = sorted(set(normalized))

    logger.info(f"[google_types] Processing {len(unique_desc)} unique descriptions")

    # 2. Load valid types for filtering
    valid_types = set(type_map_coll.distinct("google_type"))

    # 3. Load cached merchant records
    cached_records = {
        record["description_key"]: record
        for record in merchant.find(
            {"description_key": {"$in": unique_desc}},
            {"_id": 0}
        )
    }

    results = {}
    needs_lookup = []

    for desc in unique_desc:
        record = cached_records.get(desc)

        # We consider a record "cached" only if lookup_status == "ok"
        if record and record.get("google_lookup_status") == "ok":
            results[desc] = record.get("google_types", [])
        else:
            needs_lookup.append(desc)

    logger.info(
        f"[google_types] Cached={len(results)}, Needs lookup={len(needs_lookup)}"
    )

    # -----------------------------------------------------------------------
    # DRY RUN / NON-LIVE MODE: no Google API calls, no DB writes
    # -----------------------------------------------------------------------
    if not live:
        if needs_lookup:
            logger.info(
                "[google_types] Live mode disabled; "
                f"{len(needs_lookup)} merchants have no cached types."
            )
        # For non-live mode, merchants without data just get empty lists
        for desc in needs_lookup:
            results.setdefault(desc, [])
        return results

    # -----------------------------------------------------------------------
    # LIVE MODE: perform real Google Places lookups, with safety
    # -----------------------------------------------------------------------
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        logger.error(
            "[google_types] LIVE mode requested but GOOGLE_PLACES_API_KEY is not set. "
            "Skipping Google lookups."
        )
        for desc in needs_lookup:
            results.setdefault(desc, [])
        return results

    if not needs_lookup:
        logger.info("[google_types] No merchants require live lookup.")
        return results

    # Safety: show cost & prompt before making any paid calls
    if interactive:
        _prompt_for_live_confirmation(needs_lookup)

    # Now perform real lookups
    ops = []
    timestamp = datetime.datetime.utcnow()

    for idx, desc in enumerate(needs_lookup, start=1):
        logger.info(f"[google_types] ({idx}/{len(needs_lookup)}) Looking up '{desc}'...")

        place_id, raw_types = _lookup_google_by_text(desc, api_key)
        filtered = _filter_google_types(raw_types, valid_types)
        status = "ok" if filtered or place_id else "not_found"

        ops.append(
            UpdateOne(
                {"description_key": desc},
                {
                    "$set": {
                        "description_key": desc,
                        "google_place_id": place_id,
                        "google_types": filtered,
                        "google_lookup_status": status,
                        "google_last_checked": timestamp,
                    }
                },
                upsert=True,
            )
        )

        results[desc] = filtered

        # Basic rate limiting for safety
        time.sleep(0.2)

    if ops:
        logger.info(
            f"[google_types] Performing bulk write of {len(ops)} merchant updates..."
        )
        merchant.bulk_write(ops, ordered=False)

    logger.info(
        f"[google_types] Merchant-type enrichment complete. Total={len(results)}."
    )

    return results


def get_types_for_transactions(txns, apply=False, live=False, interactive=False):
    """
    Accepts a list of full transaction records (dicts).

    Behavior:
      - Extracts descriptions from txns.
      - Resolves merchant types via get_types_for_descriptions().
      - If apply=False (default):
            Returns { txn_id: [google_types...] }.
      - If apply=True:
            Computes tokens = description_tokens + google_types
            Stores them in txn["_tokens"] (NOT persisted).
            Returns the modified list of txns.
    """
    if not txns:
        return [] if apply else {}

    descriptions = [txn["description"] for txn in txns]

    # Merchant-type lookup (normalized keys)
    merchant_map = get_types_for_descriptions(
        descriptions, live=live, interactive=interactive
    )

    if not apply:
        # Map txn_id -> google types
        id_to_types = {}
        for txn in txns:
            desc_key = _normalize_description(txn["description"])
            gtypes = merchant_map.get(desc_key, [])
            id_to_types[txn["id"]] = gtypes
        return id_to_types

    # apply=True -> modify txns in-place with _tokens
    for txn in txns:
        desc_key = _normalize_description(txn["description"])
        gtypes = merchant_map.get(desc_key, [])
        _apply_tokens_to_transaction(txn, gtypes)

    return txns


def get_types_for_transaction_ids(ids, apply=False, live=False, interactive=False):
    """
    Loads transactions by ID, then delegates to get_types_for_transactions().

    Args:
        ids: list[str] of transaction IDs
        apply: see get_types_for_transactions()
        live: if True, perform live Google lookups (with safety)
    """
    if not ids:
        return [] if apply else {}

    db = db_module.db
    trx_coll = db["transactions"]

    txns = list(
        trx_coll.find(
            {"id": {"$in": ids}},
            {"_id": 0, "id": 1, "description": 1}
        )
    )

    return get_types_for_transactions(
        txns, apply=apply, live=live, interactive=interactive
    )


def get_types_for_query(query_dict, projection=None, apply=False,
                        live=False, interactive=False):
    """
    Runs a Mongo query to fetch transaction records, then delegates
    to get_types_for_transactions().

    Args:
        query_dict: MongoDB filter dict for transactions.
        projection: MongoDB projection dict. If None, uses:
                    {"_id": 0, "id": 1, "description": 1}
        apply: see get_types_for_transactions().
        live: if True, perform live Google lookups (with safety)
    """
    db = db_module.db
    trx_coll = db["transactions"]

    if projection is None:
        projection = {"_id": 0, "id": 1, "description": 1}

    txns = list(trx_coll.find(query_dict, projection))

    return get_types_for_transactions(
        txns, apply=apply, live=live, interactive=interactive
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_merchant_index(merchant_coll):
    """
    Ensure we have an index on description_key for efficient lookups.
    Safe to call repeatedly (idempotent).
    """
    merchant_coll.create_index("description_key", unique=True)


def _normalize_description(desc):
    """
    Normalize a description string into a merchant key.

    For now:
      - uppercase
      - strip leading/trailing whitespace
    """
    return desc.upper().strip()


def _prompt_for_live_confirmation(needs_lookup):
    """
    Show how many merchants will be looked up, estimate cost,
    show a sample of descriptions, and prompt the user to confirm.
    """
    count = len(needs_lookup)
    est_cost = round(count * ESTIMATED_COST_PER_MERCHANT, 2)

    logger.info("[google_types] LIVE mode enabled.")
    logger.info(f"[google_types] Merchants requiring Google lookup: {count}")
    logger.info(f"[google_types] Estimated incremental cost: ${est_cost:.2f}")

    sample = needs_lookup[:10]
    if sample:
        logger.info("[google_types] Sample merchants to be looked up:")
        for desc in sample:
            logger.info(f"    - {desc}")

    # Explicit prompt to user (no calls until confirmed)
    answer = input(
        f"\nThis will perform {count} Google Places lookups "
        f"(estimated cost ≈ ${est_cost:.2f}). Proceed? [y/N]: "
    ).strip().lower()

    if answer not in ("y", "yes"):
        logger.info("[google_types] User declined live lookup. Aborting.")
        # Abort by raising a soft exception that caller can catch or treat as no-op
        raise RuntimeError("Live Google lookup aborted by user.")


def _lookup_google_by_text(cleaned_desc, api_key):
    """
    Google Places API v3 'searchText' call.

    Returns:
        (place_id: str | None, raw_types: list[str])

    If any error occurs or no place is found, returns (None, []).
    """
    url = "https://places.googleapis.com/v1/places:searchText"

    body = {
        "textQuery": cleaned_desc,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        # Only request what we need: id and types
        "X-Goog-FieldMask": "places.id,places.types",
    }

    data = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=10) as resp:
            resp_data = resp.read().decode("utf-8")
            payload = json.loads(resp_data)

    except error.HTTPError as e:
        logger.warning(
            f"[google_types] HTTPError during Google searchText for '{cleaned_desc}': "
            f"{e.code} {e.reason}"
        )
        return None, []
    except error.URLError as e:
        logger.warning(
            f"[google_types] URLError during Google searchText for '{cleaned_desc}': "
            f"{e.reason}"
        )
        return None, []
    except Exception as e:
        logger.warning(
            f"[google_types] Unexpected error during Google searchText for "
            f"'{cleaned_desc}': {e}"
        )
        return None, []

    places = payload.get("places") or []
    if not places:
        return None, []

    first = places[0]
    place_id = first.get("id")
    raw_types = first.get("types") or []

    return place_id, raw_types


def _filter_google_types(raw_types, valid_types):
    """
    Filters raw Google types through the whitelist in google_type_mappings.
    """
    return [t for t in raw_types if t in valid_types]


def _apply_tokens_to_transaction(txn, google_types):
    """
    Compute tokens for rule matching from:
        - description tokens
        - filtered google_types

    Store them in txn["_tokens"].

    This field is intended for in-memory consumption by the rule engine
    and is NOT persisted back to MongoDB.
    """
    desc_tokens = _tokenize_description(txn["description"])
    txn["_tokens"] = desc_tokens + list(google_types)


def _tokenize_description(desc):
    """
    Basic tokenizer:
        - uppercase
        - split on whitespace
    """
    return desc.upper().split()
