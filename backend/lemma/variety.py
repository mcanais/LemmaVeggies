"""Variety model: within a product family (apples, bananas...), which variety is in the basket?

Input: CLIP embeddings of the centre tiles of a crop (lemma.crop.inner_tiles), so the
model sees the fruit more than the crate. One logistic regression per family; a crop's
variety probabilities are the mean over its tiles.

Training labels are free: a crop the team labelled compliant (or, unlabelled, that the
compliance model doesn't flag) shows the planogram's product.
"""
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression

from lemma.categories import family_of

TILES = 4  # lemma.crop.inner_tiles default: 2 x 2
C = 1.0


def tile_key(crop_path: str, t: int) -> str:
    return f"{crop_path}#{t}"


def families_with_varieties(product_names) -> dict[str, list[str]]:
    """{family: [loose product names]} for families with at least 2 varieties."""
    fams: dict[str, set[str]] = {}
    for n in product_names:
        f = family_of(n)
        if f:
            fams.setdefault(f, set()).add(n)
    return {f: sorted(ns) for f, ns in fams.items() if len(ns) >= 2}


def fit_family(tiles: np.ndarray, varieties: list[str]):
    """tiles: (N, TILES, D); varieties: N product names. None if fewer than 2 varieties."""
    if len(set(varieties)) < 2:
        return None
    X = tiles.reshape(-1, tiles.shape[-1])
    y = np.repeat(np.array(varieties), tiles.shape[1])
    return LogisticRegression(C=C, max_iter=2000).fit(X, y)


def crop_proba(clf, tiles: np.ndarray) -> np.ndarray:
    """(N, TILES, D) -> (N, n_classes): mean tile probabilities."""
    n, t, d = tiles.shape
    return clf.predict_proba(tiles.reshape(-1, d)).reshape(n, t, -1).mean(axis=1)


def mismatch_scores(clf, tiles: np.ndarray, expected: list[str]):
    """Per crop: (mismatch score, best variety, its probability).

    mismatch = 1 - P(expected) when the model knows the expected variety; when it doesn't
    (no clean examples of it), the probability of the best *other* variety.
    """
    p = crop_proba(clf, tiles)
    classes = list(clf.classes_)
    best = p.argmax(axis=1)
    out = []
    for i, e in enumerate(expected):
        if e in classes:
            m = 1.0 - p[i, classes.index(e)]
        else:
            m = p[i, best[i]]
        out.append((float(m), classes[best[i]], float(p[i, best[i]])))
    return out


@dataclass
class VarietyModel:
    models: dict  # family -> LogisticRegression
    threshold: float  # flag a variety mismatch when mismatch score > threshold (inf = never)

    def check(self, product_name: str, tiles: np.ndarray):
        """tiles: (TILES, D) for one crop -> (mismatch score, best variety, prob) or None."""
        clf = self.models.get(family_of(product_name))
        if clf is None:
            return None
        return mismatch_scores(clf, tiles[None], [product_name])[0]
