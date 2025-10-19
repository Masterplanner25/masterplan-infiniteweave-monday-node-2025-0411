from collections import Counter
import nltk
import textstat
from text_constraints import enforce_word_limit

# Ensure required tokenizer is available
nltk.download("punkt", quiet=True)

def extract_keywords(text: str, top_n=10):
    words = nltk.word_tokenize(text.lower())
    words = [word for word in words if word.isalnum()]
    freq_dist = Counter(words)
    return freq_dist.most_common(top_n)

def keyword_density(text: str, keyword: str):
    words = nltk.word_tokenize(text.lower())
    return round((words.count(keyword.lower()) / len(words)) * 100, 2)

def generate_meta_description(text: str, limit: int = 160):
    """Generate a concise meta description using text constraints and sentence-safe trimming."""
    description = enforce_word_limit(text, limit, mode="soft", sentence_safe=True)
    return description.strip()

def seo_analysis(text: str, top_n=10):
    """Performs a basic SEO analysis on given text."""
    word_count = len(nltk.word_tokenize(text))
    readability = textstat.flesch_reading_ease(text)
    keywords = extract_keywords(text, top_n)
    densities = {kw[0]: keyword_density(text, kw[0]) for kw in keywords}
    return {
        "word_count": word_count,
        "readability": readability,
        "top_keywords": [kw[0] for kw in keywords],
        "keyword_densities": densities,
    }

