"""Reports must carry the governance context, not just the verdict."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from experimentguard.config import load_frozen_policy, policy_checksum
from experimentguard.report import render_html, summary_rows_from, to_csv, to_json


@pytest.fixture(scope="module")
def policy():
    return load_frozen_policy()


ARMS = [
    dict(
        label="Arm 1 (reference)",
        impressions=3052,
        clicks=150,
        ctr=0.0491,
        ctr_lo=0.0419,
        ctr_hi=0.0575,
        role="reference (display only)",
    ),
    dict(
        label="Arm 2",
        impressions=3033,
        clicks=122,
        ctr=0.0402,
        ctr_lo=0.0338,
        ctr_hi=0.0478,
        role="challenger",
    ),
]


def test_html_states_the_decision_and_its_reasons(policy):
    html = render_html(
        policy=policy,
        test_id="t1",
        official="CONTINUE",
        reasons=["evidence remains compatible with a worthwhile effect"],
        arms=ARMS,
    )
    assert "CONTINUE" in html
    assert "compatible with a worthwhile effect" in html


def test_html_separates_scenario_from_official(policy):
    """A slider position must never be mistakable for the governed outcome."""
    html = render_html(
        policy=policy,
        test_id="t1",
        official="CONTINUE",
        scenario="LAUNCH",
        scenario_policy=policy.scenario(practical_threshold=0.01),
    )
    assert "Official decision" in html
    assert "Scenario decision" in html
    assert "not the governed outcome" in html
    assert "This is a what-if" in html


def test_html_carries_the_statistical_caveats(policy):
    html = render_html(policy=policy, test_id="t1", official="LAUNCH", arms=ARMS)
    assert "descriptive" in html  # intervals are not family-wise
    assert "post-hoc" in html  # observed power is not used
    assert "not a control" in html  # the reference arm has no causal status


def test_html_embeds_the_policy_checksum(policy):
    html = render_html(policy=policy, test_id="t1", official="LAUNCH")
    assert policy_checksum()[:16] in html


def test_html_escapes_headline_text(policy):
    """Archive headlines are arbitrary text and must not be able to inject markup."""
    hostile = [
        dict(
            label="<script>alert(1)</script>",
            impressions=10,
            clicks=1,
            ctr=0.1,
            ctr_lo=0.0,
            ctr_hi=0.4,
            role="challenger",
        )
    ]
    html = render_html(policy=policy, test_id="t1", official="CONTINUE", arms=hostile)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_is_self_contained(policy):
    """No external assets: the file must render offline and print to PDF."""
    html = render_html(policy=policy, test_id="t1", official="LAUNCH", arms=ARMS)
    for marker in ("http://", "https://", "<img", "<link"):
        assert marker not in html


def test_json_envelope_carries_policy_and_caveats(policy):
    payload = to_json(pd.DataFrame([{"test_id": "t1", "decision": "CONTINUE"}]), policy)
    doc = json.loads(payload)

    assert doc["policy"]["checksum"] == policy_checksum()
    assert doc["policy"]["practical_threshold"] == policy.practical_threshold
    assert doc["policy"]["is_frozen"] is True
    assert len(doc["caveats"]) >= 4
    assert any("observed power" in c for c in doc["caveats"])
    assert doc["result"][0]["decision"] == "CONTINUE"


def test_json_marks_a_scenario_policy_as_not_frozen(policy):
    doc = json.loads(to_json(pd.DataFrame([{"a": 1}]), policy.scenario(practical_threshold=0.2)))
    assert doc["policy"]["is_frozen"] is False
    assert doc["policy"]["practical_threshold"] == 0.2


def test_csv_round_trips():
    df = pd.DataFrame([{"test_id": "t1", "decision": "LAUNCH"}])
    assert pd.read_csv(pd.io.common.BytesIO(to_csv(df))).equals(df)


def test_summary_rows_handle_missing_values():
    row = pd.Series(
        {
            "n_arms": 3,
            "total_impressions": 9000,
            "pooled_ctr": 0.015,
            "mde_relative": None,
            "power_at_5pct": float("nan"),
        }
    )
    rows = dict(summary_rows_from(row))
    assert rows["Arms"] == "3"
    assert rows["Minimum detectable effect (relative)"] == "n/a"
    assert rows["Prospective power at 5% lift"] == "n/a"
