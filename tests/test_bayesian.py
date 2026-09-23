"""Bayesian comparison, validated against Monte Carlo and against the two traps.

Trap 1: `integral of pdf_T(x) * cdf_R(x) dx` computes P(T > R), not P(RR > c).
Trap 2: plain adaptive quadrature over [0, 1/c] silently returns 0 where the answer
is 1, because it misses concentrated posteriors.

Both are reproduced here so a regression would fail loudly rather than quietly.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import integrate, stats

from experimentguard.stats.bayesian import (
    expected_loss,
    posterior_params,
    prob_ratio_exceeds,
    ratio_credible_interval,
)

# (name, a_t, b_t, a_r, b_r) -- the parameter regimes that break naive implementations.
CASES = [
    ("typical n=3k", 1 + 54, 1 + 2946, 1 + 42, 1 + 2958),
    ("large n=200k", 1 + 3600, 1 + 196400, 1 + 3000, 1 + 197000),
    ("huge n=2M", 1 + 36000, 1 + 1964000, 1 + 30000, 1 + 1970000),
    ("near-null", 1 + 3000, 1 + 197000, 1 + 3000, 1 + 197000),
    ("zero clicks treatment", 1 + 0, 1 + 3000, 1 + 42, 1 + 2958),
    ("zero clicks reference", 1 + 54, 1 + 2946, 1 + 0, 1 + 3000),
    ("extreme difference", 1 + 500, 1 + 2500, 1 + 10, 1 + 2990),
]


def _mc(a_t, b_t, a_r, b_r, c, n=400_000, seed=0):
    rng = np.random.default_rng(seed)
    return float(np.mean(rng.beta(a_t, b_t, n) / rng.beta(a_r, b_r, n) > c))


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
@pytest.mark.parametrize("c", [1.0, 1.05, 1.20])
def test_matches_monte_carlo(case, c):
    _, a_t, b_t, a_r, b_r = case
    got = float(prob_ratio_exceeds(a_t, b_t, a_r, b_r, c=c)[0])
    assert got == pytest.approx(_mc(a_t, b_t, a_r, b_r, c), abs=3e-3)


def test_trap_one_old_formula_ignores_the_threshold():
    """P(T > R) does not vary with c; the correct quantity must."""
    a_t, b_t, a_r, b_r = 1 + 54, 1 + 2946, 1 + 42, 1 + 2958

    def old():
        f = lambda x: stats.beta.pdf(x, a_t, b_t) * stats.beta.cdf(x, a_r, b_r)  # noqa: E731
        return integrate.quad(f, 0, 1)[0]

    old_value = old()
    at_one = float(prob_ratio_exceeds(a_t, b_t, a_r, b_r, c=1.0)[0])
    at_theta = float(prob_ratio_exceeds(a_t, b_t, a_r, b_r, c=1.05)[0])

    assert at_one == pytest.approx(old_value, abs=1e-6)  # the old formula IS the c=1 case
    assert at_theta < at_one - 0.01  # and the real quantity responds to the threshold


def test_trap_two_plain_quadrature_fails_where_this_module_does_not():
    a_t, b_t, a_r, b_r = 1 + 3600, 1 + 196400, 1 + 3000, 1 + 197000
    f = lambda r: stats.beta.pdf(r, a_r, b_r) * stats.beta.sf(1.05 * r, a_t, b_t)  # noqa: E731
    naive = integrate.quad(f, 0, 1 / 1.05, limit=200)[0]

    assert naive < 0.01  # the trap: ~0 where the truth is ~1
    assert float(prob_ratio_exceeds(a_t, b_t, a_r, b_r, c=1.05)[0]) == pytest.approx(1.0, abs=1e-6)


def test_probability_is_monotone_decreasing_in_threshold():
    a_t, b_t, a_r, b_r = 1 + 54, 1 + 2946, 1 + 42, 1 + 2958
    values = [float(prob_ratio_exceeds(a_t, b_t, a_r, b_r, c=c)[0]) for c in (1.0, 1.05, 1.2, 1.5)]
    # pairwise over consecutive values, so the offset zip is intentionally ragged
    assert all(x >= y for x, y in zip(values, values[1:], strict=False))


def test_vectorises_over_comparisons():
    got = prob_ratio_exceeds(
        np.array([55.0, 3601.0]),
        np.array([2947.0, 196401.0]),
        np.array([43.0, 3001.0]),
        np.array([2959.0, 197001.0]),
        c=1.05,
    )
    assert got.shape == (2,)
    assert got[0] == pytest.approx(float(prob_ratio_exceeds(55, 2947, 43, 2959, c=1.05)[0]))


def test_expected_loss_matches_monte_carlo():
    a_t, b_t, a_r, b_r = 1 + 54, 1 + 2946, 1 + 42, 1 + 2958
    rng = np.random.default_rng(1)
    n = 400_000
    mc = float(np.mean(np.maximum(0.0, rng.beta(a_r, b_r, n) - rng.beta(a_t, b_t, n))))
    assert float(expected_loss(a_t, b_t, a_r, b_r)[0]) == pytest.approx(mc, rel=0.05)


def test_credible_interval_matches_monte_carlo_quantiles():
    a_t, b_t, a_r, b_r = 1 + 54, 1 + 2946, 1 + 42, 1 + 2958
    lo, hi = ratio_credible_interval(a_t, b_t, a_r, b_r)
    rng = np.random.default_rng(2)
    n = 1_000_000
    sample = rng.beta(a_t, b_t, n) / rng.beta(a_r, b_r, n)
    assert lo == pytest.approx(float(np.quantile(sample, 0.025)), rel=0.01)
    assert hi == pytest.approx(float(np.quantile(sample, 0.975)), rel=0.01)


def test_posterior_params_apply_the_prior():
    a, b = posterior_params(54, 3000, prior_alpha=1.0, prior_beta=1.0)
    assert float(a) == 55.0
    assert float(b) == 2947.0
