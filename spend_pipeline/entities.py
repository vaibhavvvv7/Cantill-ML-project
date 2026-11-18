from __future__ import annotations
from collections import defaultdict, Counter
import pandas as pd
from .text import clean_text, normalize_supplier, stable_key

class EntityResolver:
    def __init__(self):
        self.vendor_to_supplier = {}
        self.name_to_supplier = {}
        self.material_to_item = {}
        self.desc_to_item = {}
        self.supplier_desc_to_item = {}
        self.material_to_category = {}
        self.desc_to_category = {}
        self.item_to_category = {}

    @staticmethod
    def _majority_mapping(keys, vals, min_purity=0.8):
        bucket=defaultdict(list)
        for k,v in zip(keys, vals):
            if k and v:
                bucket[str(k)].append(str(v))
        out={}
        for k,arr in bucket.items():
            c=Counter(arr); value,n=c.most_common(1)[0]
            if n/len(arr) >= min_purity:
                out[k]=value
        return out

    def fit_a(self, erp: pd.DataFrame, labels: pd.DataFrame):
        z=erp.merge(labels, left_on="record_id", right_on="record_id", how="inner")
        self.vendor_to_supplier=self._majority_mapping(z["supplier_id"].fillna(""), z["supplier_key"].fillna(""), .8)
        self.name_to_supplier=self._majority_mapping(z["supplier_norm"].fillna(""), z["supplier_key"].fillna(""), .8)
        self.material_to_item=self._majority_mapping(z["material_id"].fillna(""), z["item_key"].fillna(""), .9)
        self.desc_to_item=self._majority_mapping(z["description_norm"].fillna(""), z["item_key"].fillna(""), .92)
        composite=(z["supplier_key"].fillna("").astype(str)+"|"+z["description_norm"].fillna("").astype(str))
        self.supplier_desc_to_item=self._majority_mapping(composite, z["item_key"].fillna(""), .88)
        cats=["\x1f".join([str(r[c]) for c in ["category_l1","category_l2","category_l3"] if c in z.columns and pd.notna(r[c])]) for _,r in z.iterrows()]
        self.material_to_category=self._majority_mapping(z["material_id"].fillna(""), cats, .9)
        self.desc_to_category=self._majority_mapping(z["description_norm"].fillna(""), cats, .92)
        self.item_to_category=self._majority_mapping(z["item_key"].fillna(""), cats, .9)
        return self

    def supplier_key(self, supplier_id, supplier_name):
        sid="" if pd.isna(supplier_id) else str(supplier_id).strip()
        name=normalize_supplier(supplier_name)
        if sid and sid in self.vendor_to_supplier:
            return self.vendor_to_supplier[sid]
        if name and name in self.name_to_supplier:
            return self.name_to_supplier[name]
        base=sid or name or "unknown_supplier"
        return stable_key("SUP", base)

    def item_key(self, material_id, description, supplier_key=""):
        mid="" if pd.isna(material_id) else str(material_id).strip()
        desc=clean_text(description)
        if mid and mid in self.material_to_item:
            return self.material_to_item[mid]
        comp=supplier_key+"|"+desc if supplier_key and desc else ""
        if comp and comp in self.supplier_desc_to_item:
            return self.supplier_desc_to_item[comp]
        if desc and desc in self.desc_to_item:
            return self.desc_to_item[desc]
        base=mid or (supplier_key+"|"+desc if desc else supplier_key+"|unknown_item")
        return stable_key("ITEM", base)

    def learned_category(self, material_id, description, item_key=""):
        mid="" if pd.isna(material_id) else str(material_id).strip()
        desc=clean_text(description)
        lab = self.item_to_category.get(str(item_key)) or self.material_to_category.get(mid) or self.desc_to_category.get(desc)
        return tuple(lab.split("\x1f")) if lab else None
