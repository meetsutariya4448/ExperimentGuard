"""Downloadable decision reports.

Every report states both the official (frozen-policy) decision and, when the reader
has been exploring alternative thresholds, the scenario decision -- clearly separated,
so a slider position can never be mistaken for the governed outcome. The frozen
policy's checksum is printed on each report so a decision can be traced back to the
exact contract that produced it.

HTML is self-contained (no external assets) and prints cleanly to PDF from a browser,
which avoids adding a native-build PDF dependency for a format most readers convert
anyway.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime

import pandas as pd
from jinja2 import Environment

from experimentguard.config import Policy, policy_checksum

_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ExperimentGuard decision report{% if test_id %} - {{ test_id }}{% endif %}</title>
<style>
  :root { color-scheme: light; }
  body { font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 2.5rem; background: #fbfbfa; color: #1a1a18; }
  .wrap { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
  h2 { font-size: 1.05rem; margin: 2rem 0 .6rem; padding-bottom: .3rem;
       border-bottom: 1px solid #e3e3df; }
  .sub { color: #6b6b64; margin: 0 0 1.5rem; }
  .verdict { display: inline-block; padding: .35rem .8rem; border-radius: 5px;
             font-weight: 600; letter-spacing: .02em; }
  .LAUNCH { background: #d8ece0; color: #17563a; }
  .CONTINUE { background: #dde6f5; color: #1f3f77; }
  .NO_MEANINGFUL_WIN { background: #f4e4d6; color: #7a3f13; }
  .INVALID { background: #f2dada; color: #7d2020; }
  table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; }
  th, td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #ebebe6; }
  th { font-weight: 600; color: #4a4a44; background: #f5f5f2; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  ul { margin: .4rem 0 1rem; padding-left: 1.2rem; }
  li { margin: .2rem 0; }
  .note { background: #f6f3e8; border-left: 3px solid #c9b77e; padding: .7rem .9rem;
          margin: 1rem 0; font-size: .92rem; }
  footer { margin-top: 2.5rem; padding-top: .8rem; border-top: 1px solid #e3e3df;
           color: #86867d; font-size: .82rem; }
  code { background: #f0f0ec; padding: .1rem .3rem; border-radius: 3px; font-size: .88em; }
</style></head><body><div class="wrap">

<h1>ExperimentGuard decision report</h1>
<p class="sub">{{ test_id or "Portfolio summary" }} &middot; generated {{ generated_at }}</p>

{% if official %}
<h2>Official decision</h2>
<p><span class="verdict {{ official }}">{{ official }}</span>
   &nbsp;<small>frozen policy v{{ policy.policy_version }} &middot;
   threshold {{ "%.0f"|format(policy.practical_threshold * 100) }}% relative lift &middot;
   {{ policy.multiplicity_method }} within experiment</small></p>
{% if reasons %}<ul>{% for r in reasons %}<li>{{ r }}</li>{% endfor %}</ul>{% endif %}
{% endif %}

{% if scenario %}
<h2>Scenario decision (exploratory)</h2>
<p><span class="verdict {{ scenario }}">{{ scenario }}</span>
   &nbsp;<small>threshold {{ "%.0f"|format(scenario_policy.practical_threshold * 100) }}%
   &middot; not the governed outcome</small></p>
<div class="note"><strong>This is a what-if.</strong> It reflects thresholds chosen while
exploring, not the frozen policy. Only the official decision above is governed.</div>
{% endif %}

{% if arms %}
<h2>Arms</h2>
<table><thead><tr>
  <th>Arm</th><th class="num">Impressions</th><th class="num">Clicks</th>
  <th class="num">CTR</th><th class="num">95% CI</th><th>Role</th>
</tr></thead><tbody>
{% for a in arms %}<tr>
  <td>{{ a.label }}</td>
  <td class="num">{{ "{:,}".format(a.impressions) }}</td>
  <td class="num">{{ "{:,}".format(a.clicks) }}</td>
  <td class="num">{{ "%.3f"|format(a.ctr * 100) }}%</td>
  <td class="num">{{ "%.3f"|format(a.ctr_lo * 100) }}&ndash;{{ "%.3f"|format(a.ctr_hi * 100) }}%</td>
  <td>{{ a.role }}</td>
</tr>{% endfor %}
</tbody></table>
<div class="note">The reference arm is the earliest-created arm, used only to orient
these displays. It is <strong>not a control</strong> &mdash; the archive's authors report
that no control-group concept was used &mdash; and no decision depends on it.</div>
{% endif %}

{% if summary_rows %}
<h2>Summary</h2>
<table><thead><tr><th>Measure</th><th class="num">Value</th></tr></thead><tbody>
{% for k, v in summary_rows %}<tr><td>{{ k }}</td><td class="num">{{ v }}</td></tr>{% endfor %}
</tbody></table>
{% endif %}

<footer>
Frozen policy checksum <code>{{ checksum[:16] }}&hellip;</code>.
Confidence and credible intervals shown are <strong>descriptive and unadjusted</strong>;
the launch gate is the multiplicity-adjusted threshold test.
Prospective power only &mdash; observed (post-hoc) power is not used anywhere.
</footer>
</div></body></html>
"""


def _fmt(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.4g}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def render_html(
    *,
    policy: Policy,
    test_id: str | None = None,
    official: str | None = None,
    reasons=None,
    arms=None,
    summary_rows=None,
    scenario: str | None = None,
    scenario_policy: Policy | None = None,
) -> str:
    env = Environment(autoescape=True)
    return env.from_string(_TEMPLATE).render(
        policy=policy,
        test_id=test_id,
        official=official,
        reasons=list(reasons or []),
        arms=list(arms or []),
        summary_rows=list(summary_rows or []),
        scenario=scenario,
        scenario_policy=scenario_policy or policy,
        checksum=policy_checksum(),
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )


def to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def to_json(payload, policy: Policy) -> bytes:
    """JSON export carrying the policy contract alongside the result."""
    if is_dataclass(payload) and not isinstance(payload, type):
        payload = asdict(payload)
    elif isinstance(payload, pd.DataFrame):
        payload = json.loads(payload.to_json(orient="records", date_format="iso"))

    envelope = {
        "generated_at": datetime.now(UTC).isoformat(),
        "policy": {
            "version": policy.policy_version,
            "practical_threshold": policy.practical_threshold,
            "multiplicity_method": policy.multiplicity_method,
            "alpha": policy.alpha,
            "is_frozen": policy.is_frozen,
            "checksum": policy_checksum(),
        },
        "caveats": [
            "Intervals are descriptive and unadjusted; the gate is the adjusted test.",
            "Prospective power only; observed power is never a decision input.",
            "The reference arm is not a control and gates no decision.",
            "randomization_unreliable is derived from the authors' documented "
            "cache-misconfiguration window (2013-06-25 to 2014-01-10).",
        ],
        "result": payload,
    }
    return json.dumps(envelope, indent=2, default=str).encode()


def summary_rows_from(row: pd.Series) -> list[tuple[str, str]]:
    """Build the summary table for one experiment's decision row."""
    pairs = [
        ("Arms", row.get("n_arms")),
        ("Total impressions", row.get("total_impressions")),
        ("Pooled CTR", f"{row.get('pooled_ctr', float('nan')) * 100:.3f}%"),
        ("Omnibus p-value", row.get("omnibus_pvalue")),
        ("Minimum detectable effect (relative)", _pct(row.get("mde_relative"))),
        ("Prospective power at 5% lift", _pct(row.get("power_at_5pct"))),
        ("Prospective power at 20% lift", _pct(row.get("power_at_20pct"))),
        ("Required n per arm for 10% lift", row.get("required_n_at_10pct")),
        ("SRM p-value (diagnostic only)", row.get("srm_pvalue")),
        ("Bayesian P(RR > threshold)", row.get("bayes_prob_exceeds")),
    ]
    return [(k, _fmt(v)) for k, v in pairs]


def _pct(value) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value * 100:.1f}%"
