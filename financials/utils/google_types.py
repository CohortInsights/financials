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

# Approximate blended cost per merchant lookup (search + details)
ESTIMATED_COST_PER_MERCHANT = 19.0 / 1000.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_types_for_descriptions(descriptions, live=False, interactive=False):
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

    Returns:
        dict[str, list[str]]:
            Maps normalized description_key → list of filtered Google types.
            For non-live mode, missing merchants return an empty list.
    """
    if not descriptions:
        return {}

    db = db_module.db
    merchant = db[MERCHANT_COLL]
    _ensure_merchant_index(merchant)

    type_map_coll = db["google_type_mappings"]

    # Normalize & dedupe
    normalized = [_normalize_description(d) for d in descriptions]
    unique_desc = sorted(set(normalized))

    logger.info(f"[google_types] Processing {len(unique_desc)} unique descriptions")

    valid_types = set(type_map_coll.distinct("google_type"))

    # Load cached merchant records
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
        if record and record.get("google_lookup_status") == "ok":
            results[desc] = record.get("google_types", [])
        else:
            needs_lookup.append(desc)

    logger.info(
        f"[google_types] Cached={len(results)}, Needs lookup={len(needs_lookup)}"
    )

    # Non-live mode → do not issue Google API calls
    if not live:
        if needs_lookup:
            logger.info(
                "[google_types] Live mode disabled; "
                f"{len(needs_lookup)} merchants have no cached types."
            )
        for desc in needs_lookup:
            results.setdefault(desc, [])
        return results

    # Live mode → perform lookups
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

    if interactive:
        _prompt_for_live_confirmation(needs_lookup)

    ops = []
    timestamp = datetime.datetime.utcnow()

    # Load merchant priority scoring map once for the run
    type_priority_map = {
        doc["google_type"]: doc.get("priority", 0)
        for doc in type_map_coll.find({}, {"_id": 0, "google_type": 1, "priority": 1})
    }

    for idx, desc in enumerate(needs_lookup, start=1):
        logger.info(f"[google_types] ({idx}/{len(needs_lookup)}) Looking up '{desc}'...")

        place_id, raw_types = _lookup_google_by_text(desc, api_key)
        filtered = _filter_google_types(raw_types, valid_types)
        primary = _select_primary_type(filtered, type_priority_map)

        status = "ok" if filtered or place_id else "not_found"

        ops.append(
            UpdateOne(
                {"description_key": desc},
                {
                    "$set": {
                        "description_key": desc,
                        "google_place_id": place_id,
                        "google_types": filtered,
                        "google_primary_type": primary,
                        "google_lookup_status": status,
                        "google_last_checked": timestamp,
                    }
                },
                upsert=True,
            )
        )

        results[desc] = filtered
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
    Resolve Google merchant types for a batch of full transaction records.

    Args:
        txns (list[dict]):
            Must include at least "id" and "description".
        apply (bool):
            If False:
                Return dict {id → list of google_types}.
            If True:
                Injects a "_tokens" list into each transaction record, consisting
                of description tokens + google_types.
        live (bool):
            Whether to call Google for missing merchants.
        interactive (bool):
            Whether to show safety prompt for live mode.

    Returns:
        dict[str, list[str]] | list[dict]:
            Either a mapping id → google types (apply=False),
            OR the modified transaction list (apply=True).
    """
    if not txns:
        return [] if apply else {}

    descriptions = [txn["description"] for txn in txns]
    merchant_map = get_types_for_descriptions(
        descriptions, live=live, interactive=interactive
    )

    if not apply:
        out = {}
        for txn in txns:
            desc_key = _normalize_description(txn["description"])
            out[txn["id"]] = merchant_map.get(desc_key, [])
        return out

    # apply=True
    for txn in txns:
        desc_key = _normalize_description(txn["description"])
        gtypes = merchant_map.get(desc_key, [])
        _apply_tokens_to_transaction(txn, gtypes)

    return txns


def get_types_for_transaction_ids(ids, apply=False, live=False, interactive=False):
    """
    Resolve Google merchant types for a set of transaction IDs.

    Args:
        ids (list[str]): Transaction primary keys.
        apply (bool): See get_types_for_transactions().
        live (bool): Live Google lookups allowed?
        interactive (bool): Display prompt before billing Google?

    Returns:
        Same as get_types_for_transactions().
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
    Lookup Google merchant types for a MongoDB query over transactions.

    Args:
        query_dict (dict):
            Mongo filter for the transactions collection.
        projection (dict | None):
            Mongo projection. Defaults to {"id", "description"}.
        apply (bool):
            Whether to inject tokens into the results.
        live (bool):
            Whether to call Google for missing merchants.
        interactive (bool):
            Whether to confirm cost with user.

    Returns:
        Dict or modified list of txns, same as get_types_for_transactions().
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
    Ensure we have a unique index on description_key.
    Called every run; safe because index creation is idempotent.

    Args:
        merchant_coll (pymongo.collection.Collection)
    """
    merchant_coll.create_index("description_key", unique=True)


def _normalize_description(desc):
    """
    Normalize raw transaction descriptions.

    Steps:
        - Convert to uppercase
        - Strip leading/trailing whitespace

    Args:
        desc (str): Raw transaction description.

    Returns:
        str: Normalized description_key.
    """
    return desc.upper().strip()


def _prompt_for_live_confirmation(needs_lookup):
    """
    Prompt user with safety confirmation for live Google lookups.

    Args:
        needs_lookup (list[str]): List of merchants lacking cached lookups.

    Raises:
        RuntimeError: If user declines the operation.
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

    answer = input(
        f"\nThis will perform {count} Google Places lookups "
        f"(estimated cost ≈ ${est_cost:.2f}). Proceed? [y/N]: "
    ).strip().lower()

    if answer not in ("y", "yes"):
        logger.info("[google_types] User declined live lookup. Aborting.")
        raise RuntimeError("Live Google lookup aborted by user.")


def _lookup_google_by_text(cleaned_desc, api_key):
    """
    Perform Google Places API searchText lookup for a cleaned description.

    Args:
        cleaned_desc (str): Normalized merchant description.
        api_key (str): Google Places API key.

    Returns:
        tuple:
            (place_id: str | None,
             raw_types: list[str])
    """
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
    """
    Filter Google-provided categories down to the curated whitelist.

    Args:
        raw_types (list[str]):
            Types returned by Google for a merchant.
        valid_types (set[str]):
            Allowed types from google_type_mappings.

    Returns:
        list[str]:
            Types that are both in Google output and in the whitelist,
            preserving Google's original order.
    """
    return [t for t in raw_types if t in valid_types]


def _select_primary_type(filtered_types, type_priority_map):
    """
    Determine the single best merchant type via weighted scoring:

        score = priority_from_csv + google_reverse_rank

    Where google_reverse_rank = N - idx for a list of length N.

    Args:
        filtered_types (list[str]):
            Whitelisted Google types returned by the API.
        type_priority_map (dict[str, int]):
            Merchant type → priority score loaded from CSV → Mongo.

    Returns:
        str | None:
            The highest scoring type, or None if filtered_types is empty.
    """
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
    """
    Insert a "_tokens" field into a transaction object for rule matching.

    Tokens include:
        - Description tokens (splitting uppercase description on whitespace)
        - Google merchant types (filtered list)

    Args:
        txn (dict):
            Transaction record (modified in-place).
        google_types (list[str]):
            Filtered list of merchant types.
    """
    desc_tokens = _tokenize_description(txn["description"])
    txn["_tokens"] = desc_tokens + list(google_types)


def _tokenize_description(desc):
    """
    Tokenize a raw description for rule matching.

    Args:
        desc (str): Raw description.

    Returns:
        list[str]: Uppercase tokens split on whitespace.
    """
    return desc.upper().split()
