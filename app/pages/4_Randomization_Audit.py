"""Reproduce the evidence that led the archive's authors to the cache glitch."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import _shared as sh

st.set_page_config(
    page_title="Randomization Audit", page_icon=":material/fact_check:", layout="wide"
)
partition = sh.sidebar("Randomization Audit")
p = sh.policy()

st.title("Randomisation audit")
st.markdown(
    f"""
In June 2024 the archive's authors published a critical update: a suspected **Cloudflare
cache misconfiguration between {p.cache_window_start} and {p.cache_window_end}** appears
to have served one variant until the cache expired and then switched, producing something
closer to block randomisation over time than assignment at the individual level. They
found possible issues with about **22%** of tests and discourage causal inference from
that portion.

The update states a flag column was added to the dataset. It was not &mdash; every public
file is still the 2020/2021 vintage and carries no such column. ExperimentGuard therefore
**derives** the flag from the documented window, and validates the derivation by checking
it reproduces the authors' own figure.
"""
)

overall = sh.query(
    """
    SELECT COUNT(*) AS n,
           SUM(CASE WHEN randomization_unreliable THEN 1 ELSE 0 END) AS unreliable
    FROM fct_experiment_decision WHERE partition = ?
    """,
    (partition,),
).iloc[0]
share = overall.unreliable / overall.n

c1, c2, c3 = st.columns(3)
c1.metric("Flagged unreliable", f"{share:.2%}", help=f"{int(overall.unreliable):,} experiments.")
c2.metric("Authors' published figure", "~22%")
c3.metric(
    "Difference",
    f"{abs(share - 0.22) * 100:.1f} pp",
    help="Agreement here is the validation that the derivation is correct.",
)

if abs(share - 0.22) < 0.02:
    st.success(
        "The derived flag reproduces the published figure, which is the evidence that "
        "deriving it from the documented window is the right reconstruction.",
        icon=":material/verified:",
    )

st.divider()

# --- Over time --------------------------------------------------------------
st.subheader("Allocation imbalance over time")
st.caption(
    "Share of experiments each month whose arm impressions deviate sharply from an even "
    "split. The window the authors identified should stand out."
)
monthly = sh.query(
    """
    SELECT date_trunc('month', started_date)                        AS month,
           COUNT(*)                                                 AS n,
           AVG(CASE WHEN srm_pvalue < 0.001 THEN 1.0 ELSE 0.0 END)  AS imbalance_rate,
           AVG(CASE WHEN randomization_unreliable THEN 1.0 ELSE 0.0 END) AS in_window
    FROM fct_experiment_decision WHERE partition = ?
    GROUP BY 1 ORDER BY 1
    """,
    (partition,),
)
monthly["segment"] = (
    monthly["in_window"].gt(0.5).map({True: "Inside the documented window", False: "Outside"})
)

fig = go.Figure()
for label, colour in (
    ("Outside", sh.AUDIT["reliable"]),
    ("Inside the documented window", sh.AUDIT["unreliable"]),
):
    part = monthly[monthly["segment"] == label]
    fig.add_bar(
        name=label,
        x=part["month"],
        y=part["imbalance_rate"],
        marker=dict(color=colour, line=dict(width=0)),
        hovertemplate="%{x|%b %Y}<br>" + label + "<br>imbalanced: %{y:.1%}<extra></extra>",
    )
fig.add_vrect(
    x0=str(p.cache_window_start),
    x1=str(p.cache_window_end),
    fillcolor=sh.AUDIT["unreliable"],
    opacity=0.07,
    line_width=0,
    annotation_text="documented cache window",
    annotation_position="top left",
    annotation_font_color=sh.MUTED,
)
fig.update_layout(
    xaxis_title=None,
    yaxis_title="Share with severe imbalance",
    yaxis_tickformat=".0%",
    barmode="overlay",
)
st.plotly_chart(sh.style_fig(fig, height=380), width="stretch")

st.divider()

# --- By hour ----------------------------------------------------------------
st.subheader("Imbalance by hour of day")
st.caption(
    "A cache that expires on a timer should make imbalance depend on when an experiment "
    "started. Random assignment should show no such pattern. This is the argument the "
    "authors used, reproduced from the data."
)
hourly = sh.query(
    """
    SELECT start_hour,
           AVG(CASE WHEN srm_pvalue < 0.001 THEN 1.0 ELSE 0.0 END) AS imbalance_rate,
           COUNT(*) AS n,
           randomization_unreliable AS in_window
    FROM fct_experiment_decision WHERE partition = ?
    GROUP BY start_hour, randomization_unreliable ORDER BY start_hour
    """,
    (partition,),
)
hf = go.Figure()
for flag, label, colour in (
    (False, "Outside the window", sh.AUDIT["reliable"]),
    (True, "Inside the window", sh.AUDIT["unreliable"]),
):
    part = hourly[hourly["in_window"] == flag]
    hf.add_scatter(
        name=label,
        x=part["start_hour"],
        y=part["imbalance_rate"],
        mode="lines+markers",
        line=dict(color=colour, width=2),
        marker=dict(size=8, color=colour, line=dict(color="#fcfcfb", width=2)),
        hovertemplate="hour %{x}:00<br>" + label + "<br>imbalanced: %{y:.1%}<extra></extra>",
    )
hf.update_layout(
    xaxis_title="Hour the experiment started",
    yaxis_title="Share with severe imbalance",
    yaxis_tickformat=".0%",
    hovermode="x unified",
)
st.plotly_chart(sh.style_fig(hf, height=360), width="stretch")

st.info(
    "**Imbalance is a diagnostic, not a verdict.** Neither the intended allocation nor "
    "each arm's active duration is recorded, so unequal impressions cannot by themselves "
    "prove that randomisation failed — the archive's authors say as much. ExperimentGuard "
    "invalidates on the documented window and reports imbalance alongside it.",
    icon=":material/balance:",
)

st.divider()
st.subheader("Attribution scope")
attr = sh.query(
    """
    SELECT AVG(CASE WHEN attribution_limited THEN 1.0 ELSE 0.0 END) AS rate, COUNT(*) AS n
    FROM fct_experiment_decision WHERE partition = ?
    """,
    (partition,),
).iloc[0]
st.metric("Experiments varying both headline and image", f"{attr.rate:.1%}")
sh.caveat(
    "These carry an ATTRIBUTION_LIMITED warning but remain valid decisions. The randomised "
    "unit is the whole package, so the experiment can still say which package to ship — it "
    "just cannot say whether the headline or the image caused the difference."
)
