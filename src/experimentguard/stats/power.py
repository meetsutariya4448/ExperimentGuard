"""Power and sample-size planning.

Everything here is **prospective**. Observed (post-hoc) power -- power computed from
the effect a completed experiment happened to produce -- is deliberately absent, and
no decision field may depend on such a quantity.

Observed power is a monotone transform of the p-value, so gating a launch on it is
circular: it adds no information beyond the test that was already run
(Hoenig & Heisey, "The Abuse of Power", The American Statistician 55(1), 2001).

What is reported instead:
  * MDE       -- the smallest relative lift detectable at `power` for the observed n
  * power     -- prospective power to detect a *prespecified* lift
  * required n-- additional sample per arm needed to reach the power target
"""

from __future__ import annotations

import numpy as np
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

__all__ = ["prospective_power", "minimum_detectable_effect", "required_sample_per_arm"]

_POWER = NormalIndPower()


def prospective_power(
    baseline_rate: float, relative_lift: float, n_per_arm: float, alpha: float = 0.05
) -> float:
    """Power to detect a prespecified `relative_lift` at the given per-arm sample size."""
    if not _valid(baseline_rate, n_per_arm) or relative_lift <= 0:
        return float("nan")
    treated = min(baseline_rate * (1.0 + relative_lift), 1.0 - 1e-12)
    effect = proportion_effectsize(treated, baseline_rate)
    if effect <= 0:
        return float("nan")
    return float(_POWER.power(effect_size=effect, nobs1=n_per_arm, alpha=alpha, ratio=1.0))


def minimum_detectable_effect(
    baseline_rate: float, n_per_arm: float, power: float = 0.80, alpha: float = 0.05
) -> float:
    """Smallest *relative* lift detectable at `power`, given `n_per_arm`.

    Solves for the effect size that reaches the power target, then inverts
    Cohen's h back to a rate and expresses it relative to the baseline.
    """
    if not _valid(baseline_rate, n_per_arm):
        return float("nan")
    try:
        effect = _POWER.solve_power(
            effect_size=None, nobs1=n_per_arm, alpha=alpha, power=power, ratio=1.0
        )
    except (ValueError, RuntimeError):
        return float("nan")
    if effect is None or not np.isfinite(effect) or effect <= 0:
        return float("nan")

    # Invert h = 2*asin(sqrt(p2)) - 2*asin(sqrt(p1)) for p2.
    phi = 2.0 * np.arcsin(np.sqrt(baseline_rate)) + float(effect)
    if phi >= np.pi:
        return float("nan")
    detectable = float(np.sin(phi / 2.0) ** 2)
    return (detectable - baseline_rate) / baseline_rate


def required_sample_per_arm(
    baseline_rate: float, relative_lift: float, power: float = 0.80, alpha: float = 0.05
) -> float:
    """Per-arm sample size needed to detect `relative_lift` at `power`."""
    if not _valid(baseline_rate, 1) or relative_lift <= 0:
        return float("nan")
    treated = min(baseline_rate * (1.0 + relative_lift), 1.0 - 1e-12)
    effect = proportion_effectsize(treated, baseline_rate)
    if effect <= 0:
        return float("nan")
    try:
        n = _POWER.solve_power(effect_size=effect, nobs1=None, alpha=alpha, power=power, ratio=1.0)
    except (ValueError, RuntimeError):
        return float("nan")
    return float(np.ceil(n)) if n is not None and np.isfinite(n) else float("nan")


def _valid(rate: float, n: float) -> bool:
    return bool(np.isfinite(rate) and np.isfinite(n) and 0.0 < rate < 1.0 and n > 0)
