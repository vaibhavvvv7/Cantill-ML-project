from __future__ import annotations
from pathlib import Path
import os
import yaml


def load_config(path: str | Path, data_root: str | Path | None = None) -> dict:
    path = Path(path).resolve()
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_config_path"] = str(path)
    cfg["_config_dir"] = str(path.parent)
    root = data_root or os.getenv("CANTILL_DATA_ROOT") or cfg.get("data_root", "data")
    root = Path(root)
    if not root.is_absolute():
        root = (path.parent.parent / root).resolve()
    cfg["_data_root"] = str(root)
    return cfg


def data_path(cfg: dict, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg["_data_root"]) / p
