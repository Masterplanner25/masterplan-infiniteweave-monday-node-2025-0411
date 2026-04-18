"""
Authorship Module — Epistemic Reclaimer
Part of the A.I.N.D.Y. framework

Purpose:
    - Counteracts invisible AI fingerprinting
    - Restores creative sovereignty through semantic watermark embedding
    - Produces traceable authorship metadata for Memory Bridge integration

Collaborative Adaptation:
    Each author or node can pass unique `originator` and `motto` values,
    preserving decentralized authorship identity.
"""

import re
import hashlib
from datetime import datetime

# --- Heuristic patterns to detect latent AI signatures ---
FINGERPRINT_HEURISTICS = [
    re.compile(r'(?<!\n)\s{2,}'),         # suspicious multiple spaces
    re.compile(r'[^\x00-\x7F]+'),         # non-ASCII characters
    re.compile(r'\u200b|\u200c|\u200d'),  # zero-width characters
    re.compile(r'(?:significant|enable|robust|utilize)'),  # GPT-favored vocab
]

# --- Default personalization (can be overridden) ---
AUTHOR_NAME = "Knight, Shawn"
AUTHOR_MOTTO = "Quicker, Better, Smarter, Faster"
INVISIBLE_WATERMARK = "\u200c\u200b\u200d"  # invisible sequence

# --- Dynamic signature template ---
SIGNATURE_BLOCK = """
---
Epistemic Reclamation Protocol: Step 6
Processed through authorship reclamation layer.
Originator: {originator}
Message: {motto}
Timestamp: {timestamp}
SHA256 Hash: {hash}
Invisible Semantic Watermark Present.
---
"""

# -------------------- CORE METHODS --------------------

def strip_formatting(text: str) -> str:
    """Normalize spacing and remove stray newlines."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_fingerprints(text: str) -> list:
    """Detect patterns that may indicate AI generation fingerprints."""
    results = []
    for pattern in FINGERPRINT_HEURISTICS:
        matches = pattern.findall(text)
        if matches:
            results.append((pattern.pattern, matches[:5]))
    return results


def add_entropy(text: str) -> str:
    """Disrupts predictable patterns to increase originality entropy."""
    lines = text.split(".")
    disrupted = [
        line.strip() + ("." if i % 2 == 0 else "...")
        for i, line in enumerate(lines)
        if line.strip()
    ]
    return " ".join(disrupted)


def embed_unicode_fingerprint(text: str, watermark: str = INVISIBLE_WATERMARK) -> str:
    """Embed invisible semantic watermark across text."""
    paragraphs = text.split("\n")
    watermarked = []
    for i, p in enumerate(paragraphs):
        if i % 3 == 0:
            watermarked.append(watermark + p)
        else:
            watermarked.append(p)
    return "\n".join(watermarked)


def add_signature(
    text: str,
    originator: str = AUTHOR_NAME,
    motto: str = AUTHOR_MOTTO,
    watermark: str = INVISIBLE_WATERMARK
) -> str:
    """
    Append semantic signature block to the text.
    Includes cryptographic hash, timestamp, and identity markers.
    """
    clean = text.encode("utf-8")
    hash_digest = hashlib.sha256(clean).hexdigest()
    timestamp = datetime.utcnow().isoformat()

    signature = SIGNATURE_BLOCK.format(
        originator=originator,
        motto=motto,
        timestamp=timestamp,
        hash=hash_digest
    )

    return f"{text}\n\n{signature}{watermark}"


def epistemic_reclaim(
    raw_text: str,
    originator: str = AUTHOR_NAME,
    motto: str = AUTHOR_MOTTO
) -> tuple[str, list]:
    """
    Executes full reclamation pipeline:
        - normalize
        - detect fingerprints
        - introduce entropy
        - embed semantic watermark
        - append signature
    Returns (final_text, detected_fingerprints)
    """
    stripped = strip_formatting(raw_text)
    flagged = detect_fingerprints(stripped)
    disrupted = add_entropy(stripped)
    watermarked = embed_unicode_fingerprint(disrupted)
    final = add_signature(watermarked, originator=originator, motto=motto)
    return final, flagged


# -------------------- TEST BLOCK --------------------
if __name__ == "__main__":
    sample_text = """OpenAI Recognition
Leah Belsky — General Manager at OpenAI — highlighted the ChatGPT Self-Educated headline from my profile.
She featured it publicly, signaling the intersection of human learning and AI cognition.
That moment symbolized the rise of AI-native thinkers reshaping visibility, authorship, and recognition.
"""

    reclaimed_text, fingerprints = epistemic_reclaim(sample_text)
    print("\n\n--- RECLAIMED TEXT ---\n")
    print(reclaimed_text)
    print("\n\n--- DETECTED FINGERPRINTS ---\n")
    print(fingerprints)
