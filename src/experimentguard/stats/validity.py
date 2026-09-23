"""Validity checks that decide whether an experiment can support causal inference.

The hierarchy here is deliberate and follows the archive authors' own guidance.

**Primary invalidity: the documented cache window.** The Upworthy authors' June 2024
critical update reports a suspected Cloudflare cache misconfiguration between
2013-06-25 and 2014-01-10 that made assignment behave like block randomisation over
time rather than individual randomisation. They found issues with ~22% of tests and
explicitly discourage causal research on that portion. Experiments starting in the
window are INVALID.

The update states a flag column was added to the dataset. It was not: every public
OSF file is still the 2020/2021 vintage and carries no such column, and the GitHub
repository holds no dataset files at all. The flag is therefore *derived* from the
documented window. Deriving it reproduces the authors' own figure -- 21.4% of
exploratory tests against their published 22% -- which is the validation that this
derivation is the right one. If an updated file ever ships the column,
`flag_cache_window` is the single call site to replace.

**Secondary diagnostic: sample ratio mismatch.** Unequal impressions across arms is
*evidence*, not proof. The authors used SRM to discover the problem and say plainly
that the analysis "can't prove it either way", because neither the intended
allocation nor each arm's active duration is recorded. SRM is therefore reported and
charted but never by itself makes an experiment invalid.

**Attribution scope is not validity.** When both headline and image vary, the
randomised unit is still the package, so the experiment remains valid for choosing a
package. It simply cannot attribute the effect to headline versus image. That is a
warning attached to a decision, never an invalidity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

__all__ = [
    "CACHE_WINDOW_START",
    "CACHE_WINDOW_END",
    "ValidityFlags",
    "flag_cache_window",
    "srm_pvalue",
    "assess_experiment",
]

CACHE_WINDOW_START = date(2013, 6, 25)
CACHE_WINDOW_END = date(2014, 1, 10)


@dataclass(frozen=True)
class ValidityFlags:
    randomization_unreliable: bool
    integrity_violation: bool
    too_few_arms: bool
    all_zero_clicks: bool
    attribution_limited: bool
    srm_pvalue: float
    reasons: tuple[str, ...]

    @property
    def is_invalid(self) -> bool:
        """SRM is deliberately absent: it is a diagnostic, not grounds for invalidity."""
        return (
            self.randomization_unreliable
            or self.integrity_violation
            or self.too_few_arms
            or self.all_zero_clicks
        )


def flag_cache_window(
    started_at,
    window_start: date = CACHE_WINDOW_START,
    window_end: date = CACHE_WINDOW_END,
) -> np.ndarray:
    """True where an experiment started inside the documented unreliable window.

    Boundaries are inclusive, matching the authors' phrasing "from June 25, 2013 to
    January 10, 2014".
    """
    ts = pd.to_datetime(pd.Series(started_at), format="ISO8601", errors="coerce")
    day = ts.dt.date
    return ((day >= window_start) & (day <= window_end)).to_numpy()


def srm_pvalue(impressions) -> float:
    """Chi-square goodness of fit of arm impressions against equal allocation.

    This is the one place a goodness-of-fit test is correct: the question is whether
    the *allocation* matches an expected split, not whether CTRs differ.

    Diagnostic only. Equal allocation is an assumption, not a recorded fact, so a
    small p-value here does not establish broken randomisation.
    """
    obs = np.asarray(impressions, dtype=float)
    if obs.size < 2 or obs.sum() <= 0 or np.any(obs < 0):
        return float("nan")
    expected = np.full(obs.shape, obs.sum() / obs.size)
    return float(stats.chisquare(obs, expected).pvalue)


def assess_experiment(
    started_at,
    clicks,
    impressions,
    *,
    n_distinct_headlines: int = 1,
    n_distinct_eyecatchers: int = 1,
    window_start: date = CACHE_WINDOW_START,
    window_end: date = CACHE_WINDOW_END,
) -> ValidityFlags:
    """Assess one experiment. `started_at` is the experiment's earliest arm timestamp."""
    clicks = np.asarray(clicks, dtype=float)
    impressions = np.asarray(impressions, dtype=float)
    reasons: list[str] = []

    unreliable = bool(flag_cache_window([started_at], window_start, window_end)[0])
    if unreliable:
        reasons.append(
            f"started within the documented cache-misconfiguration window "
            f"({window_start} to {window_end}); authors discourage causal inference"
        )

    too_few = impressions.size < 2
    if too_few:
        reasons.append("fewer than two arms")

    integrity = bool(np.any(clicks > impressions) or np.any(impressions <= 0) or np.any(clicks < 0))
    if integrity:
        reasons.append(
            "integrity violation: clicks exceed impressions, or non-positive impressions"
        )

    all_zero = bool(impressions.size > 0 and np.all(clicks == 0))
    if all_zero:
        reasons.append("every arm recorded zero clicks; no effect is estimable")

    attribution = n_distinct_headlines > 1 and n_distinct_eyecatchers > 1

    return ValidityFlags(
        randomization_unreliable=unreliable,
        integrity_violation=integrity,
        too_few_arms=too_few,
        all_zero_clicks=all_zero,
        attribution_limited=attribution,
        srm_pvalue=srm_pvalue(impressions),
        reasons=tuple(reasons),
    )
