"""Browse every experiment and drill into a single one."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import _shared as sh

st.set_page_config(page_title="Experiment Explorer", page_icon=":material/search:", layout="wide")
partition = sh.sidebar("Experiment Explorer")
p = sh.policy()

st.title("Experiment explorer")

f1, f2, f3 = st.columns([2, 1, 1])
search = f1.text_input("Search headlines", placeholder="e.g. Walmart")
decisions = f2.multiselect("Decision", sh.DECISION_ORDER, default=[])
only_eligible = f3.checkbox("Inferentially eligible only", value=False)

where = ["d.partition = ?"]
params: list = [partition]
if decisions:
    where.append(f"d.decision IN ({','.join('?' * len(decisions))})")
    params += decisions
if only_eligible:
    where.append("d.is_inferentially_eligible")
if search:
    where.append("lower(e.reference_headline) LIKE ?")
    params.append(f"%{search.lower()}%")

listing = sh.query(
    f"""
    SELECT d.test_id, e.reference_headline, d.decision, d.n_arms, d.total_impressions,
           d.pooled_ctr, d.mde_relative, d.omnibus_pvalue, d.randomization_unreliable,
           d.attribution_limited, d.started_date
    FROM fct_experiment_decision d
    JOIN dim_experiment e ON e.test_id = d.test_id
    WHERE {" AND ".join(where)}
    ORDER BY d.total_impressions DESC
    LIMIT 500
    """,
    tuple(params),
)

st.caption(f"{len(listing):,} experiments shown (capped at 500). Select a row to drill in.")
event = st.dataframe(
    listing,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "reference_headline": st.column_config.TextColumn(
            "Headline (reference arm)", width="large"
        ),
        "pooled_ctr": st.column_config.NumberColumn("CTR", format="%.3f%%"),
        "mde_relative": st.column_config.NumberColumn("MDE", format="%.1f%%"),
        "omnibus_pvalue": st.column_config.NumberColumn("Omnibus p", format="%.3g"),
        "total_impressions": st.column_config.NumberColumn("Impressions", format="%d"),
        "randomization_unreliable": st.column_config.CheckboxColumn("Unreliable"),
        "attribution_limited": st.column_config.CheckboxColumn("Attr. limited"),
    },
)

rows = event.selection.rows if event and event.selection else []
if not rows:
    st.info("Select an experiment above to see its arms, comparisons and decision.")
    st.stop()

test_id = listing.iloc[rows[0]]["test_id"]
st.divider()

decision = sh.query("SELECT * FROM fct_experiment_decision WHERE test_id = ?", (test_id,)).iloc[0]
arms = sh.query(
    """
    SELECT r.arm_id, a.headline, r.impressions, r.clicks, r.ctr,
           r.impression_share, r.expected_impression_share, a.is_reference_arm
    FROM fct_arm_result r JOIN dim_arm a ON a.arm_id = r.arm_id
    WHERE r.test_id = ? ORDER BY a.created_at, r.arm_id
    """,
    (test_id,),
)

head, verdict = st.columns([3, 1])
head.subheader(decision.get("reference_headline") or test_id)
head.caption(f"`{test_id}` · started {decision.started_date} · {int(decision.n_arms)} arms")
verdict.metric("Decision", decision.decision)

for reason in str(decision.reasons).split(" | "):
    if reason:
        st.markdown(f"- {reason}")

# --- Per-arm CTR with Wilson intervals -------------------------------------
# Single series, so no legend: the title names it. Error bars carry the uncertainty
# that a bare bar would hide.
st.markdown("##### Click-through rate by arm")
arms["label"] = [
    f"Arm {i + 1}" + (" (reference)" if ref else "")
    for i, ref in enumerate(arms["is_reference_arm"])
]
from statsmodels.stats.proportion import proportion_confint  # noqa: E402

lo, hi = proportion_confint(arms["clicks"], arms["impressions"], alpha=0.05, method="wilson")
arms["lo"], arms["hi"] = lo, hi

fig = go.Figure(
    go.Bar(
        x=arms["ctr"] * 100,
        y=arms["label"],
        orientation="h",
        marker=dict(color=sh.BLUE, line=dict(width=0)),
        error_x=dict(
            type="data",
            symmetric=False,
            array=(arms["hi"] - arms["ctr"]) * 100,
            arrayminus=(arms["ctr"] - arms["lo"]) * 100,
            color=sh.MUTED,
            thickness=1.5,
            width=5,
        ),
        text=[f"{v * 100:.2f}%" for v in arms["ctr"]],
        textposition="outside",
        hovertemplate="%{y}<br>CTR %{x:.3f}%<br>%{customdata[0]:,} clicks / "
        "%{customdata[1]:,} impressions<extra></extra>",
        customdata=arms[["clicks", "impressions"]].to_numpy(),
    )
)
fig.update_layout(xaxis_title="CTR (%)", yaxis=dict(autorange="reversed"))
st.plotly_chart(sh.style_fig(fig, height=60 + 42 * len(arms), legend=False), width="stretch")
sh.caveat(
    "Bars show 95% Wilson intervals per arm. The reference arm is the earliest-created "
    "arm and exists only to orient this chart — it is not a control and no decision "
    "depends on it."
)

# --- Pairwise comparison matrix --------------------------------------------
st.markdown("##### Does any arm beat every other arm?")
comparisons = sh.query(
    """
    SELECT treatment_arm_id, reference_arm_id, risk_ratio, rr_lo_descriptive,
           rr_hi_descriptive, p_adjusted, rejected, rr_estimable, note
    FROM fct_arm_comparison WHERE test_id = ?
    """,
    (test_id,),
)
labels = dict(zip(arms["arm_id"], arms["label"], strict=True))
if comparisons.empty:
    st.info("No pairwise comparisons: this experiment was invalid, so testing was skipped.")
else:
    comparisons["Treatment"] = comparisons["treatment_arm_id"].map(labels)
    comparisons["Beaten arm"] = comparisons["reference_arm_id"].map(labels)
    wins = (
        comparisons.groupby("Treatment")
        .agg(beats=("rejected", "sum"), of=("rejected", "size"))
        .reset_index()
    )
    wins["Beats all others"] = wins["beats"] == wins["of"]
    st.dataframe(
        wins.rename(columns={"beats": "Arms beaten", "of": "Comparisons"}),
        hide_index=True,
        width="stretch",
    )
    with st.expander("All ordered comparisons"):
        st.dataframe(
            comparisons[
                [
                    "Treatment",
                    "Beaten arm",
                    "risk_ratio",
                    "rr_lo_descriptive",
                    "rr_hi_descriptive",
                    "p_adjusted",
                    "rejected",
                    "rr_estimable",
                    "note",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "risk_ratio": st.column_config.NumberColumn("RR", format="%.3f"),
                "rr_lo_descriptive": st.column_config.NumberColumn(
                    "RR low (descr.)", format="%.3f"
                ),
                "rr_hi_descriptive": st.column_config.NumberColumn(
                    "RR high (descr.)", format="%.3f"
                ),
                "p_adjusted": st.column_config.NumberColumn("p (Holm)", format="%.4f"),
            },
        )
    sh.caveat(
        f"A launch requires one arm to beat **all** {int(decision.n_arms) - 1} others at "
        f"RR > {p.launch_ratio:.2f} after Holm adjustment. Intervals here are descriptive "
        "and unadjusted; the gate is the adjusted test."
    )

# --- Power ------------------------------------------------------------------
st.markdown("##### What could this experiment have detected?")
pw = pd.DataFrame(
    {
        "lift": ["5%", "10%", "20%", "50%"],
        "power": [
            decision.power_at_5pct,
            decision.power_at_10pct,
            decision.power_at_20pct,
            decision.power_at_50pct,
        ],
    }
)
pf = go.Figure(
    go.Bar(
        x=pw["lift"],
        y=pw["power"],
        marker=dict(color=sh.BLUE, line=dict(width=0)),
        text=[sh.pct(v, 0) for v in pw["power"]],
        textposition="outside",
        hovertemplate="%{x} relative lift<br>power %{y:.1%}<extra></extra>",
    )
)
pf.add_hline(
    y=0.8,
    line=dict(color=sh.MUTED, width=1, dash="dot"),
    annotation_text="80% power",
    annotation_font_color=sh.MUTED,
)
pf.update_layout(
    yaxis_title="Prospective power", yaxis_range=[0, 1.05], xaxis_title="Relative lift"
)
st.plotly_chart(sh.style_fig(pf, height=300, legend=False), width="stretch")
sh.caveat(
    "Prospective power at prespecified lifts, computed from this experiment's sample size. "
    "Observed (post-hoc) power is deliberately absent — it restates the p-value."
)

st.session_state["selected_test_id"] = test_id
st.page_link(
    "pages/5_Decision_Report.py",
    label="Generate a decision report for this experiment",
    icon=":material/description:",
)
