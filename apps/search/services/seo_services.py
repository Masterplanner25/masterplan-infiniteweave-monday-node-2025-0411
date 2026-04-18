from __future__ import annotations

from collections import Counter
import logging
import re

import nltk
import textstat

from AINDY.utils import enforce_word_limit, prepare_input_text

logger = logging.getLogger(__name__)
_TOKENIZER_AVAILABLE: bool | None = None


def _ensure_tokenizer() -> bool:
    global _TOKENIZER_AVAILABLE
    if _TOKENIZER_AVAILABLE is not None:
        return _TOKENIZER_AVAILABLE
    try:
        nltk.data.find("tokenizers/punkt")
        _TOKENIZER_AVAILABLE = True
    except LookupError:
        logger.warning("NLTK punkt tokenizer not available; using regex fallback for SEO tokenization")
        _TOKENIZER_AVAILABLE = False
    return _TOKENIZER_AVAILABLE


def _tokenize_words(text: str) -> list[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    if _ensure_tokenizer():
        try:
            return list(nltk.word_tokenize(normalized))
        except LookupError:
            logger.warning("NLTK tokenizer lookup failed at runtime; falling back to regex tokenization")
        except Exception as exc:
            logger.warning("NLTK tokenization failed; falling back to regex tokenization: %s", exc)
    return re.findall(r"\b\w+\b", normalized)


def extract_keywords(text: str, top_n: int = 10):
    words = _tokenize_words(text.lower())
    words = [word for word in words if word.isalnum()]
    freq_dist = Counter(words)
    return freq_dist.most_common(top_n)


def keyword_density(text: str, keyword: str):
    words = [word for word in _tokenize_words(text.lower()) if word.isalnum()]
    if not words:
        return 0.0
    return round((words.count(keyword.lower()) / len(words)) * 100, 2)


def seo_analysis(text: str, top_n: int = 10):
    """Performs a basic SEO analysis on given text."""
    prepared_text = prepare_input_text(text)
    words = _tokenize_words(prepared_text)
    word_count = len(words)
    readability = textstat.flesch_reading_ease(prepared_text)
    keywords = extract_keywords(prepared_text, top_n)
    densities = {kw[0]: keyword_density(prepared_text, kw[0]) for kw in keywords}
    return {
        "word_count": word_count,
        "readability": readability,
        "top_keywords": [kw[0] for kw in keywords],
        "keyword_densities": densities,
    }


def generate_meta_description(text: str, limit: int = 160):
    """Generate a concise meta description using text constraints and sentence-safe trimming."""
    description = enforce_word_limit(text, limit, mode="soft", sentence_safe=True)
    return description.strip()

