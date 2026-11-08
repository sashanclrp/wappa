"""Reserved expiry-index keys that ordinary cache maintenance must preserve."""

EXPIRY_DUE_KEY = "__system__:expiry:due"
EXPIRY_RECORDS_KEY = "__system__:expiry:records"


def is_expiry_index_key(key: str) -> bool:
    return key in (EXPIRY_DUE_KEY, EXPIRY_RECORDS_KEY)
