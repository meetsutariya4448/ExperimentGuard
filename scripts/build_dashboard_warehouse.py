"""Build the read-only warehouse artifact used by the hosted dashboard."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
from pathlib import Path

import duckdb

TABLES = (
    "dim_experiment",
    "dim_arm",
    "dim_date",
    "fct_arm_result",
    "fct_arm_comparison",
    "fct_experiment_decision",
    "fct_policy_comparison",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Source warehouse does not exist: {source}")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(destination))
    try:
        source_sql = str(source.resolve()).replace("'", "''")
        connection.execute(f"ATTACH '{source_sql}' AS source (READ_ONLY)")
        for table in TABLES:
            connection.execute(f"CREATE TABLE {table} AS SELECT * FROM source.main.{table}")
            expected = connection.execute(f"SELECT count(*) FROM source.main.{table}").fetchone()[0]
            actual = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if actual != expected:
                raise RuntimeError(f"{table}: copied {actual:,} rows; expected {expected:,}")
            print(f"{table}: {actual:,} rows")
        connection.execute("DETACH source")
        connection.execute("CHECKPOINT")
    finally:
        connection.close()


def compress(source: Path) -> Path:
    destination = source.with_suffix(source.suffix + ".gz")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite: {destination}")
    with (
        source.open("rb") as source_handle,
        destination.open("wb") as output_handle,
        gzip.GzipFile(
            fileobj=output_handle, mode="wb", compresslevel=9, mtime=0
        ) as destination_handle,
    ):
        shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/experimentguard.duckdb"))
    parser.add_argument(
        "--output", type=Path, default=Path("dist/experimentguard-dashboard.duckdb")
    )
    args = parser.parse_args()

    build(args.source, args.output)
    compressed = compress(args.output)
    print(f"database_sha256={sha256(args.output)}")
    print(f"compressed_sha256={sha256(compressed)}")
    print(f"artifact={compressed}")


if __name__ == "__main__":
    main()
