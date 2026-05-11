"""
A.I.N.D.Y. Input Hygiene Layer
------------------------------
Provides text preprocessing utilities used throughout the system.

Modules:
    - text_constraints: Word-limit and trimming functions.
    - sanitize_text: Remove HTML, emojis, and excess whitespace.
    - normalize_encoding: Normalize Unicode and encoding consistency.

These utilities ensure that all text entering the database or
analysis pipeline is clean, UTF-8-safe, and length-controlled.
"""

from .text_constraints import count_words, trim_to_word_limit, enforce_word_limit
from .sanitize_text import sanitize_text
from .normalize_encoding import normalize_encoding

def prepare_input_text(raw_text: str, limit: int = 500, sentence_safe: bool = True, mode: str = "hard") -> str:
    """
    Master input-preparation function combining normalization, sanitization,
    and word-limit enforcement.

    Args:
        raw_text (str): The input text.
        limit (int): Maximum word count to retain.
        sentence_safe (bool): Keep sentence boundaries if possible.
        mode (str): 'hard' for exact cutoff, 'soft' for ~±5% tolerance.

    Returns:
        str: Sanitized, normalized, and length-constrained text.
    """
    text = normalize_encoding(raw_text)
    text = sanitize_text(text)
    text = enforce_word_limit(text, limit=limit, sentence_safe=sentence_safe, mode=mode)
    return text
