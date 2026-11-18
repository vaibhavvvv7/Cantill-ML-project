from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--company",choices=["A","B"],required=True)
    ap.add_argument("--data-root",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    root=Path(args.data_root)
    out=pd.read_csv(args.output)
    if args.company=="A":
        lab=pd.read_csv(root/"company_A/labels_A.csv")
        z=lab.merge(out,on="record_id",how="inner")
        print("rows",len(z))
        print("supplier_key exact agreement",(z.supplier_key_x==z.supplier_key_y).mean())
        print("item_key exact agreement",(z.item_key_x==z.item_key_y).mean())
        for n,c in [(1,"category_l1"),(2,"category_l2"),(3,"category_l3")]:
            print(f"L{n} accuracy",(z[c].astype(str)==z[f"l{n}"].astype(str)).mean())
    else:
        lab=pd.read_csv(root/"company_B/seed_labels.csv")
        z=lab.merge(out,left_on="line_id",right_on="record_id",how="inner",suffixes=("_gold","_pred"))
        print("rows",len(z))
        print("include confusion")
        print(pd.crosstab(z.include_gold,z.include_pred))
        inc=z[z.include_gold.eq(1)]
        for n,c in [(1,"category_l1"),(2,"category_l2"),(3,"category_l3")]:
            print(f"L{n} accuracy on included labels",(inc[c].astype(str)==inc[f"l{n}"].astype(str)).mean())

if __name__=="__main__":
    main()
