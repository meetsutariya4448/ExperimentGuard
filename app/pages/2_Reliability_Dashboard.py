"""Archive-wide reliability: decision mix, detectable effects, and correction attrition."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import _shared as sh

st.set_page_config(
    page_title="Reliability Dashboard", page_icon=":material/monitoring:", layout="wide"
)
partition = sh.sidebar("Reliability Dashboard")
p = sh.policy()

st.title("Reliability dashboard")

stats = sh.query(
    """
    SELECT decision, is_inferentially_eligible, randomization_unreliable, attribution_limited,
           mde_relative, power_at_5pct, power_at_10pct, power_at_20pct, power_at_50pct,
           srm_pvalue, omnibus_pvalue, bayes_prob_exceeds, n_arms, total_impressions
    FROM fct_experiment_decision WHERE partition = ?
    """,
    (partition,),
)
n = len(stats)
eligible = stats[stats.is_inferentially_eligible]

# --- Decision mix -----------------------------------------------------------
# One hue: the decision is already on the axis, so colouring by decision would be
# redundant encoding. The semantically tempting green/orange/red set also fails CVD
# separation (red vs orange measures dE 7.1, under the 15 floor).
st.subheader("Decision mix")
mix = (
    stats["decision"].value_counts().reindex(sh.DECISION_ORDER).fillna(0).astype(int).reset_index()
)
mix.columns = ["decision", "count"]
mix["share"] = mix["count"] / n

fig = go.Figure(
    go.Bar(
        x=mix["count"],
        y=mix["decision"],
        orientation="h",
        marker=dict(color=sh.BLUE, line=dict(width=0)),
        text=[f"{c:,}  ({s:.1%})" for c, s in zip(mix["count"], mix["share"], strict=True)],
        textposition="outside",
        hovertemplate="%{y}<br>%{x:,} experiments<extra></extra>",
    )
)
fig.update_layout(xaxis_title="Experiments", yaxis=dict(autorange="reversed"))
fig.update_xaxes(range=[0, mix["count"].max() * 1.25])
st.plotly_chart(sh.style_fig(fig, height=260, legend=False), width="stretch")

cols = st.columns(4)
for col, row in zip(cols, mix.itertuples(), strict=True):
    col.metric(row.decision, f"{row.share:.1%}", help=sh.DECISION_HELP[row.decision])

st.divider()
left, right = st.columns(2)

# --- MDE distribution -------------------------------------------------------
with left:
    st.subheader("Smallest detectable lift")
    mde = eligible["mde_relative"].replace([np.inf, -np.inf], np.nan).dropna()
    mde = mde[mde < 3.0]  # a handful of tiny experiments run off the scale
    median_mde = float(np.median(mde)) if len(mde) else float("nan")

    h = go.Figure(
        go.Histogram(
            x=mde * 100,
            nbinsx=50,
            marker=dict(color=sh.BLUE, line=dict(width=0)),
            hovertemplate="MDE %{x:.0f}%<br>%{y:,} experiments<extra></extra>",
        )
    )
    h.add_vline(
        x=median_mde * 100,
        line=dict(color=sh.INK, width=2),
        annotation_text=f"median {median_mde:.0%}",
        annotation_font_color=sh.INK,
    )
    h.add_vline(
        x=10,
        line=dict(color=sh.MUTED, width=1, dash="dot"),
        annotation_text="a 10% lift",
        annotation_font_color=sh.MUTED,
    )
    h.update_layout(xaxis_title="Minimum detectable relative lift (%)", yaxis_title="Experiments")
    st.plotly_chart(sh.style_fig(h, legend=False), width="stretch")
    sh.caveat(
        "The dotted line marks a 10% relative lift — a realistic target for a product "
        "change. Almost the entire distribution sits to its right, meaning these "
        "experiments could not have resolved an effect that size."
    )

# --- Share adequately powered ----------------------------------------------
with right:
    st.subheader("Share powered to detect a given lift")
    lifts = [
        ("5%", "power_at_5pct"),
        ("10%", "power_at_10pct"),
        ("20%", "power_at_20pct"),
        ("50%", "power_at_50pct"),
    ]
    shares = [float((eligible[c] >= 0.8).mean()) for _, c in lifts]

    b = go.Figure(
        go.Bar(
            x=[label for label, _ in lifts],
            y=shares,
            marker=dict(color=sh.BLUE, line=dict(width=0)),
            text=[f"{s:.1%}" for s in shares],
            textposition="outside",
            hovertemplate="%{x} relative lift<br>%{y:.1%} of experiments have 80% power"
            "<extra></extra>",
        )
    )
    b.update_layout(
        xaxis_title="Relative lift",
        yaxis_title="Share with 80% power",
        yaxis_tickformat=".0%",
        yaxis_range=[0, max(shares + [0.1]) * 1.3],
    )
    st.plotly_chart(sh.style_fig(b, legend=False), width="stretch")
    sh.caveat(
        "Prospective power at prespecified lifts. Only experiments eligible for "
        "inference are counted."
    )

st.divider()

# --- Multiplicity attrition -------------------------------------------------
st.subheader("What multiplicity correction costs")
comp = sh.query(
    """
    SELECT COUNT(*) FILTER (WHERE p_value_unadjusted < 0.05) AS raw,
           COUNT(*) FILTER (WHERE rejected)                   AS holm,
           COUNT(*)                                           AS total
    FROM fct_arm_comparison WHERE partition = ?
    """,
    (partition,),
).iloc[0]

c1, c2, c3 = st.columns(3)
c1.metric("Ordered comparisons", f"{int(comp.total):,}")
c2.metric(
    "Significant unadjusted",
    f"{int(comp.raw):,}",
    help="p < 0.05 on the threshold test, before any correction.",
)
c3.metric(
    "Survive Holm",
    f"{int(comp.holm):,}",
    delta=f"{int(comp.holm) - int(comp.raw):,}",
    help="Holm-adjusted within each experiment's own family of comparisons.",
)
sh.caveat(
    "The decision family is the set of comparisons within one experiment, which is the "
    "family that matches the question 'should we ship this experiment's winner?'. An "
    "archive-wide FDR view is available on the policy comparison page as a research lens, "
    "but it is not the basis for any individual launch."
)

st.divider()

# --- Frequentist vs Bayesian ------------------------------------------------
st.subheader("Frequentist and Bayesian agreement")
launched = eligible[eligible["decision"] == "LAUNCH"].dropna(subset=["bayes_prob_exceeds"])
if launched.empty:
    st.info("No launches in this partition, so there is nothing to cross-check.")
else:
    disagree = float((launched["bayes_prob_exceeds"] < 0.95).mean())
    s = go.Figure(
        go.Histogram(
            x=launched["bayes_prob_exceeds"],
            nbinsx=40,
            marker=dict(color=sh.BLUE, line=dict(width=0)),
            hovertemplate="P(RR > threshold) %{x:.2f}<br>%{y:,} launches<extra></extra>",
        )
    )
    s.add_vline(
        x=0.95,
        line=dict(color=sh.INK, width=2),
        annotation_text="0.95",
        annotation_font_color=sh.INK,
    )
    s.update_layout(
        xaxis_title="Posterior P(RR > threshold) for the winning arm", yaxis_title="Launches"
    )
    st.plotly_chart(sh.style_fig(s, legend=False), width="stretch")
    st.metric("Launches where the posterior is below 0.95", f"{disagree:.1%}")
    sh.caveat(
        "The Bayesian result is a cross-check and never a gate. Beta(1,1) priors; the "
        "posterior probability is computed by bounded quadrature over the reference "
        "posterior's support, validated against a 2,000,000-draw Monte Carlo."
    )
