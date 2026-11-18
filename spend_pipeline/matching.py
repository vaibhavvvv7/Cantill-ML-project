from __future__ import annotations
import re
from collections import defaultdict
import numpy as np
import pandas as pd
from rapidfuzz.fuzz import token_set_ratio
from .text import clean_text, normalize_supplier

PO_RE = re.compile(r"(?<!\d)(\d{7,12})(?!\d)")

def extract_po(v):
    if v is None or pd.isna(v): return ""
    m=PO_RE.search(str(v).replace(",",""))
    return m.group(1) if m else ""

def extract_po_line(v):
    if v is None or pd.isna(v): return ""
    s=str(v)
    m=re.search(r"[/\-]\s*(\d+(?:\.0+)?)\s*$", s)
    if not m: return ""
    try: return str(int(float(m.group(1))))
    except: return ""

def mark_tool_duplicates(tool: pd.DataFrame) -> pd.Series:
    key = (
        tool["invoice_norm"].fillna("") + "|" + tool["supplier_norm"].fillna("") + "|" +
        tool["amount_net"].round(2).fillna(-999999).astype(str) + "|" +
        tool["description_norm"].fillna("")
    )
    # Require invoice number for exact-export duplicate logic; otherwise text collisions can be real spend.
    valid = tool["invoice_norm"].fillna("").ne("")
    dup = pd.Series(False, index=tool.index)
    dup.loc[valid] = key.loc[valid].duplicated(keep="first")
    return dup

def match_a_tool_to_erp(erp: pd.DataFrame, tool: pd.DataFrame) -> tuple[pd.Series, dict[int,str]]:
    """Conservative cross-system matcher. Returns duplicate mask and matched ERP record_id."""
    po_map=defaultdict(list)
    for i,r in erp.iterrows():
        po=str(r.get("po_norm","") or "")
        if po: po_map[po].append(i)
    dup=pd.Series(False,index=tool.index)
    matched={}
    for ti,tr in tool.iterrows():
        po=tr.get("po_norm","")
        if not po or po not in po_map: continue
        ta=tr.get("amount_net",np.nan)
        if pd.isna(ta): continue
        # Amount-first pruning keeps matching fast even for POs with 100+ receipts.
        candidates=[]
        for ei in po_map[po]:
            ea=erp.at[ei,"amount_reporting"]
            if pd.isna(ea): continue
            denom=max(abs(float(ta)),abs(float(ea)),1.0)
            rel=abs(float(ta)-float(ea))/denom
            if rel <= 0.05: candidates.append((rel,ei))
        candidates.sort(key=lambda x:x[0])
        best=None
        for rel,ei in candidates[:5]:
            er=erp.loc[ei]
            amount_score=max(0,1-rel/0.05)
            qty_score=0
            tq=tr.get("quantity",np.nan); eq=er.get("quantity",np.nan)
            if pd.notna(tq) and pd.notna(eq):
                qden=max(abs(float(tq)),abs(float(eq)),1.0)
                qty_score=max(0,1-abs(float(tq)-float(eq))/qden)
            desc_score=token_set_ratio(str(tr.get("description_norm","")),str(er.get("description_norm","")))/100
            supp_score=token_set_ratio(str(tr.get("supplier_norm","")),str(er.get("supplier_norm","")))/100
            line_bonus=0.0
            pl=str(tr.get("po_line_norm","") or "")
            epl=str(er.get("po_line_norm","") or "")
            if pl and epl and pl==epl: line_bonus=.08
            score=.58*amount_score+.16*qty_score+.13*desc_score+.08*supp_score+line_bonus+.05
            if best is None or score>best[0]: best=(score,ei,rel)
        if best and ((best[0]>=.72 and best[2]<=.025) or (best[2]<=.005 and best[0]>=.60)):
            dup.at[ti]=True
            matched[ti]=erp.loc[best[1],"record_id"]
    return dup, matched
