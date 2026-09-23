"""Run the decision engine across a partition and write the analysis tables.

Partition discipline is enforced here rather than by convention: the holdout cannot
be analysed without `--confirm-final`, and doing so appends to policy/HOLDOUT_LOG.md.
The archive's authors created exclusive partitions precisely so a policy can be
frozen before it is graded; reading the holdout casually would spend that once-only
evidence.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from experimentguard.config import (
    DEFAULT_PARTITION,
    DUCKDB_PATH,
    HOLDOUT_LOG_PATH,
    Policy,
    load_frozen_policy,
    policy_checksum,
)
from experimentguard.decision import evaluate_experiment
from experimentguard.policies import (
    editor_winner,
    from_decision,
    naive_argmax_ctr,
    recorded_first_place,
)

_ARMS_SQL = """
SELECT
    test_id,
    partition,
    arm_id,
    created_at,
    impressions,
    clicks,
    headline,
    eyecatcher_id,
    first_place,
    winner
FROM raw_packages
WHERE partition = ?
ORDER BY test_id, created_at, arm_id
"""


def _log_holdout_access(policy: Policy, reason: str) -> None:
    row = (
        f"| {datetime.now(UTC).date()} | {policy.policy_version} | "
        f"{policy_checksum()[:16]}... | {reason} | ingest CLI |\n"
    )
    text = HOLDOUT_LOG_PATH.read_text()
    text = text.replace("| _(no holdout access yet)_ | | | | |\n", "")
    HOLDOUT_LOG_PATH.write_text(text.rstrip("\n") + "\n" + row)


def analyse_partition(
    partition: str = DEFAULT_PARTITION,
    policy: Policy | None = None,
    db_path: Path = DUCKDB_PATH,
    *,
    confirm_final: bool = False,
    limit: int | None = None,
    progress_every: int = 2000,
) -> dict[str, pd.DataFrame]:
    """Evaluate every experiment in `partition`. Returns the analysis frames."""
    policy = policy or load_frozen_policy()

    if partition == "holdout" and not confirm_final:
        raise PermissionError(
            "The holdout partition may be analysed once, for final evaluation only. "
            "Pass --confirm-final (or confirm_final=True); the access is recorded in "
            "policy/HOLDOUT_LOG.md."
        )

    con = duckdb.connect(str(db_path), read_only=True)
    arms = con.execute(_ARMS_SQL, [partition]).df()
    con.close()
    if arms.empty:
        raise ValueError(f"no rows for partition {partition!r}; run ingest first")

    decisions, comparisons, selections = [], [], []
    groups = list(arms.groupby("test_id", sort=False))
    if limit:
        groups = groups[:limit]

    print(f"Analysing {len(groups):,} experiments in '{partition}' ...", flush=True)
    for i, (test_id, g) in enumerate(groups, start=1):
        # Deterministic reference arm: earliest created, ties broken by arm_id.
        # Display only -- it carries no causal status and gates no decision.
        g = g.sort_values(["created_at", "arm_id"])
        arm_ids = g["arm_id"].tolist()
        clicks = g["clicks"].to_numpy(dtype=float)
        impressions = g["impressions"].to_numpy(dtype=float)

        d = evaluate_experiment(
            test_id,
            arm_ids,
            clicks,
            impressions,
            g["created_at"].iloc[0],
            policy,
            reference_arm_id=arm_ids[0],
            n_distinct_headlines=int(g["headline"].nunique(dropna=True)),
            n_distinct_eyecatchers=int(g["eyecatcher_id"].nunique(dropna=True)),
        )

        decisions.append(
            {
                "test_id": test_id,
                "partition": partition,
                "decision": str(d.decision),
                "is_inferentially_eligible": d.is_inferentially_eligible,
                "randomization_unreliable": d.randomization_unreliable,
                "attribution_limited": d.attribution_limited,
                "selected_arm_id": d.selected_arm_id,
                "reference_arm_id": d.reference_arm_id,
                "best_ctr_arm_id": d.best_ctr_arm_id,
                "n_arms": d.n_arms,
                "total_impressions": d.total_impressions,
                "pooled_ctr": d.pooled_ctr,
                "srm_pvalue": d.srm_pvalue,
                "omnibus_pvalue": d.omnibus_pvalue,
                "mde_relative": d.mde_relative,
                "bayes_prob_exceeds": d.bayes_prob_exceeds,
                "started_at": g["created_at"].iloc[0],
                "start_hour": int(pd.Timestamp(g["created_at"].iloc[0]).hour),
                "reasons": " | ".join(d.reasons),
                **{f"power_at_{int(k * 100)}pct": v for k, v in d.prospective_power.items()},
                **{f"required_n_at_{int(k * 100)}pct": v for k, v in d.required_n_per_arm.items()},
            }
        )

        for c in d.comparisons:
            comparisons.append(
                {
                    "test_id": test_id,
                    "partition": partition,
                    "treatment_arm_id": c.treatment_arm_id,
                    "reference_arm_id": c.reference_arm_id,
                    "risk_ratio": c.risk_ratio,
                    "rr_lo": c.rr_lo,
                    "rr_hi": c.rr_hi,
                    "p_value": c.p_value,
                    "p_adjusted": c.p_adjusted,
                    "rejected": c.rejected,
                    "rr_estimable": c.rr_estimable,
                    "note": c.note,
                }
            )

        for sel in (
            naive_argmax_ctr(test_id, arm_ids, clicks, impressions),
            recorded_first_place(test_id, arm_ids, g["first_place"].to_numpy()),
            editor_winner(test_id, arm_ids, g["winner"].to_numpy()),
            from_decision(test_id, d.selected_arm_id),
        ):
            selections.append(
                {
                    "test_id": test_id,
                    "partition": partition,
                    "policy": sel.policy,
                    "selection_status": str(sel.selection_status),
                    "selected_arm_id": sel.selected_arm_id,
                    "selection_count": sel.selection_count,
                    "is_inferentially_eligible": d.is_inferentially_eligible,
                }
            )

        if progress_every and i % progress_every == 0:
            print(f"  {i:,}/{len(groups):,}", flush=True)

    return {
        "analysis_experiment_stats": pd.DataFrame(decisions),
        "analysis_arm_comparison": pd.DataFrame(comparisons),
        "analysis_policy_selection": pd.DataFrame(selections),
    }


def write(frames: dict[str, pd.DataFrame], partition: str, db_path: Path = DUCKDB_PATH) -> None:
    """Replace this partition's rows in each analysis table."""
    con = duckdb.connect(str(db_path))
    for name, df in frames.items():
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()[0]
        con.register("incoming", df)
        if exists:
            con.execute(f"DELETE FROM {name} WHERE partition = ?", [partition])
            con.execute(f"INSERT INTO {name} SELECT * FROM incoming")
        else:
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM incoming")
        con.unregister("incoming")
        print(f"  wrote {len(df):,} rows to {name}")
    con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the decision engine over a partition.")
    parser.add_argument("--partition", default=DEFAULT_PARTITION)
    parser.add_argument("--confirm-final", action="store_true", help="required for holdout")
    parser.add_argument("--reason", default="final evaluation", help="recorded in HOLDOUT_LOG")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    policy = load_frozen_policy()
    frames = analyse_partition(
        args.partition, policy, confirm_final=args.confirm_final, limit=args.limit
    )
    write(frames, args.partition)

    if args.partition == "holdout" and args.confirm_final:
        _log_holdout_access(policy, args.reason)
        print(f"  recorded holdout access in {HOLDOUT_LOG_PATH}")

    stats = frames["analysis_experiment_stats"]
    print(f"\nDecision mix for '{args.partition}':")
    for decision, n in stats["decision"].value_counts().items():
        print(f"  {decision:20} {n:7,}  ({n / len(stats):6.2%})")
    eligible = stats[stats.is_inferentially_eligible]
    if len(eligible):
        print(f"\n  median MDE (eligible): {np.nanmedian(eligible.mde_relative):.1%}")


if __name__ == "__main__":
    main()
