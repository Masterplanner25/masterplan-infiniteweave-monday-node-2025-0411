# utils/text_constraints.py

import re

def count_words(text: str) -> int:
    """Counts the number of words in a given text."""
    return len(text.strip().split())


def trim_to_word_limit(text: str, limit: int, sentence_safe: bool = False) -> str:
    """
    Trims text to a given word limit.

    Args:
        text (str): The input text.
        limit (int): Max number of words allowed.
        sentence_safe (bool): If True, avoids cutting sentences awkwardly.

    Returns:
        str: Text trimmed to the word limit.
    """
    words = text.strip().split()

    if len(words) <= limit:
        return text

    if not sentence_safe:
        return " ".join(words[:limit])

    # Sentence-safe trimming
    sentences = re.split(r'(?<=[.!?]) +', text)
    trimmed = []
    count = 0

    for sentence in sentences:
        sentence_words = sentence.strip().split()
        if count + len(sentence_words) > limit:
            break
        trimmed.append(sentence.strip())
        count += len(sentence_words)

    return " ".join(trimmed)


def enforce_word_limit(text: str, limit: int, mode: str = "hard", sentence_safe: bool = False) -> str:
    """
    Applies a word limit to the text.

    Args:
        text (str): The input text.
        limit (int): Word limit.
        mode (str): 'hard' (cut exactly), 'soft' (approx. +/- 5% margin).
        sentence_safe (bool): Try to keep sentence boundaries if possible.

    Returns:
        str: Processed text within the word constraints.
    """
    if mode == "soft":
        margin = int(limit * 0.05)
        lower = limit - margin
        upper = limit + margin
        actual_count = count_words(text)
        if lower <= actual_count <= upper:
            return text

    return trim_to_word_limit(text, limit, sentence_safe)
