"""Configuration, paths, and the frozen decision policy.

The policy that produces *official* decisions is frozen on disk and checksummed.
Scenario exploration in the UI constructs a separate, clearly labelled policy object
and can never overwrite the frozen one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
EXPORT_DIR = PROJECT_ROOT / "exports"
POLICY_DIR = PROJECT_ROOT / "policy"
DUCKDB_PATH = DATA_DIR / "experimentguard.duckdb"

FROZEN_POLICY_PATH = POLICY_DIR / "frozen_policy.yml"
FROZEN_CHECKSUM_PATH = POLICY_DIR / "frozen_policy.sha256"
HOLDOUT_LOG_PATH = POLICY_DIR / "HOLDOUT_LOG.md"

# The three deployed partitions. `undeployed` is deliberately absent: those packages
# never ran and carry no impressions.
PARTITIONS = ("exploratory", "confirmatory", "holdout")
DEFAULT_PARTITION = "exploratory"

# OSF download identifiers for the deployed archive files.
ARCHIVE_FILES = {
    "exploratory": (
        "https://osf.io/download/3vqmp/",
        "upworthy-archive-exploratory-packages-03.12.2020.csv",
    ),
    "confirmatory": (
        "https://osf.io/download/vy8mj/",
        "upworthy-archive-confirmatory-packages-03.12.2020.csv",
    ),
    "holdout": (
        "https://osf.io/download/ynf3k/",
        "upworthy-archive-holdout-packages-03.12.2020.csv",
    ),
}

# Published totals for the deployed archive, asserted after ingestion.
EXPECTED_TEST_COUNT = 32_487
EXPECTED_PACKAGE_COUNT = 150_817


@dataclass(frozen=True)
class Policy:
    """A decision policy. `is_frozen` distinguishes official from scenario runs."""

    policy_version: str
    practical_threshold: float
    alpha: float
    multiplicity_method: str
    require_omnibus_gate: bool
    omnibus_alpha: float
    cache_window_start: date
    cache_window_end: date
    power_target: float
    prospective_lifts: tuple[float, ...]
    bayes_prior_alpha: float
    bayes_prior_beta: float
    bayes_support_eps: float
    is_frozen: bool = False

    @property
    def launch_ratio(self) -> float:
        """The risk ratio a winning arm must exceed: 1 + theta."""
        return 1.0 + self.practical_threshold

    def scenario(self, **overrides) -> Policy:
        """Derive an exploratory scenario policy. Never frozen, never official.

        `is_frozen` is discarded if supplied: a derived policy cannot claim to be the
        official one, so the flag is forced rather than allowed through or raising.
        """
        overrides.pop("is_frozen", None)
        return replace(self, is_frozen=False, **overrides)


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def load_frozen_policy(path: Path | None = None) -> Policy:
    """Load the official frozen policy from disk."""
    path = path or FROZEN_POLICY_PATH
    raw = yaml.safe_load(path.read_text())
    return Policy(
        policy_version=str(raw["policy_version"]),
        practical_threshold=float(raw["practical_threshold"]),
        alpha=float(raw["alpha"]),
        multiplicity_method=str(raw["multiplicity_method"]),
        require_omnibus_gate=bool(raw["require_omnibus_gate"]),
        omnibus_alpha=float(raw["omnibus_alpha"]),
        cache_window_start=_as_date(raw["cache_window_start"]),
        cache_window_end=_as_date(raw["cache_window_end"]),
        power_target=float(raw["power_target"]),
        prospective_lifts=tuple(float(x) for x in raw["prospective_lifts"]),
        bayes_prior_alpha=float(raw["bayes_prior_alpha"]),
        bayes_prior_beta=float(raw["bayes_prior_beta"]),
        bayes_support_eps=float(raw["bayes_support_eps"]),
        is_frozen=True,
    )


def policy_checksum(path: Path | None = None) -> str:
    """SHA-256 of the frozen policy file as it sits on disk."""
    path = path or FROZEN_POLICY_PATH
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_checksum(path: Path | None = None) -> str:
    return (path or FROZEN_CHECKSUM_PATH).read_text().strip()
