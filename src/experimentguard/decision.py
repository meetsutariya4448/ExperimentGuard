"""The LAUNCH / NO_MEANINGFUL_WIN / CONTINUE / INVALID decision engine.

The central rule, and the reason this is not a one-liner: **a launch requires an arm
that beats every other arm by more than theta**, not an arm that beats one nominated
reference. The Upworthy archive has no control group -- its authors say so -- so the
earliest-created arm is an arbitrary reference. Beating it establishes nothing about
whether the chosen package is the best one available.

So the procedure is:

1. Validity gate. Invalid experiments short-circuit and are still emitted as rows.
2. Gatekeeping omnibus across all arms (2 x K contingency).
3. Every *ordered* pair of arms is tested against H0: RR <= 1 + theta.
4. Holm adjustment over that within-experiment family.
5. An arm wins only if all of its outward comparisons reject.

`CONTINUE` and `NO_MEANINGFUL_WIN` are then distinguished by whether any arm is still
a plausible winner: if some arm's descriptive upper bounds leave room for a
worthwhile win, more data could settle it; if no arm has that room, the experiment
has answered the question in the negative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from experimentguard.config import Policy
from experimentguard.stats.bayesian import posterior_params, prob_ratio_exceeds
from experimentguard.stats.frequentist import compare_arms, omnibus_ctr_test
from experimentguard.stats.multiplicity import adjust
from experimentguard.stats.power import (
    minimum_detectable_effect,
    prospective_power,
    required_sample_per_arm,
)
from experimentguard.stats.validity import assess_experiment


class Decision(StrEnum):
    LAUNCH = "LAUNCH"
    NO_MEANINGFUL_WIN = "NO_MEANINGFUL_WIN"
    CONTINUE = "CONTINUE"
    INVALID = "INVALID"


# The project brief names this state REJECT. NO_MEANINGFUL_WIN is the same state
# under a name that says what the evidence actually shows.
REJECT = Decision.NO_MEANINGFUL_WIN


@dataclass
class Comparison:
    treatment_arm_id: str
    reference_arm_id: str
    risk_ratio: float | None
    rr_lo: float | None
    rr_hi: float | None
    p_value: float | None
    p_adjusted: float | None
    rejected: bool
    rr_estimable: bool
    note: str | None = None


@dataclass
class ExperimentDecision:
    test_id: str
    decision: Decision
    reasons: list[str]
    selected_arm_id: str | None
    is_inferentially_eligible: bool
    randomization_unreliable: bool
    attribution_limited: bool
    n_arms: int
    total_impressions: int
    pooled_ctr: float
    reference_arm_id: str | None
    best_ctr_arm_id: str | None
    srm_pvalue: float
    omnibus_pvalue: float | None
    mde_relative: float
    prospective_power: dict[float, float]
    required_n_per_arm: dict[float, float]
    bayes_prob_exceeds: float | None
    comparisons: list[Comparison] = field(default_factory=list)

    @property
    def is_launch(self) -> bool:
        return self.decision is Decision.LAUNCH


def evaluate_experiment(
    test_id: str,
    arm_ids,
    clicks,
    impressions,
    started_at,
    policy: Policy,
    *,
    reference_arm_id: str | None = None,
    n_distinct_headlines: int = 1,
    n_distinct_eyecatchers: int = 1,
) -> ExperimentDecision:
    """Evaluate one experiment under `policy`."""
    arm_ids = list(arm_ids)
    clicks = np.asarray(clicks, dtype=float)
    impressions = np.asarray(impressions, dtype=float)
    k = len(arm_ids)

    flags = assess_experiment(
        started_at,
        clicks,
        impressions,
        n_distinct_headlines=n_distinct_headlines,
        n_distinct_eyecatchers=n_distinct_eyecatchers,
        window_start=policy.cache_window_start,
        window_end=policy.cache_window_end,
    )

    total_impressions = int(impressions.sum()) if impressions.size else 0
    pooled_ctr = float(clicks.sum() / impressions.sum()) if impressions.sum() > 0 else float("nan")
    best_arm = arm_ids[int(np.argmax(clicks / np.maximum(impressions, 1)))] if k else None
    reference_arm_id = reference_arm_id or (arm_ids[0] if k else None)

    n_per_arm = total_impressions / k if k else float("nan")
    mde = minimum_detectable_effect(
        pooled_ctr, n_per_arm, power=policy.power_target, alpha=policy.alpha
    )
    power_at = {
        lift: prospective_power(pooled_ctr, lift, n_per_arm, alpha=policy.alpha)
        for lift in policy.prospective_lifts
    }
    need_n = {
        lift: required_sample_per_arm(
            pooled_ctr, lift, power=policy.power_target, alpha=policy.alpha
        )
        for lift in policy.prospective_lifts
    }

    base = dict(
        test_id=test_id,
        selected_arm_id=None,
        randomization_unreliable=flags.randomization_unreliable,
        attribution_limited=flags.attribution_limited,
        n_arms=k,
        total_impressions=total_impressions,
        pooled_ctr=pooled_ctr,
        reference_arm_id=reference_arm_id,
        best_ctr_arm_id=best_arm,
        srm_pvalue=flags.srm_pvalue,
        mde_relative=mde,
        prospective_power=power_at,
        required_n_per_arm=need_n,
    )

    if flags.is_invalid:
        # Still emitted as a row: excluded from inference, not from the warehouse.
        return ExperimentDecision(
            decision=Decision.INVALID,
            reasons=list(flags.reasons),
            is_inferentially_eligible=False,
            omnibus_pvalue=None,
            bayes_prob_exceeds=None,
            comparisons=[],
            **base,
        )

    _, omnibus_p, _ = omnibus_ctr_test(clicks, impressions)

    # Every ordered pair: does arm i beat arm j by more than theta?
    raw: list[Comparison] = []
    for i in range(k):
        for j in range(k):
            if i == j:
                continue
            res = compare_arms(
                int(clicks[i]),
                int(impressions[i]),
                int(clicks[j]),
                int(impressions[j]),
                ratio_null=policy.launch_ratio,
                alpha=policy.alpha,
            )
            raw.append(
                Comparison(
                    treatment_arm_id=arm_ids[i],
                    reference_arm_id=arm_ids[j],
                    risk_ratio=res.risk_ratio,
                    rr_lo=res.rr_lo,
                    rr_hi=res.rr_hi,
                    p_value=res.p_value,
                    p_adjusted=None,
                    rejected=False,
                    rr_estimable=res.rr_estimable,
                    note=res.reason,
                )
            )

    rejected, adjusted = adjust(
        [c.p_value for c in raw], method=policy.multiplicity_method, alpha=policy.alpha
    )
    for c, rej, adj in zip(raw, rejected, adjusted, strict=True):
        c.rejected = bool(rej)
        c.p_adjusted = None if not np.isfinite(adj) else float(adj)

    omnibus_passed = (not policy.require_omnibus_gate) or (
        omnibus_p is not None and omnibus_p < policy.omnibus_alpha
    )

    winner = _arm_beating_all(arm_ids, raw)
    reasons: list[str] = []
    bayes = None

    if winner is not None and omnibus_passed:
        decision = Decision.LAUNCH
        selected = winner
        reasons.append(
            f"arm {winner[:8]} beats every other arm at RR > {policy.launch_ratio:.2f} "
            f"after {policy.multiplicity_method} adjustment within this experiment"
        )
        bayes = _bayes_for(winner, arm_ids, clicks, impressions, policy)
    else:
        selected = None
        if winner is not None and not omnibus_passed:
            reasons.append(
                f"an arm passed its pairwise tests but the omnibus gate did not "
                f"(p={omnibus_p:.3g} >= {policy.omnibus_alpha})"
            )
        if _no_plausible_winner(arm_ids, raw, policy.launch_ratio):
            decision = Decision.NO_MEANINGFUL_WIN
            reasons.append(
                f"no arm can plausibly exceed RR {policy.launch_ratio:.2f} against all "
                f"others; a worthwhile win is ruled out by the descriptive bounds"
            )
        else:
            decision = Decision.CONTINUE
            reasons.append(
                "evidence remains compatible with a worthwhile effect; "
                "more sample is required to decide"
            )
            if np.isfinite(mde):
                reasons.append(f"smallest detectable relative lift at current n is {mde:.1%}")

    if flags.attribution_limited:
        reasons.append(
            "ATTRIBUTION_LIMITED: headline and image both vary, so the effect cannot be "
            "attributed to either component (the package remains a valid unit to choose)"
        )
    if any(not c.rr_estimable for c in raw):
        reasons.append(
            "RR_NOT_ESTIMABLE on at least one comparison (zero-click arm); "
            "those comparisons cannot support a launch"
        )

    return ExperimentDecision(
        decision=decision,
        reasons=reasons,
        is_inferentially_eligible=True,
        omnibus_pvalue=omnibus_p,
        bayes_prob_exceeds=bayes,
        comparisons=raw,
        **{**base, "selected_arm_id": selected},
    )


def _arm_beating_all(arm_ids, comparisons: list[Comparison]) -> str | None:
    """The arm whose every outward comparison rejects H0: RR <= 1 + theta.

    A non-estimable comparison can never reject, so a zero-click arm anywhere in an
    arm's row automatically disqualifies that arm from winning.
    """
    by_treatment: dict[str, list[Comparison]] = {a: [] for a in arm_ids}
    for c in comparisons:
        by_treatment[c.treatment_arm_id].append(c)
    winners = [
        arm
        for arm, rows in by_treatment.items()
        if rows and all(r.rejected and r.rr_estimable for r in rows)
    ]
    # Beating every other arm is mutually exclusive, so more than one is impossible;
    # if adjustment ever produced a tie, refusing to pick is the honest outcome.
    return winners[0] if len(winners) == 1 else None


def _no_plausible_winner(arm_ids, comparisons: list[Comparison], launch_ratio: float) -> bool:
    """True when no arm retains room to beat every other arm by more than theta.

    An arm stays plausible while all of its outward upper bounds leave the threshold
    reachable. If every arm has at least one comparison whose upper bound sits below
    the threshold, a meaningful win has been ruled out.
    """
    by_treatment: dict[str, list[Comparison]] = {a: [] for a in arm_ids}
    for c in comparisons:
        by_treatment[c.treatment_arm_id].append(c)

    for rows in by_treatment.values():
        if not rows:
            continue
        # Missing bounds mean "not ruled out" -- absence of evidence is not evidence.
        plausible = all(r.rr_hi is None or r.rr_hi >= launch_ratio for r in rows)
        if plausible:
            return False
    return True


def _bayes_for(winner: str, arm_ids, clicks, impressions, policy: Policy) -> float | None:
    """Posterior probability the winner beats its strongest rival by more than theta."""
    idx = arm_ids.index(winner)
    others = [i for i in range(len(arm_ids)) if i != idx]
    if not others:
        return None
    rival = max(others, key=lambda i: clicks[i] / max(impressions[i], 1))
    a_t, b_t = posterior_params(
        clicks[idx], impressions[idx], policy.bayes_prior_alpha, policy.bayes_prior_beta
    )
    a_r, b_r = posterior_params(
        clicks[rival], impressions[rival], policy.bayes_prior_alpha, policy.bayes_prior_beta
    )
    return float(
        prob_ratio_exceeds(a_t, b_t, a_r, b_r, c=policy.launch_ratio, eps=policy.bayes_support_eps)[
            0
        ]
    )
