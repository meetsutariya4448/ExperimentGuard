"""The four competing selection policies.

The archive documents `first_place` as information shown to editors and `winner` as
what editors ultimately selected. Neither is established as an automatic
highest-CTR rule, so they are modelled as *separate* policies rather than assumed to
be the naive one. The naive rule is computed here from the observed CTRs instead.

Every policy may decline to select. Measured over the full 32,487-test archive:

    winner        NONE 24,834 (76.4%)   ONE  7,642 (23.5%)   MULTIPLE 11
    first_place   NONE    365 ( 1.1%)   ONE 32,122 (98.9%)   MULTIPLE  0

Forcing a winner where the source records none would invent data, so
`selection_status` is a first-class outcome and `selected_arm_id` is nullable.
Agreement rates must therefore always state their denominator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

__all__ = [
    "POLICY_NAMES",
    "SelectionStatus",
    "Selection",
    "naive_argmax_ctr",
    "recorded_first_place",
    "editor_winner",
    "from_decision",
    "agreement",
]


class SelectionStatus(StrEnum):
    ONE = "ONE"
    NONE = "NONE"
    MULTIPLE = "MULTIPLE"


@dataclass(frozen=True)
class Selection:
    policy: str
    test_id: str
    selection_status: SelectionStatus
    selected_arm_id: str | None
    selection_count: int


POLICY_NAMES = ("naive_argmax_ctr", "recorded_first_place", "editor_winner", "experimentguard")


def _from_mask(policy: str, test_id: str, arm_ids, mask) -> Selection:
    chosen = [a for a, m in zip(arm_ids, mask, strict=True) if m]
    if len(chosen) == 1:
        return Selection(policy, test_id, SelectionStatus.ONE, chosen[0], 1)
    if not chosen:
        return Selection(policy, test_id, SelectionStatus.NONE, None, 0)
    return Selection(policy, test_id, SelectionStatus.MULTIPLE, None, len(chosen))


def naive_argmax_ctr(test_id: str, arm_ids, clicks, impressions) -> Selection:
    """ "Highest conversion rate wins", computed here rather than read from the archive.

    Exact ties yield MULTIPLE: the rule genuinely does not pick in that case, and
    breaking the tie arbitrarily would flatter the naive policy.
    """
    clicks = np.asarray(clicks, dtype=float)
    impressions = np.asarray(impressions, dtype=float)
    if impressions.size == 0 or np.all(impressions <= 0):
        return Selection("naive_argmax_ctr", test_id, SelectionStatus.NONE, None, 0)
    ctr = np.divide(clicks, impressions, out=np.full(clicks.shape, np.nan), where=impressions > 0)
    if np.all(np.isnan(ctr)):
        return Selection("naive_argmax_ctr", test_id, SelectionStatus.NONE, None, 0)
    return _from_mask("naive_argmax_ctr", test_id, arm_ids, ctr == np.nanmax(ctr))


def recorded_first_place(test_id: str, arm_ids, first_place) -> Selection:
    return _from_mask("recorded_first_place", test_id, arm_ids, np.asarray(first_place, dtype=bool))


def editor_winner(test_id: str, arm_ids, winner) -> Selection:
    return _from_mask("editor_winner", test_id, arm_ids, np.asarray(winner, dtype=bool))


def from_decision(test_id: str, selected_arm_id: str | None) -> Selection:
    """ExperimentGuard selects exactly when it launches."""
    if selected_arm_id is None:
        return Selection("experimentguard", test_id, SelectionStatus.NONE, None, 0)
    return Selection("experimentguard", test_id, SelectionStatus.ONE, selected_arm_id, 1)


def agreement(left, right, *, eligible=None) -> dict:
    """Agreement between two policies over an explicitly stated denominator.

    Only tests where *both* policies selected exactly one arm can agree or disagree;
    everything else is reported as excluded rather than counted as a disagreement.
    """
    left_by = {s.test_id: s for s in left}
    right_by = {s.test_id: s for s in right}
    shared = set(left_by) & set(right_by)
    if eligible is not None:
        shared &= set(eligible)

    comparable = [
        t
        for t in shared
        if left_by[t].selection_status is SelectionStatus.ONE
        and right_by[t].selection_status is SelectionStatus.ONE
    ]
    agreed = sum(left_by[t].selected_arm_id == right_by[t].selected_arm_id for t in comparable)

    return {
        "tests_considered": len(shared),
        "denominator": len(comparable),
        "agreed": agreed,
        "agreement_rate": (agreed / len(comparable)) if comparable else float("nan"),
        "excluded_no_single_selection": len(shared) - len(comparable),
    }
