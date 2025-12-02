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
                        "find": "  ",       # collapse double spaces
                        "replacement": " "
                    }
                }
            }
        }
    }
