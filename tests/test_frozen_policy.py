"""The frozen policy is the official decision contract; changes must be deliberate."""

from __future__ import annotations

from experimentguard.config import (
    FROZEN_POLICY_PATH,
    load_frozen_policy,
    policy_checksum,
    recorded_checksum,
)


def test_frozen_policy_checksum_matches_the_recorded_value():
    """If this fails, the policy file changed. That is allowed -- but it must be an
    intentional act, with the recorded checksum and HOLDOUT_LOG updated to match."""
    assert policy_checksum() == recorded_checksum(), (
        "policy/frozen_policy.yml changed without updating policy/frozen_policy.sha256"
    )


def test_frozen_policy_is_marked_frozen():
    assert load_frozen_policy().is_frozen


def test_scenario_derivation_cannot_forge_a_frozen_policy():
    frozen = load_frozen_policy()
    scenario = frozen.scenario(practical_threshold=0.5, is_frozen=True)
    assert scenario.is_frozen is False
    assert frozen.practical_threshold == 0.05  # original untouched


def test_policy_values_are_the_reviewed_ones():
    p = load_frozen_policy()
    assert p.practical_threshold == 0.05
    assert p.multiplicity_method == "holm"  # within-experiment family, not global BH
    assert p.require_omnibus_gate is True
    assert p.launch_ratio == 1.05
    assert str(p.cache_window_start) == "2013-06-25"
    assert str(p.cache_window_end) == "2014-01-10"


def test_policy_file_documents_the_gatekeeping_caveat():
    """The omnibus step is gatekeeping, not closed testing. The file must not claim
    error control it does not provide."""
    text = FROZEN_POLICY_PATH.read_text().lower()
    assert "gatekeeping" in text
    assert "not closed testing" in text
