"""Parquet exports of the star schema, for Power BI and other BI tools.

Power BI Desktop is Windows-only and this project is developed on macOS, so the
deliverable is the modelled star schema plus a documented semantic model, rather than
a .pbix that could not be built or verified here. Everything a report author needs --
grain, relationships, cardinality, and the DAX measures -- ships in powerbi/.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from experimentguard.config import DUCKDB_PATH, EXPORT_DIR

# Dimensions first: a BI tool importing in this order gets its relationships resolved.
TABLES = (
    "dim_date",
    "dim_experiment",
    "dim_arm",
    "fct_arm_result",
    "fct_arm_comparison",
    "fct_experiment_decision",
    "fct_policy_comparison",
)


def export(db_path: Path = DUCKDB_PATH, out_dir: Path = EXPORT_DIR) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)
    counts: dict[str, int] = {}
    for table in TABLES:
        target = out_dir / f"{table}.parquet"
        con.execute(f"COPY (SELECT * FROM {table}) TO '{target}' (FORMAT PARQUET)")
        counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:28} {counts[table]:>9,} rows -> {target.name}")
    con.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the star schema to Parquet.")
    parser.add_argument("--out", type=Path, default=EXPORT_DIR)
    args = parser.parse_args()
    print(f"Exporting star schema to {args.out} ...")
    export(out_dir=args.out)


if __name__ == "__main__":
    main()
