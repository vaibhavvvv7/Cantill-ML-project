from __future__ import annotations
import argparse
import pandas as pd

REQUIRED=["record_id","include","exclusion_reason","supplier_key","item_key","spend","l1","l2","l3","l4","confidence"]
ALLOWED={"CANCELLED","NOT_APPROVED","NON_PROCUREMENT","DUPLICATE"}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("csv"); args=ap.parse_args()
    d=pd.read_csv(args.csv,keep_default_na=False)
    assert list(d.columns)==REQUIRED, f"columns differ: {list(d.columns)}"
    assert d.record_id.is_unique
    assert set(pd.to_numeric(d.include).unique()).issubset({0,1})
    exc=d[d.include.astype(int).eq(0)]
    inc=d[d.include.astype(int).eq(1)]
    assert set(exc.exclusion_reason).issubset(ALLOWED)
    assert (pd.to_numeric(exc.spend,errors="coerce").fillna(0)==0).all()
    assert inc.exclusion_reason.eq("").all()
    conf=pd.to_numeric(d.confidence,errors="coerce")
    assert conf.notna().all() and conf.between(0,1).all()
    print(f"OK: {len(d):,} rows; included={len(inc):,}; excluded={len(exc):,}; spend={pd.to_numeric(d.spend,errors='coerce').fillna(0).sum():,.2f}")

if __name__=="__main__": main()
