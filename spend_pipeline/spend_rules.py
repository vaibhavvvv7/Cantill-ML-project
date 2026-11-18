from __future__ import annotations
from collections import defaultdict, Counter
import re
import numpy as np
import pandas as pd

GENERIC_NONPROC = re.compile(
    r"\b(?:intercompany|inter company|i/c payable|ic payable|sales tax|vat payable|withholding tax|royalt(?:y|ies)|"
    r"partner billing|interest expense|bank fee|finance charge|loan|dividend|income tax|corporate tax|"
    r"state \& local taxes|gst input tax|input tax|sales taxes?|\bic[0-9]+\b)\b",
    re.I,
)

class SpendRuleEngine:
    def __init__(self, cfg: dict):
        self.cfg=cfg
        self.exact_nonproc={}

    def fit_seed(self, source_df: pd.DataFrame, labels: pd.DataFrame):
        if labels is None or labels.empty or "include" not in labels.columns:
            return self
        z=source_df.merge(labels[[c for c in labels.columns if c in {"record_id","line_id","include","exclusion_reason"}]],
                          left_on="source_id", right_on=("line_id" if "line_id" in labels.columns else "record_id"), how="inner")
        for col in self.cfg.get("spend_rules",{}).get("learn_exact_columns",[]):
            if col not in z.columns: continue
            bucket=defaultdict(list)
            for v,inc in zip(z[col].fillna("<NA>").astype(str), z["include"]): bucket[v].append(int(inc))
            vals=set()
            for v,arr in bucket.items():
                if len(arr)>=3 and sum(arr)==0: vals.add(v)
            self.exact_nonproc[col]=vals
        return self

    def apply(self, df: pd.DataFrame) -> tuple[pd.Series,pd.Series]:
        include=pd.Series(1,index=df.index,dtype=int)
        reason=pd.Series("",index=df.index,dtype=object)
        status_col=self.cfg.get("spend_rules",{}).get("status_column")
        if status_col and status_col in df.columns:
            status=df[status_col].fillna("").astype(str).str.strip().str.lower()
            cancelled=set(x.lower() for x in self.cfg.get("spend_rules",{}).get("cancelled_statuses",["cancelled","canceled"]))
            approved=set(x.lower() for x in self.cfg.get("spend_rules",{}).get("approved_statuses",["approved","paid"]))
            m=status.isin(cancelled); include.loc[m]=0; reason.loc[m]="CANCELLED"
            m=(include.eq(1) & ~status.isin(approved)); include.loc[m]=0; reason.loc[m]="NOT_APPROVED"
        # generic + configured text rules
        cols=self.cfg.get("spend_rules",{}).get("non_procurement_text_columns",[])
        text=pd.Series("",index=df.index)
        for c in cols:
            if c in df.columns: text=text+" "+df[c].fillna("").astype(str)
        patterns=self.cfg.get("spend_rules",{}).get("non_procurement_regex",[])
        regexes=[GENERIC_NONPROC]+[re.compile(p,re.I) for p in patterns]
        m=pd.Series(False,index=df.index)
        for rgx in regexes: m |= text.str.contains(rgx,na=False,regex=True)
        for col,vals in self.exact_nonproc.items():
            if col in df.columns: m |= df[col].fillna("<NA>").astype(str).isin(vals)
        m &= include.eq(1)
        include.loc[m]=0; reason.loc[m]="NON_PROCUREMENT"
        return include,reason
