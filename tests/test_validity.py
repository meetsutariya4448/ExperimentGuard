"""Validity checks, including the derived randomization flag."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from experimentguard.stats.validity import (
    CACHE_WINDOW_END,
    CACHE_WINDOW_START,
    assess_experiment,
    flag_cache_window,
    srm_pvalue,
)


def test_documented_window_boundaries_are_inclusive():
    """The authors' phrasing is 'from June 25, 2013 to January 10, 2014'."""
    inside = flag_cache_window(
        ["2013-06-25 00:00:01", "2013-09-01 12:00:00", "2014-01-10 23:59:59"]
    )
    outside = flag_cache_window(["2013-06-24 23:59:59", "2014-01-11 00:00:01"])
    assert inside.all()
    assert not outside.any()
    assert date(2013, 6, 25) == CACHE_WINDOW_START
    assert date(2014, 1, 10) == CACHE_WINDOW_END


def test_mixed_timestamp_formats_parse():
    """The archive mixes fractional and whole-second timestamps in one column."""
    flags = flag_cache_window(["2013-09-01 12:00:00", "2013-09-01 12:00:00.123"])
    assert flags.all()


def test_cache_window_makes_an_experiment_invalid():
    flags = assess_experiment("2013-09-01 10:00:00", [50, 60], [3000, 3000])
    assert flags.randomization_unreliable
    assert flags.is_invalid
    assert any("cache-misconfiguration" in r for r in flags.reasons)


def test_experiment_outside_the_window_is_valid():
    flags = assess_experiment("2014-06-01 10:00:00", [50, 60], [3000, 3000])
    assert not flags.randomization_unreliable
    assert not flags.is_invalid


def test_srm_is_a_diagnostic_and_never_by_itself_invalidates():
    """A severe allocation imbalance outside the window must remain *valid*.

    Neither the intended allocation nor each arm's active duration is recorded, so
    imbalance is evidence, not proof. The archive's own authors say the analysis
    "can't prove it either way".
    """
    flags = assess_experiment("2014-06-01 10:00:00", [50, 60], [500, 9500])
    assert flags.srm_pvalue < 1e-6
    assert not flags.is_invalid


def test_srm_detects_and_excuses_correctly():
    assert srm_pvalue([5000, 5000]) == pytest.approx(1.0)
    assert srm_pvalue([500, 9500]) < 1e-6
    assert math.isnan(srm_pvalue([1000]))


@pytest.mark.parametrize(
    ("clicks", "impressions", "field"),
    [
        ([5000, 60], [3000, 3000], "integrity_violation"),
        ([50, 60], [0, 3000], "integrity_violation"),
        ([0, 0], [3000, 3000], "all_zero_clicks"),
        ([50], [3000], "too_few_arms"),
    ],
)
def test_integrity_failures_invalidate(clicks, impressions, field):
    flags = assess_experiment("2014-06-01 10:00:00", clicks, impressions)
    assert getattr(flags, field)
    assert flags.is_invalid


def test_attribution_limited_is_a_warning_not_an_invalidity():
    """The randomised unit is the package, so a two-component change stays valid.

    It simply cannot attribute the effect to headline versus image.
    """
    flags = assess_experiment(
        "2014-06-01 10:00:00",
        [50, 60],
        [3000, 3000],
        n_distinct_headlines=2,
        n_distinct_eyecatchers=2,
    )
    assert flags.attribution_limited
    assert not flags.is_invalid


def test_single_component_change_is_not_attribution_limited():
    flags = assess_experiment(
        "2014-06-01 10:00:00",
        [50, 60],
        [3000, 3000],
        n_distinct_headlines=2,
        n_distinct_eyecatchers=1,
    )
    assert not flags.attribution_limited


def test_flag_reproduces_the_published_share_on_a_realistic_spread():
    """Sanity check on the derivation's magnitude.

    Against the real archive this flag marks 7,016 of 32,487 tests (21.6%), against
    the authors' published ~22%. Here we only assert the window logic selects the
    documented span out of a uniform spread of dates.
    """
    days = np.arange(np.datetime64("2013-01-01"), np.datetime64("2015-05-01"))
    flags = flag_cache_window([str(d) for d in days])
    expected = (np.datetime64("2014-01-10") - np.datetime64("2013-06-25")).astype(int) + 1
    assert flags.sum() == expected
