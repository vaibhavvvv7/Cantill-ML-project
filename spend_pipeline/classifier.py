from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import normalize
from .text import clean_text


def _path_label(path: tuple[str, ...]) -> str:
    return "\x1f".join(path)


def _label_path(label: str) -> tuple[str, ...]:
    return tuple(label.split("\x1f"))

@dataclass
class Predictions:
    paths: list[tuple[str, ...]]
    confidence: np.ndarray

class TaxonomyClassifier:
    """Hybrid classifier: exact learned mappings -> supervised text -> taxonomy-only lexical similarity."""
    def __init__(self, taxonomy_paths: list[tuple[str, ...]], random_state: int = 42):
        self.paths = taxonomy_paths
        self.random_state = random_state
        self.vectorizer = TfidfVectorizer(
            lowercase=True, ngram_range=(1,2), min_df=1, sublinear_tf=True,
            max_features=40000, strip_accents="unicode"
        )
        self.model = None
        self.tax_matrix = None
        self.tax_vectorizer = FeatureUnion([
            ("word", TfidfVectorizer(lowercase=True, ngram_range=(1,2), analyzer="word", sublinear_tf=True)),
            ("char", TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3,5), sublinear_tf=True)),
        ])
        self._fit_zero_shot()

    def _taxonomy_docs(self):
        docs=[]
        for p in self.paths:
            # Repeat leaf and parent terms to give specific category words more weight.
            leaf = p[-1]
            docs.append(" | ".join(p) + " | " + leaf + " | " + leaf)
        return docs

    def _fit_zero_shot(self):
        docs = self._taxonomy_docs()
        self.tax_matrix = normalize(self.tax_vectorizer.fit_transform(docs))

    def fit(self, texts: list[str], paths: list[tuple[str, ...]]):
        y = np.array([_path_label(p) for p in paths])
        if len(np.unique(y)) < 2:
            return self
        X = self.vectorizer.fit_transform([clean_text(t) for t in texts])
        self.model = SGDClassifier(
            loss="log_loss", alpha=1e-5, max_iter=120, tol=1e-3,
            class_weight="balanced", random_state=self.random_state, n_jobs=-1
        )
        self.model.fit(X, y)
        return self

    def predict_zero_shot(self, texts: list[str]) -> Predictions:
        X = normalize(self.tax_vectorizer.transform([clean_text(t) for t in texts]))
        sim = (X @ self.tax_matrix.T).toarray()
        if sim.shape[1] == 1:
            best = np.zeros(len(texts), dtype=int)
            margin = np.ones(len(texts))
            top = sim[:,0]
        else:
            order = np.argsort(sim, axis=1)
            best = order[:,-1]
            second = order[:,-2]
            top = sim[np.arange(len(texts)), best]
            margin = top - sim[np.arange(len(texts)), second]
        # lexical scores are usually low; combine absolute score and separation.
        conf = np.clip(0.18 + 1.35*top + 1.6*margin, 0.05, 0.88)
        return Predictions([self.paths[i] for i in best], conf)

    def predict(self, texts: list[str]) -> Predictions:
        zero = self.predict_zero_shot(texts)
        if self.model is None:
            return zero
        X = self.vectorizer.transform([clean_text(t) for t in texts])
        proba = self.model.predict_proba(X)
        best = proba.argmax(axis=1)
        sup_conf = proba[np.arange(len(texts)), best]
        sup_paths = [_label_path(self.model.classes_[i]) for i in best]
        # Supervised model wins when decisive; otherwise taxonomy-only result is safer for sparse classes.
        out_paths=[]; out_conf=[]
        for sp, sc, zp, zc in zip(sup_paths, sup_conf, zero.paths, zero.confidence):
            if sc >= 0.42:
                out_paths.append(sp)
                out_conf.append(min(0.99, 0.25 + 0.75*float(sc)))
            else:
                out_paths.append(zp)
                out_conf.append(float(zc)*0.85)
        return Predictions(out_paths, np.asarray(out_conf))
