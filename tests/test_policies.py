"""Selection policies, with particular attention to declining to select."""

from __future__ import annotations

import pytest

from experimentguard.policies import (
    SelectionStatus,
    agreement,
    editor_winner,
    from_decision,
    naive_argmax_ctr,
    recorded_first_place,
)

ARMS = ["a", "b", "c"]


def test_naive_picks_the_highest_rate_not_the_highest_count():
    """Arm 'a' has more clicks but a worse rate; the rule is about rates."""
    s = naive_argmax_ctr("t", ARMS, [100, 60, 10], [10_000, 1_000, 1_000])
    assert s.selection_status is SelectionStatus.ONE
    assert s.selected_arm_id == "b"


def test_naive_declines_on_an_exact_tie():
    """Breaking a tie arbitrarily would flatter the naive rule."""
    s = naive_argmax_ctr("t", ["a", "b"], [30, 30], [1000, 1000])
    assert s.selection_status is SelectionStatus.MULTIPLE
    assert s.selected_arm_id is None
    assert s.selection_count == 2


def test_naive_handles_zero_impressions():
    s = naive_argmax_ctr("t", ["a", "b"], [0, 0], [0, 0])
    assert s.selection_status is SelectionStatus.NONE


@pytest.mark.parametrize(
    ("flags", "status", "count"),
    [
        ([False, True, False], SelectionStatus.ONE, 1),
        ([False, False, False], SelectionStatus.NONE, 0),
        ([True, True, False], SelectionStatus.MULTIPLE, 2),
    ],
)
def test_recorded_policies_expose_all_three_states(flags, status, count):
    """All three states occur in the real archive, so none may be collapsed.

    Across all 32,487 experiments, `winner` is NONE for 24,834, ONE for 7,642 and
    MULTIPLE for 11.
    """
    for policy_fn in (recorded_first_place, editor_winner):
        s = policy_fn("t", ARMS, flags)
        assert s.selection_status is status
        assert s.selection_count == count
        assert (s.selected_arm_id is not None) == (status is SelectionStatus.ONE)


def test_experimentguard_selects_only_when_it_launches():
    assert from_decision("t", "b").selection_status is SelectionStatus.ONE
    assert from_decision("t", None).selection_status is SelectionStatus.NONE


def test_agreement_denominator_excludes_non_selections():
    """Only experiments where both policies chose one arm can agree or disagree."""
    left = [
        naive_argmax_ctr("t1", ["a", "b"], [10, 30], [1000, 1000]),  # picks b
        naive_argmax_ctr("t2", ["a", "b"], [30, 10], [1000, 1000]),  # picks a
        naive_argmax_ctr("t3", ["a", "b"], [20, 20], [1000, 1000]),  # tie -> MULTIPLE
    ]
    right = [
        from_decision("t1", "b"),  # agrees
        from_decision("t2", None),  # no selection -> excluded
        from_decision("t3", "a"),  # left is MULTIPLE -> excluded
    ]
    result = agreement(left, right)

    assert result["tests_considered"] == 3
    assert result["denominator"] == 1  # only t1 is comparable
    assert result["agreed"] == 1
    assert result["agreement_rate"] == 1.0
    assert result["excluded_no_single_selection"] == 2


def test_agreement_is_nan_rather_than_zero_when_nothing_is_comparable():
    """An empty denominator must not silently read as 0% agreement."""
    result = agreement([from_decision("t1", None)], [from_decision("t1", None)])
    assert result["denominator"] == 0
    assert result["agreement_rate"] != result["agreement_rate"]  # NaN


def test_agreement_respects_an_eligibility_filter():
    left = [naive_argmax_ctr("t1", ["a", "b"], [10, 30], [1000, 1000])]
    right = [from_decision("t1", "b")]
    assert agreement(left, right, eligible={"t1"})["denominator"] == 1
    assert agreement(left, right, eligible=set())["denominator"] == 0
