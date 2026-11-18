from __future__ import annotations
import pandas as pd
import numpy as np
from .config import data_path
from .normalize import parse_number, parse_vat, first_valid_date
from .text import clean_text, normalize_supplier, normalize_identifier, join_text
from .matching import extract_po, extract_po_line

CANONICAL_DEFAULTS={
    "source_id":"", "source_name":"", "supplier_id":"", "supplier_name":"",
    "material_id":"", "description":"", "status":"", "currency":"", "amount_raw":np.nan,
    "amount_reporting":np.nan, "quantity":np.nan, "po_number":"", "po_line":"", "invoice_number":"",
    "date":pd.NaT
}

def _col(df, name, default=""):
    return df[name] if name and name in df.columns else pd.Series(default,index=df.index)

def ingest_source(cfg: dict, sc: dict) -> pd.DataFrame:
    raw=pd.read_csv(data_path(cfg,sc["file"]), low_memory=False)
    out=pd.DataFrame(index=raw.index)
    out["source_id"]=_col(raw,sc["id_column"]).astype(str)
    out["source_name"]=sc["name"]
    out["record_id"]=sc.get("record_prefix","")+out["source_id"]
    mapping=sc.get("columns",{})
    for canon in ["supplier_id","supplier_name","material_id","status","currency","quantity","po_number","po_line","invoice_number"]:
        src=mapping.get(canon)
        out[canon]=_col(raw,src, np.nan if canon=="quantity" else "")
    desc_cols=sc.get("description_columns",[])
    out["description"] = raw.apply(lambda r: join_text(r,desc_cols),axis=1) if desc_cols else ""
    date_cols=sc.get("date_columns",[])
    out["date"]=first_valid_date(raw,date_cols) if date_cols else pd.NaT
    ac=sc["amount"]
    out["amount_raw"]=_col(raw,ac["column"],np.nan).map(parse_number)
    if ac.get("type","net")=="gross":
        vat_col=ac.get("tax_column")
        vat=_col(raw,vat_col,np.nan).map(lambda x: parse_vat(x,ac.get("default_tax",0.15)))
        out["vat_rate_norm"]=vat
        out["amount_net"]=out["amount_raw"]/(1+vat)
    else:
        out["amount_net"]=out["amount_raw"]
    out["amount_reporting"]=out["amount_net"]
    # Retain raw fields needed by configurable rules/classification.
    for c in set(sc.get("retain_columns",[])+cfg.get("classification",{}).get("feature_columns",[])+cfg.get("spend_rules",{}).get("learn_exact_columns",[])+cfg.get("spend_rules",{}).get("non_procurement_text_columns",[])):
        if c in raw.columns and c not in out.columns: out[c]=raw[c]
    out["supplier_norm"]=out["supplier_name"].map(normalize_supplier)
    out["description_norm"]=out["description"].map(clean_text)
    out["material_id"]=out["material_id"].fillna("").astype(str).replace("nan","")
    out["invoice_norm"]=out["invoice_number"].map(normalize_identifier)
    out["po_norm"]=out["po_number"].map(extract_po)
    # if PO line is separately available, prefer it; otherwise parse PO ref suffix.
    sep_line=out["po_line"].map(lambda x: "" if pd.isna(x) or str(x).strip()=="" else str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x))
    parsed_line=out["po_number"].map(extract_po_line)
    out["po_line_norm"]=sep_line.where(sep_line.ne(""),parsed_line)
    out["date_parse_failed"]=False
    if date_cols:
        any_raw=pd.Series(False,index=raw.index)
        for c in date_cols:
            if c in raw.columns: any_raw |= raw[c].notna() & raw[c].astype(str).str.strip().ne("")
        out["date_parse_failed"]=any_raw & out["date"].isna()
    out["amount_parse_failed"]=out["amount_reporting"].isna()
    return out


def apply_fx(cfg: dict, df: pd.DataFrame, sc: dict) -> pd.DataFrame:
    fx=cfg.get("fx")
    if not fx: return df
    reporting=cfg.get("reporting_currency","USD")
    currency=df["currency"].fillna(reporting).astype(str).str.upper().str.strip()
    amount=df["amount_net"].astype(float)
    rate_col=fx.get("inline_rate_column")
    # retained raw rate is present if configured
    rate=pd.to_numeric(df[rate_col],errors="coerce") if rate_col and rate_col in df.columns else pd.Series(np.nan,index=df.index)
    out=amount.copy()
    non=currency.ne(reporting.upper())
    use_inline=non & rate.notna() & rate.ne(0)
    out.loc[use_inline]=amount.loc[use_inline]/rate.loc[use_inline]
    need=non & ~use_inline
    if need.any() and fx.get("file"):
        rates=pd.read_csv(data_path(cfg,fx["file"]))
        month=df["date"].dt.to_period("M").astype(str)
        lookup={(str(r[fx.get("currency_column","currency")]).upper(),str(r[fx.get("month_column","month")])):float(r[fx.get("rate_column","units_per_usd")]) for _,r in rates.iterrows()}
        vals=[]
        for i in df.index:
            if not need.loc[i]: vals.append(np.nan); continue
            vals.append(lookup.get((currency.loc[i],month.loc[i]),np.nan))
        fallback=pd.Series(vals,index=df.index)
        ok=need & fallback.notna() & fallback.ne(0)
        out.loc[ok]=amount.loc[ok]/fallback.loc[ok]
        df["fx_missing"]=need & ~ok
    else:
        df["fx_missing"]=False
    df["amount_reporting"]=out
    return df
