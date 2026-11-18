from __future__ import annotations
import re
import numpy as np
import pandas as pd


def parse_number(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return np.nan
    if isinstance(v, (int, float, np.number)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return np.nan
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[^0-9eE+\-.]", "", s)
    try:
        x = float(s)
        return -x if neg else x
    except ValueError:
        return np.nan


def parse_vat(v, default=0.15):
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return float(default)
    s = str(v).strip().replace("%", "")
    try:
        x = float(s)
    except ValueError:
        return float(default)
    if x > 1:
        x /= 100.0
    return max(x, 0.0)


def parse_dates(series: pd.Series) -> pd.Series:
    # Pandas mixed format handles ISO, dd-Mon-yy and most blind-test variants.
    try:
        return pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=False)
    except TypeError:
        return pd.to_datetime(series, errors="coerce", infer_datetime_format=True)


def first_valid_date(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    out = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    for c in cols:
        if c not in df.columns:
            continue
        p = parse_dates(df[c])
        out = out.fillna(p)
    return out
