from __future__ import annotations
import argparse, json, tempfile
import pandas as pd
from sklearn.metrics import accuracy_score
from .config import load_config, data_path
from .pipeline import run_pipeline


def evaluate_zero_label(config_path,data_root=None):
    cfg=load_config(config_path,data_root)
    labels_cfg=cfg.get("labels",{})
    if not labels_cfg.get("file"): raise ValueError("Config has no labels")
    labels=pd.read_csv(data_path(cfg,labels_cfg["file"]))
    ids=(labels_cfg.get("id_prefix","")+labels[labels_cfg.get("id_column","record_id")].astype(str))
    with tempfile.TemporaryDirectory() as td:
        out,_=run_pipeline(config_path,f"{td}/out.csv",data_root,use_labels=False)
    z=out.set_index("record_id").reindex(ids)
    metrics={}
    cats=labels_cfg.get("category_columns",["category_l1","category_l2","category_l3"])
    for i,c in enumerate(cats,1):
        metrics[f"l{i}_accuracy"]=float(accuracy_score(labels[c].astype(str),z[f"l{i}"].fillna("").astype(str)))
    return metrics


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True); ap.add_argument("--data-root")
    args=ap.parse_args(); print(json.dumps(evaluate_zero_label(args.config,args.data_root),indent=2))
if __name__=="__main__": main()
