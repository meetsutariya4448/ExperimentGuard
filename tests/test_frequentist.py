"""Frequentist tests checked against independently derived reference values.

These deliberately avoid self-consistency: each expected number comes from a closed
form computed here from first principles, or from a published worked example, not
from the module under test.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from experimentguard.stats.frequentist import arm_stat, compare_arms, omnibus_ctr_test


def test_wilson_interval_matches_closed_form():
    n, x = 3000, 54
    p, z = x / n, stats.norm.ppf(0.975)
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom

    got = arm_stat(x, n)
    assert got.ctr == pytest.approx(p)
    assert got.ctr_lo == pytest.approx(centre - half, abs=1e-12)
    assert got.ctr_hi == pytest.approx(centre + half, abs=1e-12)


def test_omnibus_is_a_contingency_test_not_goodness_of_fit():
    """The 2 x K table must drive the result, so equal CTRs give no evidence...

    ...even when the arms have wildly different sizes. A goodness-of-fit test on
    impressions would scream at the imbalance; that is a different question.
    """
    clicks = np.array([100, 200, 400])
    impressions = np.array([1000, 2000, 4000])  # identical 10% CTR throughout
    _, p, dof = omnibus_ctr_test(clicks, impressions)
    assert p == pytest.approx(1.0)
    assert dof == 2


def test_omnibus_matches_hand_computed_chi_square():
    clicks = np.array([150, 122, 110])
    impressions = np.array([3052, 3033, 3092])
    table = np.vstack([clicks, impressions - clicks])

    # Pearson chi-square computed directly from the table.
    row, col = table.sum(axis=1, keepdims=True), table.sum(axis=0, keepdims=True)
    expected = row @ col / table.sum()
    manual = float((((table - expected) ** 2) / expected).sum())

    chi2, p, dof = omnibus_ctr_test(clicks, impressions)
    assert chi2 == pytest.approx(manual, rel=1e-12)
    assert dof == 2
    assert p == pytest.approx(float(stats.chi2.sf(manual, 2)), rel=1e-12)


def test_omnibus_degenerate_table_is_not_significant():
    chi2, p, dof = omnibus_ctr_test(np.array([0, 0]), np.array([100, 100]))
    assert math.isnan(chi2) and p == 1.0 and dof == 0


def test_risk_ratio_point_estimate():
    res = compare_arms(54, 3000, 42, 3000, ratio_null=1.05)
    assert res.risk_ratio == pytest.approx((54 / 3000) / (42 / 3000))
    assert res.rr_estimable


def test_threshold_test_is_directional():
    """H0: RR <= 1.05 with a 'larger' alternative must not reject when the arm is worse."""
    better = compare_arms(54, 3000, 42, 3000, ratio_null=1.05)
    worse = compare_arms(42, 3000, 54, 3000, ratio_null=1.05)
    assert worse.p_value > better.p_value
    assert worse.p_value > 0.5


def test_threshold_test_is_stricter_than_a_bare_difference_test():
    """Testing RR > 1.05 must be harder than testing RR > 1 on the same data.

    This is the property that makes practical significance a hypothesis rather than
    a point-estimate comparison.
    """
    at_one = compare_arms(600, 30000, 500, 30000, ratio_null=1.0)
    at_theta = compare_arms(600, 30000, 500, 30000, ratio_null=1.05)
    assert at_theta.p_value > at_one.p_value


@pytest.mark.parametrize(
    ("t_clicks", "r_clicks"),
    [(54, 0), (0, 54), (0, 0)],
)
def test_zero_click_arms_are_not_estimable(t_clicks, r_clicks):
    res = compare_arms(t_clicks, 3000, r_clicks, 3000, ratio_null=1.05)
    assert res.rr_estimable is False
    assert res.risk_ratio is None
    assert res.p_value is None
    assert "not estimable" in res.reason


def test_zero_click_comparison_still_offers_a_fallback():
    res = compare_arms(54, 3000, 0, 3000, ratio_null=1.05)
    assert res.fallback_p_value is not None
    assert res.fallback_p_value < 0.01  # 54 vs 0 clicks is not a coin flip
    assert res.diff_lo is not None and res.diff_hi is not None


def test_non_positive_impressions_rejected():
    res = compare_arms(0, 0, 10, 100)
    assert res.rr_estimable is False
    assert "non-positive impressions" in res.reason
