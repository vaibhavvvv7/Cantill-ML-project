from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import normalize
from .text import clean_text, extract_keywords


def _path_label(path: tuple[str, ...]) -> str:
    return "\x1f".join(path)


def _label_path(label: str) -> tuple[str, ...]:
    return tuple(label.split("\x1f"))


@dataclass
class Predictions:
    paths: list[tuple[str, ...]]
    confidence: np.ndarray


class TaxonomyClassifier:
    """Hybrid classifier: exact learned mappings -> supervised sparse model -> zero-label taxonomy matching."""
    def __init__(self, taxonomy_paths: list[tuple[str, ...]], random_state: int = 42):
        self.paths = taxonomy_paths
        self.random_state = random_state
        self.vectorizer = TfidfVectorizer(
            lowercase=True, ngram_range=(1, 2), min_df=1, sublinear_tf=True,
            max_features=45000, strip_accents="unicode"
        )
        self.model = None
        self.tax_matrix = None
        self.tax_vectorizer = FeatureUnion([
            ("word", TfidfVectorizer(
                lowercase=True, ngram_range=(1, 2), analyzer="word",
                sublinear_tf=True, stop_words="english"
            )),
            ("char", TfidfVectorizer(
                lowercase=True, analyzer="char_wb", ngram_range=(3, 5),
                sublinear_tf=True
            )),
        ])
        self.path_keyword_sets = [set(extract_keywords(" ".join(p))) for p in self.paths]
        self._fit_zero_shot()

    def _taxonomy_docs(self) -> list[str]:
        docs = []
        for p, kw in zip(self.paths, self.path_keyword_sets):
            leaf = p[-1]
            stemmed_kw = " ".join(kw)
            # Combine canonical path terms, emphasized leaf, and stemmed root keywords
            docs.append(f"{' '.join(p)} | {leaf} {leaf} | {stemmed_kw}")
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
            loss="log_loss", alpha=1e-5, max_iter=150, tol=1e-3,
            class_weight="balanced", random_state=self.random_state, n_jobs=-1
        )
        self.model.fit(X, y)
        return self

    def predict_zero_shot(self, texts: list[str]) -> Predictions:
        cleaned_texts = [clean_text(t) for t in texts]
        X = normalize(self.tax_vectorizer.transform(cleaned_texts))
        sim = (X @ self.tax_matrix.T).toarray()

        n_samples, n_classes = sim.shape
        if n_classes == 1:
            best = np.zeros(n_samples, dtype=int)
            top = sim[:, 0]
            margin = np.ones(n_samples)
        else:
            # Add keyword overlap score for top candidates to boost exact conceptual alignment
            order = np.argsort(sim, axis=1)
            top_candidates = order[:, -min(10, n_classes):]

            scores = sim.copy()
            for row_idx in range(n_samples):
                row_kw = set(extract_keywords(texts[row_idx]))
                if not row_kw:
                    continue
                for col_idx in top_candidates[row_idx]:
                    pk = self.path_keyword_sets[col_idx]
                    if pk:
                        overlap = len(pk & row_kw)
                        overlap_ratio = overlap / max(len(pk), 1)
                        if overlap >= 2:
                            scores[row_idx, col_idx] += 0.25 * overlap_ratio + 0.15
                        elif overlap == 1:
                            scores[row_idx, col_idx] += 0.15 * overlap_ratio

            new_order = np.argsort(scores, axis=1)
            best = new_order[:, -1]
            second = new_order[:, -2]
            top = scores[np.arange(n_samples), best]
            margin = top - scores[np.arange(n_samples), second]

        conf = np.clip(0.20 + 1.25 * top + 1.8 * margin, 0.05, 0.95)
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

        out_paths = []
        out_conf = []
        for sp, sc, zp, zc in zip(sup_paths, sup_conf, zero.paths, zero.confidence):
            if sc >= 0.40:
                out_paths.append(sp)
                out_conf.append(min(0.99, 0.25 + 0.75 * float(sc)))
            else:
                out_paths.append(zp)
                out_conf.append(float(zc) * 0.85)
        return Predictions(out_paths, np.asarray(out_conf))
