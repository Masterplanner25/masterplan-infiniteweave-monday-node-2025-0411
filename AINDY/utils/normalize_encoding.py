# utils/normalize_encoding.py
import unicodedata

def normalize_encoding(text: str) -> str:
    """
    Normalize unicode text to NFC form and ensure UTF-8 compatibility.
    Converts fancy quotes, dashes, etc. to canonical equivalents.
    """
    if not isinstance(text, str):
        try:
            text = text.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    # Normalize Unicode form
    normalized = unicodedata.normalize("NFC", text)
    # Strip non-printable control chars
    cleaned = "".join(ch for ch in normalized if ch.isprintable() or ch in ("\n", "\t"))
    return cleaned.strip()
