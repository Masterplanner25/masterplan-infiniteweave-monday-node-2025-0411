# utils/sanitize_text.py
import re
import html
import unicodedata

def strip_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)

def remove_emojis(text: str) -> str:
    """Strip emojis and other non-text symbols."""
    if not text:
        return ""
    emoji_pattern = re.compile(
        "["                     # broad unicode ranges for pictographs
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r"", text)

def collapse_whitespace(text: str) -> str:
    """Normalize multiple spaces, newlines, and tabs."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def sanitize_text(text: str) -> str:
    """Full sanitization pipeline."""
    text = strip_html(text)
    text = remove_emojis(text)
    text = collapse_whitespace(text)
    return text
