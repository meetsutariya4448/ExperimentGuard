"""ExperimentGuard - landing page and headline reliability findings."""

from __future__ import annotations

import streamlit as st

import _shared as sh

st.set_page_config(page_title="ExperimentGuard", page_icon=":material/science:", layout="wide")

partition = sh.sidebar("Overview")
p = sh.policy()

st.title("ExperimentGuard")
st.markdown(
    "**Would this A/B test justify shipping the change?** ExperimentGuard evaluates the "
    "Upworthy Research Archive &mdash; 32,487 fielded headline experiments, including a "
    "documented period of unreliable randomisation &mdash; and returns a governed decision "
    "for each one."
)

summary = sh.query(
    """
    SELECT
        COUNT(*)                                                  AS experiments,
        SUM(CASE WHEN decision = 'LAUNCH' THEN 1 ELSE 0 END)      AS launches,
        SUM(CASE WHEN randomization_unreliable THEN 1 ELSE 0 END) AS unreliable,
        SUM(CASE WHEN is_inferentially_eligible THEN 1 ELSE 0 END) AS eligible,
        median(CASE WHEN is_inferentially_eligible THEN mde_relative END) AS median_mde,
        SUM(CASE WHEN is_inferentially_eligible AND power_at_10pct >= 0.8
                 THEN 1 ELSE 0 END)                               AS powered_10
    FROM fct_experiment_decision WHERE partition = ?
    """,
    (partition,),
).iloc[0]

n = int(summary.experiments)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Experiments", f"{n:,}", help=f"Partition: {partition}")
c2.metric(
    "Would launch",
    f"{summary.launches / n:.1%}",
    help="One arm beat every other arm by more than the threshold, after adjustment.",
)
c3.metric(
    "Unreliable randomisation",
    f"{summary.unreliable / n:.1%}",
    help="Started inside the cache-misconfiguration window the archive's authors documented.",
)
c4.metric(
    "Median detectable lift",
    sh.pct(summary.median_mde),
    help="The smallest relative lift an experiment of this size could detect at 80% power.",
)

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Why most of this archive cannot answer its own question")
    powered_share = summary.powered_10 / max(int(summary.eligible), 1)
    st.markdown(
        f"""
The typical experiment here runs about 3,000 impressions per arm at roughly a 1.5%
click-through rate. At that size the smallest lift it could reliably detect is
**{sh.pct(summary.median_mde)}** &mdash; far larger than the single-digit improvements
teams actually ship for.

Only **{powered_share:.1%}** of eligible experiments have 80% power to detect a 10%
relative lift. A "winner" in the rest is usually indistinguishable from noise, which is
exactly the failure mode this platform exists to catch.
"""
    )
    st.info(
        "**A careful phrasing, deliberately.** When ExperimentGuard declines to launch, "
        "that means the evidence was insufficient under the stated policy &mdash; **not** "
        "that the effect is zero. Failing to reject a null hypothesis is not proof that "
        "nothing happened.",
        icon=":material/balance:",
    )

with right:
    st.subheader("The decision states")
    for name in sh.DECISION_ORDER:
        st.markdown(f"**{name}** &mdash; {sh.DECISION_HELP[name]}")
    st.caption(
        "NO_MEANINGFUL_WIN is the precise form of the brief's REJECT state: the evidence "
        "rules out a worthwhile win, rather than merely failing to find one."
    )

st.divider()
st.subheader("How a decision is reached")
st.markdown(
    """
1. **Validity gate.** Experiments starting between 2013-06-25 and 2014-01-10 are INVALID:
   the archive's authors traced a suspected Cloudflare cache misconfiguration to that
   window and discourage causal inference from it. Integrity failures and degenerate
   experiments are also excluded.
2. **Gatekeeping omnibus** across all arms, on the 2 x K table of clicks and non-clicks.
3. **Every ordered pair of arms** is tested against the hypothesis that its risk ratio
   exceeds 1 + threshold &mdash; practical significance as a hypothesis, not a point estimate.
4. **Holm adjustment** across that within-experiment family.
5. **An arm wins only by beating every other arm.** The archive has no control group, so
   beating one nominated reference arm would establish nothing.
"""
)
sh.caveat(
    "Confidence intervals shown throughout are descriptive and unadjusted; the launch gate "
    "is the multiplicity-adjusted test. Power is prospective only &mdash; observed power is a "
    "restatement of the p-value and is never a decision input."
)
