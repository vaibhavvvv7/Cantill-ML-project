from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from .config import data_path

@dataclass
class Taxonomy:
    frame: pd.DataFrame
    level_columns: list[str]
    paths: list[tuple[str, ...]]

    @classmethod
    def from_config(cls, cfg: dict) -> "Taxonomy":
        tc = cfg["taxonomy"]
        df = pd.read_csv(data_path(cfg, tc["file"]))
        configured = tc.get("columns")
        if configured:
            levels = [c for c in configured if c in df.columns]
        else:
            levels = [c for c in df.columns if str(c).lower().startswith(("category_l", "l"))]
        if not levels:
            raise ValueError("No taxonomy level columns found")
        paths = []
        for _, row in df[levels].iterrows():
            vals = tuple(str(row[c]).strip() for c in levels if pd.notna(row[c]) and str(row[c]).strip())
            if vals and vals not in paths:
                paths.append(vals)
        return cls(df, levels, paths)

    def valid_path_set(self) -> set[tuple[str, ...]]:
        return set(self.paths)
