"""Pandera schemas guarding the Python/warehouse boundaries.

Two gates: raw CSV as it lands from OSF, and the analysis frame before it is written
back into DuckDB. Anything that violates these is a bug in ingestion or analysis, not
a data quirk to be tolerated downstream.
"""

from __future__ import annotations

from pandera.pandas import Check, Column, DataFrameSchema

__all__ = ["RAW_PACKAGE_SCHEMA", "ANALYSIS_SCHEMA", "validate_raw", "validate_analysis"]

# The archive's own header. Note there is no package/arm id column: `arm_id` is
# constructed during ingestion from (source_file, source_row_number, test_id).
RAW_PACKAGE_SCHEMA = DataFrameSchema(
    {
        "arm_id": Column(str, nullable=False, unique=True),
        "source_row_number": Column("int64", nullable=False),
        "source_file": Column(str, nullable=False),
        "partition": Column(str, Check.isin(["exploratory", "confirmatory", "holdout"])),
        "test_id": Column(str, nullable=False),
        "created_at": Column("datetime64[ns]", nullable=False),
        "impressions": Column("int64", Check.gt(0), nullable=False),
        "clicks": Column("int64", Check.ge(0), nullable=False),
        "headline": Column(str, nullable=True),
        "eyecatcher_id": Column(str, nullable=True),
        "slug": Column(str, nullable=True),
        "lede": Column(str, nullable=True),
        "excerpt": Column(str, nullable=True),
        "test_week": Column("int64", nullable=True),
        "first_place": Column(bool, nullable=False),
        "winner": Column(bool, nullable=False),
        "significance": Column(float, nullable=True),
    },
    checks=[
        # The one cross-column invariant that must hold for any binomial arm.
        Check(lambda df: (df["clicks"] <= df["impressions"]).all(), name="clicks_le_impressions"),
    ],
    strict="filter",
    coerce=True,
)

ANALYSIS_SCHEMA = DataFrameSchema(
    {
        "test_id": Column(str, nullable=False, unique=True),
        "partition": Column(str, Check.isin(["exploratory", "confirmatory", "holdout"])),
        "decision": Column(
            str,
            Check.isin(["LAUNCH", "NO_MEANINGFUL_WIN", "CONTINUE", "INVALID"]),
            nullable=False,
        ),
        "n_arms": Column("int64", Check.ge(1)),
        "total_impressions": Column("int64", Check.ge(0)),
        "is_inferentially_eligible": Column(bool, nullable=False),
        "randomization_unreliable": Column(bool, nullable=False),
        "attribution_limited": Column(bool, nullable=False),
        "selected_arm_id": Column(str, nullable=True),
        "srm_pvalue": Column(float, nullable=True),
        "omnibus_pvalue": Column(float, nullable=True),
        "mde_relative": Column(float, nullable=True),
    },
    strict="filter",
    coerce=True,
)


def validate_raw(df):
    """Validate ingested archive rows. `lazy` so every violation is reported at once."""
    return RAW_PACKAGE_SCHEMA.validate(df, lazy=True)


def validate_analysis(df):
    return ANALYSIS_SCHEMA.validate(df, lazy=True)
