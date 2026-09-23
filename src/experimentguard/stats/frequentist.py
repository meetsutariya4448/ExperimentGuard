"""Frequentist tests and interval estimates for binomial arm comparisons.

Design notes that follow directly from statistical review:

* The omnibus test is a **2 x K contingency** test (`chi2_contingency`), not a
  goodness-of-fit test. It answers "do these arms differ in CTR?".
  `chisquare` answers a different question and is used only for the SRM
  *diagnostic* in `validity.py`.
* Practical significance is a **hypothesis**, not a point estimate: we test
  H0: RR <= 1 + theta with a one-sided alternative, rather than checking whether
  a point estimate clears theta.
* Intervals returned here are **descriptive**. They are not multiplicity
  adjusted and must never be presented as family-wise bounds. The decision gate
  is the adjusted test alone.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from scipy import stats
from statsmodels.stats.proportion import (
    confint_proportions_2indep,
    proportion_confint,
    test_proportions_2indep,
)

__all__ = [
    "ArmStat",
    "ComparisonResult",
    "arm_stat",
    "omnibus_ctr_test",
    "compare_arms",
]


@dataclass(frozen=True)
class ArmStat:
    """Descriptive statistics for a single arm."""

    clicks: int
    impressions: int
    ctr: float
    ctr_lo: float
    ctr_hi: float


@dataclass(frozen=True)
class ComparisonResult:
    """One ordered comparison: does `treatment` beat `reference` by more than theta?

    `p_value` tests H0: RR <= 1 + theta (one-sided, 'larger').
    All interval fields are descriptive and unadjusted.

    `diff_lo`/`diff_hi` are populated only when the risk ratio is NOT estimable,
    where they serve as the fallback effect estimate. On the ordinary path they are
    None: computing them costs ~25x the rest of the comparison and nothing reads them.
    """

    risk_ratio: float | None
    rr_lo: float | None
    rr_hi: float | None
    abs_diff: float
    diff_lo: float | None
    diff_hi: float | None
    p_value: float | None
    rr_estimable: bool
    fallback_p_value: float | None  # Fisher exact, used when RR is not estimable
    reason: str | None


def arm_stat(clicks: int, impressions: int, alpha: float = 0.05) -> ArmStat:
    """Per-arm CTR with a Wilson score interval (descriptive)."""
    if impressions <= 0:
        return ArmStat(int(clicks), int(impressions), float("nan"), float("nan"), float("nan"))
    lo, hi = proportion_confint(clicks, impressions, alpha=alpha, method="wilson")
    return ArmStat(int(clicks), int(impressions), clicks / impressions, float(lo), float(hi))


def omnibus_ctr_test(clicks: np.ndarray, impressions: np.ndarray) -> tuple[float, float, int]:
    """Gatekeeping omnibus across all arms on the 2 x K table of [clicks, non-clicks].

    Returns (chi2, p_value, dof). Returns (nan, 1.0, 0) when the table is degenerate
    -- for example when every arm has zero clicks, so there is nothing to compare.
    """
    clicks = np.asarray(clicks, dtype=float)
    impressions = np.asarray(impressions, dtype=float)
    non_clicks = impressions - clicks

    table = np.vstack([clicks, non_clicks])
    # A row that is entirely zero (no clicks anywhere, or no non-clicks anywhere)
    # makes the contingency test undefined.
    if table.shape[1] < 2 or np.any(table < 0) or np.any(table.sum(axis=1) == 0):
        return float("nan"), 1.0, 0

    chi2, p, dof, _ = stats.chi2_contingency(table, correction=False)
    return float(chi2), float(p), int(dof)


def compare_arms(
    t_clicks: int,
    t_impressions: int,
    r_clicks: int,
    r_impressions: int,
    *,
    ratio_null: float = 1.05,
    alpha: float = 0.05,
) -> ComparisonResult:
    """Test whether the treatment arm beats the reference arm by more than theta.

    `ratio_null` is 1 + theta. The null is H0: RR <= ratio_null; rejecting it is
    evidence of a practically meaningful improvement, which a bare "RR > 1" test
    would not establish.

    When either arm has zero clicks the risk ratio is not estimable (it is zero or
    undefined, and score intervals for the ratio break down). In that case
    `rr_estimable` is False, `p_value` is None, and a Fisher exact p-value is
    supplied as a descriptive fallback. A non-estimable comparison can never
    support a launch.
    """
    abs_diff = _safe_rate(t_clicks, t_impressions) - _safe_rate(r_clicks, r_impressions)

    if t_impressions <= 0 or r_impressions <= 0:
        return ComparisonResult(
            None,
            None,
            None,
            abs_diff,
            None,
            None,
            None,
            False,
            None,
            "non-positive impressions",
        )

    estimable = t_clicks > 0 and r_clicks > 0

    if not estimable:
        # The Newcombe score interval costs ~1.3 ms, about 25x the ratio test and
        # ratio interval combined. It is only *needed* on this branch -- as the
        # fallback when the risk ratio is undefined -- so it is computed lazily
        # rather than on every ordered pair and discarded.
        diff_lo, diff_hi = _try(
            lambda: confint_proportions_2indep(
                t_clicks,
                t_impressions,
                r_clicks,
                r_impressions,
                compare="diff",
                method="score",
                alpha=alpha,
            )
        )
        fisher_p = _try_scalar(
            lambda: stats.fisher_exact(
                [[t_clicks, t_impressions - t_clicks], [r_clicks, r_impressions - r_clicks]],
                alternative="greater",
            )[1]
        )
        return ComparisonResult(
            None,
            None,
            None,
            abs_diff,
            diff_lo,
            diff_hi,
            None,
            False,
            fisher_p,
            "zero clicks in at least one arm; risk ratio not estimable",
        )

    rr = (t_clicks / t_impressions) / (r_clicks / r_impressions)
    rr_lo, rr_hi = _try(
        lambda: confint_proportions_2indep(
            t_clicks,
            t_impressions,
            r_clicks,
            r_impressions,
            compare="ratio",
            alpha=alpha,
        )
    )
    p_value = _try_scalar(
        lambda: (
            test_proportions_2indep(
                t_clicks,
                t_impressions,
                r_clicks,
                r_impressions,
                value=ratio_null,
                compare="ratio",
                alternative="larger",
            ).pvalue
        )
    )

    return ComparisonResult(
        float(rr), rr_lo, rr_hi, abs_diff, None, None, p_value, True, None, None
    )


def _safe_rate(clicks: int, impressions: int) -> float:
    return clicks / impressions if impressions > 0 else float("nan")


def _try(fn) -> tuple[float | None, float | None]:
    """statsmodels raises or returns nan on degenerate counts; treat that as 'no interval'.

    Degenerate counts also make statsmodels emit divide-by-zero RuntimeWarnings from
    its internal ratio computation even when we only asked for a difference interval,
    so warnings are suppressed at this boundary rather than leaking to callers.
    """
    try:
        with warnings.catch_warnings(), np.errstate(divide="ignore", invalid="ignore"):
            warnings.simplefilter("ignore", RuntimeWarning)
            lo, hi = fn()
    except (ValueError, ZeroDivisionError, FloatingPointError):
        return None, None
    lo, hi = float(lo), float(hi)
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return None, None
    return lo, hi


def _try_scalar(fn) -> float | None:
    try:
        with warnings.catch_warnings(), np.errstate(divide="ignore", invalid="ignore"):
            warnings.simplefilter("ignore", RuntimeWarning)
            value = float(fn())
    except (ValueError, ZeroDivisionError, FloatingPointError):
        return None
    return value if np.isfinite(value) else None
