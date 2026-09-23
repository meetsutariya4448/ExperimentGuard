"""Download the deployed Upworthy archive partitions and load them into DuckDB.

Three details here are consequences of what the real files actually contain:

1. `created_at` has *mixed* timestamp formats -- most rows carry fractional seconds,
   some do not. pandas' inference picks the fractional format from the first rows and
   then fails partway through the file, so the format is pinned to ISO8601 explicitly.

2. There is no package/arm identifier column. `slug` is not unique (22,334 distinct
   across 22,666 exploratory rows), so a stable `arm_id` is constructed by hashing
   (source_file, source_row_number, test_id).

3. The unnamed leading index column is a *global* row number spanning the whole
   archive (0 .. 150,816 across the three deployed partitions), which is why it makes
   a sound hash input and independently corroborates the 150,817-package total.

The `undeployed` file is never fetched: those packages never ran and have no
impressions, so they cannot inform a decision.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd

from experimentguard.config import (
    ARCHIVE_FILES,
    DUCKDB_PATH,
    EXPECTED_PACKAGE_COUNT,
    EXPECTED_TEST_COUNT,
    PARTITIONS,
    RAW_DIR,
)
from experimentguard.schemas import validate_raw

_RENAMES = {"Unnamed: 0": "source_row_number", "clickability_test_id": "test_id"}


def download_partition(partition: str, dest_dir: Path = RAW_DIR, force: bool = False) -> Path:
    """Fetch one partition's CSV, skipping the download if it is already present."""
    url, filename = ARCHIVE_FILES[partition]
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / filename
    if path.exists() and path.stat().st_size > 0 and not force:
        print(f"  [skip] {filename} already present ({path.stat().st_size / 1e6:.1f} MB)")
        return path
    print(f"  [get ] {filename} ...", flush=True)
    urllib.request.urlretrieve(url, path)  # noqa: S310 - fixed https OSF endpoints
    print(f"  [done] {filename} ({path.stat().st_size / 1e6:.1f} MB)")
    return path


def _arm_id(source_file: str, row_number: int, test_id: str) -> str:
    return hashlib.sha256(f"{source_file}|{row_number}|{test_id}".encode()).hexdigest()[:32]


def read_partition(path: Path, partition: str) -> pd.DataFrame:
    """Read and normalise one partition into the raw schema."""
    df = pd.read_csv(path, low_memory=False).rename(columns=_RENAMES)

    # Pinned format: the file mixes fractional and whole-second timestamps.
    df["created_at"] = pd.to_datetime(df["created_at"], format="ISO8601")

    df["source_file"] = path.name
    df["partition"] = partition
    df["arm_id"] = [
        _arm_id(path.name, int(row), str(tid))
        for row, tid in zip(df["source_row_number"], df["test_id"], strict=True)
    ]

    for col in ("first_place", "winner"):
        df[col] = df[col].astype(bool)
    for col in ("headline", "eyecatcher_id", "slug", "lede", "excerpt"):
        df[col] = df[col].astype("string").astype(object).where(df[col].notna(), None)

    return df


def load(db_path: Path = DUCKDB_PATH, partitions=PARTITIONS, force: bool = False) -> None:
    """Download, validate and load the deployed partitions into `raw_packages`."""
    frames = []
    for partition in partitions:
        path = download_partition(partition, force=force)
        df = read_partition(path, partition)
        print(f"  [read] {partition:12} {len(df):>7,} packages  {df.test_id.nunique():>6,} tests")
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    print(f"\nValidating {len(combined):,} rows against the raw schema ...")
    combined = validate_raw(combined)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS main")
    con.execute("DROP TABLE IF EXISTS raw_packages")
    con.register("incoming", combined)
    con.execute("CREATE TABLE raw_packages AS SELECT * FROM incoming")
    con.unregister("incoming")

    n_tests, n_pkgs = con.execute(
        "SELECT COUNT(DISTINCT test_id), COUNT(*) FROM raw_packages"
    ).fetchone()
    overlap = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT test_id FROM raw_packages
            GROUP BY test_id HAVING COUNT(DISTINCT partition) > 1
        )
        """
    ).fetchone()[0]
    con.close()

    print(f"\nLoaded {n_pkgs:,} packages across {n_tests:,} tests into {db_path}")
    _report("test count", n_tests, EXPECTED_TEST_COUNT, partitions)
    _report("package count", n_pkgs, EXPECTED_PACKAGE_COUNT, partitions)
    if overlap:
        raise ValueError(f"partitions are not mutually exclusive: {overlap} tests appear in >1")
    print("  [ok] partitions are mutually exclusive")


def _report(label: str, actual: int, expected: int, partitions) -> None:
    if set(partitions) != set(PARTITIONS):
        print(f"  [--] {label}: {actual:,} (partial load; published total is {expected:,})")
    elif actual == expected:
        print(f"  [ok] {label}: {actual:,} matches the published archive total")
    else:
        raise ValueError(f"{label} is {actual:,}, expected the published {expected:,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the Upworthy archive into DuckDB.")
    parser.add_argument("--partition", action="append", choices=list(PARTITIONS))
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--confirm-final", action="store_true", help="required to read holdout")
    args = parser.parse_args()

    partitions = tuple(args.partition) if args.partition else PARTITIONS
    if "holdout" in partitions and not args.confirm_final:
        # Ingestion may load holdout so the warehouse is complete; analysis is what
        # must stay gated. Loading it silently would make that gate easy to forget.
        print(
            "note: holdout is being loaded into the warehouse. Analysis of it still "
            "requires --confirm-final and is recorded in policy/HOLDOUT_LOG.md."
        )
    load(partitions=partitions, force=args.force)


if __name__ == "__main__":
    main()
