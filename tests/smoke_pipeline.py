"""End-to-end pipeline smoke test against the committed fixture.

Runs ingestion, the decision engine and the policy layer over ~90 real archive rows
chosen to cover the awkward cases: the cache window, zero-click arms, an all-zero
experiment, two-arm and six-arm experiments. Fast enough for CI and offline, so a push
never pulls ~95 MB of archive data.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from experimentguard.analyze import analyse_partition, write  # noqa: E402
from experimentguard.config import load_frozen_policy  # noqa: E402
from experimentguard.ingest import read_partition  # noqa: E402
from experimentguard.schemas import validate_raw  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "archive_fixture.csv"


def main() -> int:
    if not FIXTURE.exists():
        print(f"FAIL: fixture missing at {FIXTURE}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "smoke.duckdb"

        print("1. ingest + validate")
        df = read_partition(FIXTURE, "exploratory")
        df = validate_raw(df)
        con = duckdb.connect(str(db))
        con.register("incoming", df)
        con.execute("CREATE TABLE raw_packages AS SELECT * FROM incoming")
        con.close()
        print(f"   {len(df)} packages / {df.test_id.nunique()} tests validated")

        assert df["arm_id"].is_unique, "arm_id must be unique"
        assert (df["clicks"] <= df["impressions"]).all()

        print("2. decision engine")
        frames = analyse_partition("exploratory", load_frozen_policy(), db, progress_every=0)
        write(frames, "exploratory", db)

        stats = frames["analysis_experiment_stats"]
        comparisons = frames["analysis_arm_comparison"]
        selections = frames["analysis_policy_selection"]

        print("3. invariants")
        checks: list[tuple[str, bool]] = [
            ("every experiment has a decision row", len(stats) == df.test_id.nunique()),
            (
                "decisions are in the allowed domain",
                set(stats.decision) <= {"LAUNCH", "NO_MEANINGFUL_WIN", "CONTINUE", "INVALID"},
            ),
            (
                "INVALID is never inferentially eligible",
                not stats[stats.decision == "INVALID"].is_inferentially_eligible.any(),
            ),
            (
                "LAUNCH always names an arm",
                stats[stats.decision == "LAUNCH"].selected_arm_id.notna().all(),
            ),
            (
                "non-LAUNCH never names an arm",
                stats[stats.decision != "LAUNCH"].selected_arm_id.isna().all(),
            ),
            ("the fixture exercises the cache window", bool(stats.randomization_unreliable.any())),
            ("the fixture exercises zero-click arms", bool((~comparisons.rr_estimable).any())),
            ("four policies per experiment", len(selections) == 4 * len(stats)),
            (
                "selected_arm_id is null exactly when status is not ONE",
                bool(
                    (
                        (selections.selection_status == "ONE") == selections.selected_arm_id.notna()
                    ).all()
                ),
            ),
            (
                "no decision field depends on observed power",
                not any("observed" in c.lower() for c in stats.columns),
            ),
        ]

        failed = [name for name, ok in checks if not ok]
        for name, ok in checks:
            print(f"   [{'ok' if ok else 'FAIL'}] {name}")

        if failed:
            print(f"\nFAILED: {len(failed)} invariant(s)")
            return 1

    mix = stats.decision.value_counts().to_dict()
    print(f"\nPipeline smoke test passed. Decision mix on the fixture: {mix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
