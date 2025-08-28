import hashlib


def hash_text(text: str) -> str:
    """Return SHA256 hash for given text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
