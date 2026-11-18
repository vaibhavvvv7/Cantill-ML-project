from __future__ import annotations
import hashlib
import re
import unicodedata
import pandas as pd

LEGAL_SUFFIXES = {
    "pty", "ltd", "limited", "inc", "incorporated", "corp", "corporation",
    "llc", "plc", "co", "company", "sa", "gmbh", "bv", "ag"
}


def clean_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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
