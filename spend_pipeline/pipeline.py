from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .config import load_config, data_path
from .ingest import ingest_source, apply_fx
from .taxonomy import Taxonomy
from .classifier import TaxonomyClassifier
from .entities import EntityResolver
from .spend_rules import SpendRuleEngine
from .matching import mark_tool_duplicates, match_a_tool_to_erp
from .text import clean_text

OUTPUT_COLUMNS=["record_id","include","exclusion_reason","supplier_key","item_key","spend","l1","l2","l3","l4","confidence"]

def _read_labels(cfg):
    lc=cfg.get("labels")
    if not lc or not lc.get("file"): return None
    p=data_path(cfg,lc["file"])
    if not p.exists(): return None
    return pd.read_csv(p)

def _feature_text(df: pd.DataFrame, cfg: dict) -> list[str]:
    cols=cfg.get("classification",{}).get("feature_columns",[])
    fallback=["description","material_id","supplier_name","supplier_id"]
    cols=cols or fallback
    vals=[]
    for _,r in df.iterrows():
        parts=[]
        for c in cols:
            if c in r.index and pd.notna(r[c]):
                v = str(r[c]).strip()
                if v and v.lower() != "nan":
                    parts.append(v)
        vals.append(" | ".join(parts))
    return vals

def _label_paths(labels: pd.DataFrame, taxonomy: Taxonomy, cfg: dict):
    lc=cfg.get("labels",{})
    cats=lc.get("category_columns") or taxonomy.level_columns
    out=[]
    for _,r in labels.iterrows():
        p=tuple(str(r[c]).strip() for c in cats if c in labels.columns and pd.notna(r[c]) and str(r[c]).strip())
        out.append(p)
    return out

def _normalize_label_ids(labels: pd.DataFrame, cfg: dict):
    lc=cfg.get("labels",{})
    idc=lc.get("id_column","record_id")
    prefix=lc.get("id_prefix","")
    return prefix+labels[idc].astype(str)

def run_pipeline(config_path: str, output_path: str, data_root: str|None=None, use_labels: bool=True, diagnostics_path: str|None=None):
    cfg=load_config(config_path,data_root)
    taxonomy=Taxonomy.from_config(cfg)
    labels=_read_labels(cfg) if use_labels else None
    frames=[]
    source_cfgs={}
    for sc in cfg["sources"]:
        d=ingest_source(cfg,sc)
        d=apply_fx(cfg,d,sc)
        frames.append(d); source_cfgs[sc["name"]]=sc
    df=pd.concat(frames,ignore_index=True,sort=False)
    resolver=EntityResolver()
    # Learn A-style entity/category dictionaries from golden labels when schema supports them.
    if labels is not None and {"supplier_key","item_key"}.issubset(labels.columns):
        labels=labels.copy(); labels["record_id"]=_normalize_label_ids(labels,cfg)
        train=df[df["record_id"].isin(labels["record_id"])].copy()
        resolver.fit_a(train,labels)
    # Spend rules can learn conservative exact exclusions from seed labels.
    rules=SpendRuleEngine(cfg)
    if labels is not None and "include" in labels.columns:
        rules.fit_seed(df,labels)
    include,reason=rules.apply(df)
    # Cross-system A matching is enabled purely by config.
    match_cfg=cfg.get("matching",{})
    matched_erp={}
    if match_cfg.get("enabled") and len(cfg["sources"])>=2:
        erp_name=match_cfg["primary_source"]; tool_name=match_cfg["secondary_source"]
        eidx=df.index[df.source_name.eq(erp_name)]; tidx=df.index[df.source_name.eq(tool_name)]
        erp=df.loc[eidx].copy(); tool=df.loc[tidx].copy()
        # tool-tool duplicates first, but primary ERP match takes same exclusion code anyway.
        tdup=mark_tool_duplicates(tool)
        tdup_idx=tdup.index[tdup & include.loc[tdup.index].eq(1)]
        include.loc[tdup_idx]=0; reason.loc[tdup_idx]="DUPLICATE"
        xdup,local_match=match_a_tool_to_erp(erp,tool)
        xdup_idx=xdup.index[xdup & include.loc[xdup.index].eq(1)]
        include.loc[xdup_idx]=0; reason.loc[xdup_idx]="DUPLICATE"
        matched_erp.update(local_match)
    # supplier and item keys
    df["supplier_key"]=[resolver.supplier_key(r.supplier_id,r.supplier_name) for _,r in df.iterrows()]
    df["item_key"]=[resolver.item_key(r.material_id,r.description,sk) for (_,r),sk in zip(df.iterrows(),df["supplier_key"])]
    # For tool rows matched to ERP, inherit entity keys from ERP for grouping consistency.
    rec_to_idx={rec:idx for idx,rec in zip(df.index,df.record_id)}
    matched_pairs=[(ti,rec_to_idx[erp_rec]) for ti,erp_rec in matched_erp.items() if erp_rec in rec_to_idx]
    if matched_pairs:
        tool_rows=[p[0] for p in matched_pairs]
        erp_rows=[p[1] for p in matched_pairs]
        df.loc[tool_rows,"supplier_key"]=df.loc[erp_rows,"supplier_key"].to_numpy()
        df.loc[tool_rows,"item_key"]=df.loc[erp_rows,"item_key"].to_numpy()
    # classification model
    clf=TaxonomyClassifier(taxonomy.paths)
    valid_paths=taxonomy.valid_path_set()
    if labels is not None:
        label_ids=_normalize_label_ids(labels,cfg)
        all_label_paths=_label_paths(labels,taxonomy,cfg)
        path_by_id={rid:path for rid,path in zip(label_ids,all_label_paths) if path in valid_paths}
        mask=df["record_id"].isin(path_by_id)
        if mask.any():
            train_df=df.loc[mask]
            train_paths=[path_by_id[rid] for rid in train_df["record_id"]]
            clf.fit(_feature_text(train_df,cfg),train_paths)
    pred=clf.predict(_feature_text(df,cfg))
    paths=pred.paths; conf=pred.confidence.copy()
    # Strong learned exact material/description category mapping overrides text model.
    for pos,(i,r) in enumerate(df.iterrows()):
        p=resolver.learned_category(r.material_id,r.description,r.item_key)
        if p and p in valid_paths:
            paths[pos]=p; conf[pos]=max(conf[pos],.96)
    # Matched tool rows inherit primary ERP category.
    idx_to_pos={idx:pos for pos,idx in enumerate(df.index)}
    for ti,erp_rec in matched_erp.items():
        ei=rec_to_idx.get(erp_rec)
        if ei is not None:
            paths[idx_to_pos[ti]]=paths[idx_to_pos[ei]]
            conf[idx_to_pos[ti]]=max(conf[idx_to_pos[ti]],conf[idx_to_pos[ei]])
    out=pd.DataFrame(index=df.index)
    out["record_id"]=df["record_id"]
    out["include"]=include.astype(int)
    out["exclusion_reason"]=reason.where(include.eq(0),"")
    out["supplier_key"]=df["supplier_key"]
    out["item_key"]=df["item_key"]
    out["spend"]=df["amount_reporting"].where(include.eq(1),0.0).fillna(0.0)
    for n in range(1,5):
        out[f"l{n}"]=[p[n-1] if include.iloc[pos]==1 and len(p)>=n else "" for pos,p in enumerate(paths)]
    out["confidence"]=[float(conf[pos]) if include.iloc[pos]==1 else float(min(max(conf[pos],.05),.99)) for pos in range(len(out))]
    out=validate_output(out,taxonomy,len(df))
    Path(output_path).parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(output_path,index=False)
    diag={
        "company":cfg.get("company"), "input_rows":int(len(df)), "output_rows":int(len(out)),
        "included":int(out.include.sum()), "excluded":int((out.include==0).sum()),
        "exclusion_counts":out.loc[out.include.eq(0),"exclusion_reason"].value_counts().to_dict(),
        "total_spend":float(out.spend.sum()), "date_parse_failures":int(df.date_parse_failed.sum()),
        "amount_parse_failures":int(df.amount_parse_failed.sum()), "fx_missing":int(df.get("fx_missing",pd.Series(False,index=df.index)).sum()),
        "supplier_keys":int(out.supplier_key.nunique()), "item_keys":int(out.item_key.nunique()),
        "mean_confidence":float(out.confidence.mean()),
    }
    if diagnostics_path:
        Path(diagnostics_path).write_text(json.dumps(diag,indent=2),encoding="utf-8")
    return out,diag

def validate_output(out: pd.DataFrame,taxonomy: Taxonomy,input_rows: int):
    assert len(out)==input_rows
    assert out.record_id.is_unique, "record_id must be unique"
    assert set(out.include.unique()).issubset({0,1})
    allowed={"","CANCELLED","NOT_APPROVED","NON_PROCUREMENT","DUPLICATE"}
    assert set(out.exclusion_reason.fillna("").unique()).issubset(allowed)
    assert (out.loc[out.include.eq(0),"spend"]==0).all()
    assert out.loc[out.include.eq(1),"exclusion_reason"].fillna("").eq("").all()
    assert out.confidence.between(0,1).all()
    valid=taxonomy.valid_path_set()
    inc=out.loc[out.include.eq(1),["l1","l2","l3","l4"]].fillna("").astype(str)
    bad=[]
    for vals in inc.itertuples(index=False,name=None):
        p=tuple(v for v in vals if v.strip() and v != "nan")
        if p and p not in valid:
            bad.append(p)
            if len(bad)>=3: break
    if bad:
        raise AssertionError(f"Invalid taxonomy path(s): {bad}")
    return out[OUTPUT_COLUMNS]
