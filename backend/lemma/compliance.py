"""Compliance model: does a crop show the product its planogram area expects?

Features compare each crop with its *expected* product:
  text_sim      CLIP similarity to the expected category's prompts
  margin_other  text_sim minus the best *other* category
  margin_empty  text_sim minus the best "empty / covered" prompt
  best_vs_empty best match over *all* categories minus the best "empty / covered" prompt
                (< 0: the crop looks like no product at all, i.e. empty or covered)
  proto_sim     similarity to the expected category's visual prototype
Without labels, UnsupervisedModel flags the crops that score lowest on these.
A logistic regression on these gives P(compliant). Then area consistency
(similarity to the area's usual look over the day) may nudge P by at most
±max_shift: stores reorganise and mix products, so it is deliberately the
weakest signal and can only tip borderline cases.
"""
from dataclasses import dataclass, field

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from lemma.categories import EMPTY_PROMPTS, all_categories, base_noun, prompts_for

MAIN_FEATURES = ["text_sim", "margin_other", "margin_empty", "best_vs_empty", "proto_sim"]
MIN_PROTO = 3  # labelled compliant crops needed before a category uses a labelled prototype
# Scoring: +1 correct, -2 wrong -> say "non-compliant" only if P(non-compliant) > 2/3.
DEFAULT_THRESHOLD = 1 / 3  # on P(compliant)
NUDGE_WEIGHTS = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)


@dataclass
class TextBank:
    categories: list[str]
    cat_emb: np.ndarray    # (K, D)
    empty_emb: np.ndarray  # (E, D)

    @classmethod
    def build(cls, clip) -> "TextBank":
        cats = all_categories()
        return cls(cats, clip.prompt_set([prompts_for(c) for c in cats]), clip.texts(EMPTY_PROMPTS))


@dataclass
class Context:
    """Reference embeddings learned from (mostly unlabelled) crops + labels."""
    protos: dict[str, np.ndarray] = field(default_factory=dict)  # category -> unit vector
    proto_n: dict[str, int] = field(default_factory=dict)         # labelled crops behind it (0 = fallback)
    area_median: dict[str, np.ndarray] = field(default_factory=dict)
    area_typical: dict[str, float] = field(default_factory=dict)


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-8)


def fit_context(E: np.ndarray, cats: list[str], area_ids: list[str], compliant: np.ndarray) -> Context:
    """compliant: 1 / 0 for labelled crops, NaN for unlabelled.

    Prototype per category = mean of labelled compliant crops if there are >= MIN_PROTO,
    else the median of every crop whose area expects that category (most are compliant).
    """
    ctx = Context()
    cats_a, areas_a = np.array(cats), np.array(area_ids)
    for c in set(cats):
        rows = cats_a == c
        pos = rows & (compliant == 1)
        if pos.sum() >= MIN_PROTO:
            ctx.protos[c], ctx.proto_n[c] = _unit(E[pos].mean(axis=0)), int(pos.sum())
        else:
            ctx.protos[c], ctx.proto_n[c] = _unit(np.median(E[rows], axis=0)), 0
    for a in set(area_ids):
        rows = areas_a == a
        med = _unit(np.median(E[rows], axis=0))
        ctx.area_median[a] = med
        ctx.area_typical[a] = float(np.median(E[rows] @ med))
    return ctx


def text_scores(E: np.ndarray, cats: list[str], bank: TextBank) -> np.ndarray:
    """(N, 4): text_sim, margin_other, margin_empty, best_vs_empty."""
    S = E @ bank.cat_emb.T
    idx = np.array([bank.categories.index(c) for c in cats])
    t = S[np.arange(len(E)), idx]
    nouns = np.array([base_noun(c) for c in bank.categories])
    same = nouns[None, :] == nouns[idx][:, None]  # loose vs packaged of the same thing isn't "other"
    other = np.where(same, -np.inf, S).max(axis=1)
    empty = (E @ bank.empty_emb.T).max(axis=1)
    return np.stack([t, t - other, t - empty, S.max(axis=1) - empty], axis=1)


def features(E, cats, area_ids, bank: TextBank, ctx: Context, self_labels: np.ndarray | None = None):
    """Main feature matrix (N, 5) and area-consistency delta (N,).

    self_labels: labels of these same crops when they helped build ctx; their own
    contribution is removed from the prototype (no peeking at the answer).
    """
    proto = np.stack([ctx.protos[c] for c in cats])
    proto_sim = (E * proto).sum(axis=1)
    if self_labels is not None:
        for i, c in enumerate(cats):
            n = ctx.proto_n[c]
            if n > 1 and self_labels[i] == 1:
                loo = _unit(ctx.protos[c] * n - E[i])  # approx. leave-one-out mean direction
                proto_sim[i] = float(E[i] @ loo)
    X = np.column_stack([text_scores(E, cats, bank), proto_sim])
    delta = np.array([
        float(E[i] @ ctx.area_median[a]) - ctx.area_typical[a] if a in ctx.area_median else 0.0
        for i, a in enumerate(area_ids)
    ])
    return X, delta


@dataclass
class UnsupervisedModel:
    """No-label fallback: flag the crops that look least like their expected product.

    score = z(margin_other) + z(proto_sim), standardised over many (mostly compliant) crops;
    the lowest `flag_rate` share is flagged. A crop that looks more like an empty/covered
    shelf than like *any* product (best_vs_empty < 0) is not "the wrong product", so it
    is kept compliant; its emptiness is the stock model's job.
    """
    mu: np.ndarray
    sd: np.ndarray
    cutoff: float
    flag_rate: float
    threshold: float = 0.5
    ctx: Context | None = None

    @staticmethod
    def _score(X, mu, sd):
        z = (X - mu) / sd
        return z[:, 1] + z[:, 4]

    @classmethod
    def fit(cls, X, ctx: Context, flag_rate: float = 0.05) -> "UnsupervisedModel":
        mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-8
        s = cls._score(X, mu, sd)
        not_empty = X[:, 3] >= 0
        cutoff = float(np.quantile(s[not_empty], flag_rate))
        return cls(mu, sd, cutoff, flag_rate, ctx=ctx)

    def proba(self, X, delta=None, nudge: bool = True) -> np.ndarray:
        p = 1.0 / (1.0 + np.exp(-(self._score(X, self.mu, self.sd) - self.cutoff)))
        return np.where(X[:, 3] < 0, 1.0, p)


def apply_nudge(p: np.ndarray, delta: np.ndarray, w: float, max_shift: float) -> np.ndarray:
    return np.clip(p + np.clip(w * delta, -max_shift, max_shift), 0.0, 1.0)


def points(pred_compliant: np.ndarray, y: np.ndarray) -> int:
    """Identification part of the challenge score: +1 correct, -2 wrong."""
    correct = pred_compliant == y.astype(bool)
    return int(correct.sum() - 2 * (~correct).sum())


@dataclass
class ComplianceModel:
    clf: object
    ctx: Context
    nudge_w: float
    max_shift: float
    threshold: float = DEFAULT_THRESHOLD

    @classmethod
    def fit(cls, X, delta, y, ctx, max_shift: float, threshold: float = DEFAULT_THRESHOLD):
        if len(set(y.tolist())) < 2:
            raise ValueError("labels need both compliant and non-compliant examples to train")
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)).fit(X, y)
        p = clf.predict_proba(X)[:, 1]
        # Pick the nudge weight that scores best on the training labels (ties -> smaller weight).
        best_w = max(NUDGE_WEIGHTS, key=lambda w: (points(apply_nudge(p, delta, w, max_shift) >= threshold, y), -w))
        return cls(clf, ctx, best_w if max_shift > 0 else 0.0, max_shift, threshold)

    def proba(self, X, delta, nudge: bool = True) -> np.ndarray:
        p = self.clf.predict_proba(X)[:, 1]
        return apply_nudge(p, delta, self.nudge_w, self.max_shift) if nudge else p
