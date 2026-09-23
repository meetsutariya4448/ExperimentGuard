"""Multiplicity correction.

Two distinct families, deliberately kept apart:

* **Decision family** -- all ordered arm comparisons *within one experiment*.
  Holm, which controls FWER without assuming independence. This is the family that
  matches the question "should we ship this experiment's winner?".

* **Research family** -- all experiments in a partition. Benjamini-Hochberg FDR.
  Useful for describing the archive as a whole; it is *not* the basis for any
  individual launch decision.

Applying an archive-wide correction to a single experiment's decision would answer
the wrong question, so the two never mix.
"""

from __future__ import annotations

import numpy as np
from statsmodels.stats.multitest import multipletests

__all__ = ["holm_adjust", "bh_adjust", "adjust"]


def _adjust(pvalues, method: str, alpha: float):
    """Return (reject, adjusted_p), tolerating None/NaN entries.

    A None p-value means the comparison was not estimable (for example a zero-click
    arm). Such entries never reject and are excluded from the correction's rank
    accounting rather than being silently treated as p = 1.
    """
    raw = [np.nan if p is None else float(p) for p in pvalues]
    arr = np.asarray(raw, dtype=float)
    usable = np.isfinite(arr)

    reject = np.zeros(arr.shape, dtype=bool)
    adjusted = np.full(arr.shape, np.nan, dtype=float)

    if usable.sum() > 0:
        rej, adj, _, _ = multipletests(arr[usable], alpha=alpha, method=method)
        reject[usable] = rej
        adjusted[usable] = adj
    return reject, adjusted


def holm_adjust(pvalues, alpha: float = 0.05):
    """Holm-Bonferroni within one experiment's comparison family."""
    return _adjust(pvalues, "holm", alpha)


def bh_adjust(pvalues, alpha: float = 0.05):
    """Benjamini-Hochberg FDR across a research-scale family."""
    return _adjust(pvalues, "fdr_bh", alpha)


def adjust(pvalues, method: str = "holm", alpha: float = 0.05):
    methods = {"holm": "holm", "bonferroni": "bonferroni", "fdr_bh": "fdr_bh", "bh": "fdr_bh"}
    if method not in methods:
        raise ValueError(f"unsupported multiplicity method: {method!r}")
    return _adjust(pvalues, methods[method], alpha)
