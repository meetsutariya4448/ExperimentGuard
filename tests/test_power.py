"""Power and sample-size planning. Prospective only -- observed power is absent by design."""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest
from scipy import stats

from experimentguard.stats import power as power_mod
from experimentguard.stats.power import (
    minimum_detectable_effect,
    prospective_power,
    required_sample_per_arm,
)


def test_mde_delivers_its_promised_power_under_simulation():
    """Validate the MDE against simulation, not against another approximation.

    A crude closed form -- delta = (z_a + z_b) * sqrt(2p(1-p)/n), using only the
    baseline rate -- disagrees with this module by ~14% at archive-scale parameters.
    Simulation settles which is right: at the module's MDE the empirical rejection
    rate is ~0.80, while at the crude approximation's it is only ~0.70. The crude
    form understates the effect because it ignores that the treated arm's variance
    differs from the baseline's once the lift is large.
    """
    p, n, trials = 0.015, 3000, 40_000
    mde = minimum_detectable_effect(p, n, power=0.80, alpha=0.05)

    rng = np.random.default_rng(0)
    treated_rate = p * (1 + mde)
    c1 = rng.binomial(n, p, trials)
    c2 = rng.binomial(n, treated_rate, trials)
    pooled = (c1 + c2) / (2 * n)
    se = np.sqrt(pooled * (1 - pooled) * 2 / n)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(se > 0, (c2 / n - c1 / n) / se, 0.0)
    empirical_power = float(np.mean(np.abs(z) > stats.norm.ppf(0.975)))

    assert empirical_power == pytest.approx(0.80, abs=0.02)


def test_mde_shrinks_as_sample_grows():
    p = 0.015
    values = [minimum_detectable_effect(p, n) for n in (1_000, 10_000, 100_000, 1_000_000)]
    assert all(x > y for x, y in zip(values, values[1:], strict=False))


def test_archive_scale_experiments_cannot_detect_small_lifts():
    """The finding that motivates the whole platform, pinned as a test.

    A typical Upworthy arm is ~3,000 impressions at ~1.5% CTR. Such an experiment
    cannot detect a 10% relative lift; its MDE is tens of percent.
    """
    mde = minimum_detectable_effect(0.015, 3000.0)
    assert mde > 0.25
    assert prospective_power(0.015, 0.10, 3000.0) < 0.20


def test_prospective_power_rises_with_effect_and_sample():
    assert prospective_power(0.015, 0.50, 3000.0) > prospective_power(0.015, 0.10, 3000.0)
    assert prospective_power(0.015, 0.10, 100_000.0) > prospective_power(0.015, 0.10, 3000.0)


def test_required_sample_inverts_prospective_power():
    n = required_sample_per_arm(0.015, 0.10, power=0.80)
    assert prospective_power(0.015, 0.10, n) == pytest.approx(0.80, abs=0.01)


@pytest.mark.parametrize(
    ("rate", "n"),
    [(0.0, 3000), (1.0, 3000), (0.015, 0), (float("nan"), 3000)],
)
def test_degenerate_inputs_return_nan(rate, n):
    assert math.isnan(minimum_detectable_effect(rate, n))


def test_module_exposes_no_observed_power_function():
    """Observed (post-hoc) power must not be computable from this module.

    It is a monotone transform of the p-value, so gating on it is circular
    (Hoenig & Heisey 2001). Keeping it absent is the enforcement.
    """
    names = [n for n, _ in inspect.getmembers(power_mod, inspect.isfunction)]
    banned = [n for n in names if "observed" in n.lower() or "post_hoc" in n.lower()]
    assert banned == []
