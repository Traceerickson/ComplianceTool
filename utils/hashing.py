import hashlib


def sha256_hex(text: str) -> str:
    """Return a hex SHA-256 digest for the given text (utf-8)."""
    if text is None:
        text = ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha1_hex(text: str) -> str:
    """Return a hex SHA-1 digest for the given text (utf-8). Useful for shorter IDs."""
    if text is None:
        text = ""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()

