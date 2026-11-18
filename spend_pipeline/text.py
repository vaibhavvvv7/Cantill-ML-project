from __future__ import annotations
import hashlib
import re
import unicodedata
import pandas as pd

LEGAL_SUFFIXES = {
    "pty", "ltd", "limited", "inc", "incorporated", "corp", "corporation",
    "llc", "plc", "co", "company", "sa", "gmbh", "bv", "ag"
}

COMMON_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "with", "at", "by", "from",
    "in", "on", "to", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "but", "if", "then", "else",
    "when", "up", "down", "out", "over", "under", "again", "further", "once",
    "here", "there", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "can", "will", "just", "should", "now", "per", "via"
}


def clean_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def stem_token(word: str) -> str:
    """Lightweight rule-based stemmer for English procurement vocabulary."""
    if len(word) <= 3:
        return word
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ss"):
        return word
    if word.endswith("s") and not word.endswith("us") and not word.endswith("is"):
        word = word[:-1]
    if word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("tion") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ment") and len(word) > 6:
        word = word[:-4]
    return word


def extract_keywords(text: str) -> list[str]:
    """Tokenize, clean, filter stopwords, and stem tokens."""
    cleaned = clean_text(text)
    tokens = cleaned.split()
    return [stem_token(t) for t in tokens if t not in COMMON_STOPWORDS and len(t) > 1]


def normalize_supplier(value) -> str:
    toks = clean_text(value).split()
    toks = [t for t in toks if t not in LEGAL_SUFFIXES]
    return " ".join(toks)


def normalize_identifier(value) -> str:
    s = clean_text(value)
    return re.sub(r"\s+", "", s)


def stable_key(prefix: str, value: str, size: int = 12) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:size]
    return f"{prefix}_{digest}"


def join_text(row, columns: list[str]) -> str:
    parts = []
    for c in columns:
        if c in row.index:
            v = row[c]
            if pd.notna(v) and str(v).strip():
                parts.append(str(v))
    return " | ".join(parts)
