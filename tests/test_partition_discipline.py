"""The three archive partitions exist so a policy can be frozen before it is graded.

These tests enforce that the holdout is not consumed by any default code path.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from experimentguard import analyze, config


def test_default_analysis_partition_is_exploratory():
    assert config.DEFAULT_PARTITION == "exploratory"


def test_holdout_requires_explicit_confirmation():
    """`analyze` must refuse the holdout unless the caller confirms a final read."""
    source = inspect.getsource(analyze)
    assert "confirm_final" in source
    assert "HOLDOUT_LOG" in source


def test_holdout_log_exists_and_describes_the_rule():
    text = config.HOLDOUT_LOG_PATH.read_text()
    assert "opened" in text.lower()
    assert "confirm-final" in text


def test_no_module_silently_defaults_to_holdout():
    src_root = Path(config.__file__).resolve().parent
    offenders = []
    for path in src_root.rglob("*.py"):
        text = path.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if 'partition="holdout"' in stripped or "partition='holdout'" in stripped:
                offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], f"holdout used as a default: {offenders}"
