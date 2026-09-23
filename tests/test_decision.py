"""Decision engine behaviour, one test per rule the statistical review insisted on."""

from __future__ import annotations

import pytest

from experimentguard.config import load_frozen_policy
from experimentguard.decision import REJECT, Decision, evaluate_experiment

VALID_DATE = "2014-06-01 10:00:00"
WINDOW_DATE = "2013-09-01 10:00:00"


@pytest.fixture(scope="module")
def policy():
    return load_frozen_policy()


def run(policy, clicks, impressions, started_at=VALID_DATE, **kw):
    arms = [f"arm{i}" for i in range(len(clicks))]
    return evaluate_experiment("t1", arms, clicks, impressions, started_at, policy, **kw)


def test_cache_window_experiment_is_invalid_and_still_emitted(policy):
    d = run(policy, [500, 100], [10_000, 10_000], started_at=WINDOW_DATE)
    assert d.decision is Decision.INVALID
    assert d.is_inferentially_eligible is False
    assert d.test_id == "t1"  # present as a row, not dropped
    assert any("cache-misconfiguration" in r for r in d.reasons)


def test_beating_the_reference_arm_alone_does_not_launch(policy):
    """The core correction: an arm must beat *every* arm, not the nominated reference.

    arm0 is the reference. arm1 crushes it, but arm2 is just as good as arm1, so no
    arm has established itself as best and nothing may launch.
    """
    d = run(policy, [100, 600, 600], [20_000, 20_000, 20_000])
    assert d.decision is not Decision.LAUNCH
    assert d.selected_arm_id is None

    beats_reference = [
        c for c in d.comparisons if c.treatment_arm_id == "arm1" and c.reference_arm_id == "arm0"
    ]
    assert beats_reference[0].rejected  # it really does beat the reference


def test_an_arm_beating_every_other_arm_launches(policy):
    d = run(policy, [300, 900, 310], [30_000, 30_000, 30_000])
    assert d.decision is Decision.LAUNCH
    assert d.selected_arm_id == "arm1"
    assert d.is_inferentially_eligible
    assert d.bayes_prob_exceeds is not None


def test_underpowered_experiment_continues(policy):
    """An observed gap that the data cannot resolve must not launch.

    Note the engine will happily launch a *large* effect on a small sample when it
    genuinely clears the threshold test -- 15 vs 5 clicks per 300 impressions is
    significant at p = 0.02 and is not noise. The underpowered case is the one where
    the observed gap is ordinary, so the interval still spans the threshold.
    """
    d = run(policy, [10, 14], [300, 300])
    assert d.decision is Decision.CONTINUE
    assert d.selected_arm_id is None
    assert any("more sample is required" in r for r in d.reasons)


def test_a_large_effect_on_a_small_sample_may_still_launch(policy):
    """Guards against over-correcting: the engine gates on evidence, not on n."""
    d = run(policy, [5, 15], [300, 300])
    assert d.decision is Decision.LAUNCH
    assert d.selected_arm_id == "arm1"


def test_large_sample_with_negligible_effect_is_no_meaningful_win(policy):
    """Enough data to rule out a worthwhile lift in either direction."""
    d = run(policy, [10_000, 10_010], [1_000_000, 1_000_000])
    assert d.decision is Decision.NO_MEANINGFUL_WIN
    assert any("ruled out" in r for r in d.reasons)


def test_reject_is_an_alias_for_no_meaningful_win():
    """The brief names this state REJECT; the engine names it for what it shows."""
    assert REJECT is Decision.NO_MEANINGFUL_WIN


def test_zero_click_arm_cannot_launch(policy):
    """RR is not estimable against a zero-click arm, so that arm cannot be beaten
    on the ratio scale and no launch may rest on it."""
    d = run(policy, [0, 900], [30_000, 30_000])
    assert d.decision is not Decision.LAUNCH
    assert any(not c.rr_estimable for c in d.comparisons)
    assert any("RR_NOT_ESTIMABLE" in r for r in d.reasons)


def test_all_zero_click_experiment_is_invalid(policy):
    d = run(policy, [0, 0], [3000, 3000])
    assert d.decision is Decision.INVALID
    assert any("zero clicks" in r for r in d.reasons)


def test_single_arm_experiment_is_invalid(policy):
    d = run(policy, [50], [3000])
    assert d.decision is Decision.INVALID
    assert any("fewer than two arms" in r for r in d.reasons)


def test_attribution_limited_attaches_to_a_real_decision(policy):
    d = run(
        policy,
        [300, 900, 310],
        [30_000, 30_000, 30_000],
        n_distinct_headlines=2,
        n_distinct_eyecatchers=2,
    )
    assert d.decision is Decision.LAUNCH  # a warning, never an invalidity
    assert d.attribution_limited
    assert any("ATTRIBUTION_LIMITED" in r for r in d.reasons)


def test_omnibus_gate_can_block_a_pairwise_winner(policy):
    """The gate is consulted, not decorative.

    The alpha is pinned just below this experiment's own omnibus p-value, so the
    only thing that changes between the two runs is whether the gate passes.
    """
    clicks, impressions = [300, 900, 310], [30_000, 30_000, 30_000]
    passing = run(policy, clicks, impressions)
    assert passing.decision is Decision.LAUNCH

    strict = policy.scenario(omnibus_alpha=passing.omnibus_pvalue / 2)
    blocked = run(strict, clicks, impressions)
    assert blocked.decision is not Decision.LAUNCH
    assert blocked.selected_arm_id is None
    assert any("omnibus gate" in r for r in blocked.reasons)


def test_omnibus_gate_can_be_disabled(policy):
    clicks, impressions = [300, 900, 310], [30_000, 30_000, 30_000]
    ungated = policy.scenario(require_omnibus_gate=False, omnibus_alpha=1e-300)
    assert run(ungated, clicks, impressions).decision is Decision.LAUNCH


def test_threshold_changes_the_decision(policy):
    """theta is a real lever: a lift that clears 5% need not clear 100%."""
    clicks, impressions = [300, 900, 310], [30_000, 30_000, 30_000]
    assert run(policy, clicks, impressions).decision is Decision.LAUNCH
    # The winning arm has 3x the reference CTR, so it clears an RR > 2 bar too.
    # Demanding RR > 6 is what it cannot clear.
    demanding = policy.scenario(practical_threshold=5.00)
    assert run(demanding, clicks, impressions).decision is not Decision.LAUNCH


def test_scenario_policies_are_never_frozen(policy):
    assert policy.is_frozen
    assert not policy.scenario(practical_threshold=0.2).is_frozen


def test_every_decision_carries_reasons(policy):
    for clicks, impressions, started in [
        ([500, 100], [10_000, 10_000], WINDOW_DATE),
        ([300, 900, 310], [30_000, 30_000, 30_000], VALID_DATE),
        ([5, 15], [300, 300], VALID_DATE),
        ([10_000, 10_010], [1_000_000, 1_000_000], VALID_DATE),
    ]:
        d = run(policy, clicks, impressions, started_at=started)
        assert d.reasons, f"{d.decision} produced no reasons"


def test_comparison_count_is_all_ordered_pairs(policy):
    d = run(policy, [300, 900, 310, 305], [30_000] * 4)
    assert len(d.comparisons) == 4 * 3  # K(K-1) ordered comparisons
