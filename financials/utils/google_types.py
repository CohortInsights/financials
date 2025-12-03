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
from financials.utils.helpers import normalize_description

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MERCHANT_COLL = "google_merchant_types"

# Approximate blended cost per merchant lookup (search + details)
ESTIMATED_COST_PER_MERCHANT = 19.0 / 1000.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
# ----------------------------------------------------------------------
# GOOGLE PRIMARY TYPE HELPER
# ----------------------------------------------------------------------

def get_primary_types_for_descriptions(descriptions):
    """
    Lightweight helper:
    Return mapping normalized_desc_key → google_primary_type or None.
    Uses only cached merchant entries; no live Google calls.
    """
    if not descriptions:
        return {}

    db = db_module.db
    merchant = db[MERCHANT_COLL]

    normalized = [normalize_description(d) for d in descriptions]
    keys = sorted(set(normalized))

    cursor = merchant.find(
        {"normalized_description": {"$in": keys}},
        {"_id": 0, "normalized_description": 1, "google_primary_type": 1}
    )

    result = {k: None for k in keys}
    for rec in cursor:
        result[rec["normalized_description"]] = rec.get("google_primary_type")

    return result


def get_types_for_descriptions(descriptions, live=False, interactive=False, force=False, primary=False):
    """
    Resolve Google merchant types for a list of description strings.

    Args:
        descriptions (list[str]):
            Raw transaction descriptions.
        live (bool):
            If False:
                Only use cached lookup results already stored in MongoDB.
            If True:
                Perform live Google Places lookups for merchants that are missing
                or have no "ok" lookup_status.
        interactive (bool):
            If True and live=True:
                Prompt user with estimated cost before making any paid requests.
        force (bool):
            If True:
                Ignore cache entirely, always perform live lookups, and always
                overwrite stored results (still with interactive confirmation).
        primary (bool):
                Whether the return type is the primary google type (True) or the list of all google_types (False)

    Returns:
        dict[str, list[str]]:
            Maps normalized normalized_description → list of filtered Google types.
            For non-live mode, missing merchants return an empty list.
    """
    if not descriptions:
        return {}

    db = db_module.db
    merchant = db[MERCHANT_COLL]
    _ensure_merchant_index(merchant)

    type_map_coll = db["google_type_mappings"]

    # Normalize & dedupe
    normalized = [normalize_description(d) for d in descriptions]
    unique_desc = sorted(set(normalized))

    logger.info(f"[google_types] Processing {len(unique_desc)} unique descriptions")

    valid_types = set(type_map_coll.distinct("google_type"))

    # Load cached merchant records
    cached_records = {
        record["normalized_description"]: record
        for record in merchant.find(
            {"normalized_description": {"$in": unique_desc}},
            {"_id": 0}
        )
    }

    results = {}
    needs_lookup = []

    for desc in unique_desc:
        record = cached_records.get(desc)

        # FORCE MODE — ignore cache entirely
        if force:
            needs_lookup.append(desc)
            continue

        # DEFAULT BEHAVIOR — reuse cached "ok" entries
        if record and record.get("google_lookup_status") in ("ok", "not_found"):
            if primary:
                results[desc] = record.get("google_primary_type", [])
            else:
                results[desc] = record.get("google_types", [])
        else:
            needs_lookup.append(desc)

    logger.info(
        f"[google_types] Cached={len(results)}, Needs lookup={len(needs_lookup)}"
    )

    # Non-live mode → do not issue Google API calls
    if not live and not force:
        if needs_lookup:
            logger.info(
                "[google_types] Live mode disabled; "
                f"{len(needs_lookup)} merchants have no cached types."
            )
        for desc in needs_lookup:
            results.setdefault(desc, [])
        return results

    # Live or forced lookup mode
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        logger.error(
            "[google_types] LIVE mode requested but GOOGLE_PLACES_API_KEY is not set. "
            "Skipping Google lookups."
        )
        for desc in needs_lookup:
            results.setdefault(desc, [])
        return results

    if not needs_lookup and not force:
        logger.info("[google_types] No merchants require live lookup.")
        return results

    # Still prompt user when forcing
    if interactive:
        _prompt_for_live_confirmation(needs_lookup)

    timestamp = datetime.datetime.utcnow()

    # Load merchant priority scoring map once for the run
    type_priority_map = {
        doc["google_type"]: doc.get("priority", 0)
        for doc in type_map_coll.find({}, {"_id": 0, "google_type": 1, "priority": 1})
    }

    # ---------------------------------------------
    # NEW: One-at-a-time writes (no bulk_write)
    # ---------------------------------------------
    for idx, desc in enumerate(needs_lookup, start=1):
        logger.info(f"[google_types] ({idx}/{len(needs_lookup)}) Looking up '{desc}'...")

        place_id, raw_types = _lookup_google_by_text(desc, api_key)
        filtered = _filter_google_types(raw_types, valid_types)
        primary_value = _select_primary_type(filtered, type_priority_map)

        status = "ok" if filtered or place_id else "not_found"

        # Immediate persistence for each merchant update
        merchant.update_one(
            {"normalized_description": desc},
            {
                "$set": {
                    "normalized_description": desc,
                    "google_place_id": place_id,
                    "google_types": filtered,
                    "google_raw_types": raw_types,
                    "google_primary_type": primary_value,
                    "google_lookup_status": status,
                    "google_last_checked": timestamp,
                }
            },
            upsert=True,
        )

        if primary:
            results[desc] = primary_value
        else:
            results[desc] = filtered

        time.sleep(0.2)

    logger.info(
        f"[google_types] Merchant-type enrichment complete. Total={len(results)}."
    )

    return results


def get_types_for_transactions(txns, live=False, interactive=False, force=False, primary=False):
    """
    Resolve Google merchant types for a batch of full transaction records.
    """
    if not txns:
        return []

    descriptions = [txn["description"] for txn in txns]
    merchant_map = get_types_for_descriptions(
        descriptions, live=live, interactive=interactive, force=force, primary=primary
    )

    out = {}
    for txn in txns:
        desc_key = normalize_description(txn["description"])
        out[txn["id"]] = merchant_map.get(desc_key, [])
    return out


def get_types_for_transaction_ids(ids, live=False, interactive=False, force=False, primary=False):
    """
    Resolve Google merchant types for a set of transaction IDs.
    """
    if not ids:
        return []

    db = db_module.db
    trx_coll = db["transactions"]

    txns = list(
        trx_coll.find(
            {"id": {"$in": ids}},
            {"_id": 0, "id": 1, "description": 1}
        )
    )

    return get_types_for_transactions(
        txns, live=live, interactive=interactive, force=force, primary=primary
    )


def get_types_for_query(query_dict, projection=None, live=False, interactive=False, force=False, primary=False):
    """
    Lookup Google merchant types for a MongoDB query over transactions.
    """
    db = db_module.db
    trx_coll = db["transactions"]

    if projection is None:
        projection = {"_id": 0, "id": 1, "description": 1}

    txns = list(trx_coll.find(query_dict, projection))

    return get_types_for_transactions(
        txns, live=live, interactive=interactive, force=force, primary=primary
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_merchant_index(merchant_coll):
    merchant_coll.create_index("normalized_description", unique=True)


def _prompt_for_live_confirmation(needs_lookup):
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

    answer = input(
        f"\nThis will perform {count} Google Places lookups "
        f"(estimated cost ≈ ${est_cost:.2f}). Proceed? [y/N]: "
    ).strip().lower()

    if answer not in ("y", "yes"):
        logger.info("[google_types] User declined live lookup. Aborting.")
        raise RuntimeError("Live Google lookup aborted by user.")


def _lookup_google_by_text(cleaned_desc, api_key):
    url = "https://places.googleapis.com/v1/places:searchText"

    body = {
        "textQuery": cleaned_desc,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
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
    return [t for t in raw_types if t in valid_types]


def _select_primary_type(filtered_types, type_priority_map):
    if not filtered_types:
        return None

    n = len(filtered_types)
    best_type = None
    best_score = -1

    for idx, t in enumerate(filtered_types):
        csv_priority = type_priority_map.get(t, 0)
        google_weight = n - idx
        score = csv_priority + google_weight

        if score > best_score:
            best_score = score
            best_type = t

    return best_type


def _apply_tokens_to_transaction(txn, google_types):
    desc_tokens = _tokenize_description(txn["description"])
    txn["_tokens"] = desc_tokens + list(google_types)


def _tokenize_description(desc):
    return desc.upper().split()
