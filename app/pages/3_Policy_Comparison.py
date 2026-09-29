"""Four selection policies, compared honestly - including when they decline to choose."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import _shared as sh

st.set_page_config(
    page_title="Policy Comparison", page_icon=":material/compare_arrows:", layout="wide"
)
partition = sh.sidebar("Policy Comparison")
p = sh.policy()

POLICY_LABEL = {
    "naive_argmax_ctr": "Naive (highest CTR)",
    "recorded_first_place": "Archive first_place",
    "editor_winner": "Archive winner (editor)",
    "experimentguard": "ExperimentGuard",
}
STATUS_ORDER = ["ONE", "NONE", "MULTIPLE"]

sh.page_header(
    "Policy comparison",
    "Decision behavior",
    "Compare naive winner selection, archive editorial signals, and the governed "
    "ExperimentGuard policy on the same experiments.",
)
st.markdown(
    "The archive records two of its own selection signals. `first_place` was information "
    "shown to editors; `winner` was what editors ultimately chose. Neither is documented "
    "as an automatic highest-CTR rule, so the naive rule is **computed here** from the "
    "observed rates rather than read from the data, and all four policies are compared "
    "separately."
)

sel = sh.query(
    """
    SELECT policy, selection_status, COUNT(*) AS n
    FROM fct_policy_comparison WHERE partition = ?
    GROUP BY policy, selection_status
    """,
    (partition,),
)
total = sh.query(
    "SELECT COUNT(DISTINCT test_id) AS n FROM fct_policy_comparison WHERE partition = ?",
    (partition,),
).iloc[0]["n"]

st.subheader("Does the policy select at all?")
pivot = (
    sel.pivot(index="policy", columns="selection_status", values="n")
    .reindex(list(POLICY_LABEL))
    .reindex(columns=STATUS_ORDER)
    .fillna(0)
)

# Three series -> categorical slots 1-3, validated on the adjacent pairlist in both
# modes. Legend present, and every segment is directly labelled, so identity is never
# carried by colour alone.
fig = go.Figure()
for i, status in enumerate(STATUS_ORDER):
    fig.add_bar(
        name=status,
        y=[POLICY_LABEL[k] for k in pivot.index],
        x=pivot[status],
        orientation="h",
        marker=dict(color=sh.CATEGORICAL[i], line=dict(color="#fcfcfb", width=2)),
        text=[f"{int(v):,}" if v / total > 0.04 else "" for v in pivot[status]],
        textposition="inside",
        insidetextfont=dict(color="white"),
        hovertemplate="%{y}<br>" + status + ": %{x:,} experiments<extra></extra>",
    )
fig.update_layout(barmode="stack", xaxis_title="Experiments", yaxis=dict(autorange="reversed"))
st.plotly_chart(sh.style_fig(fig, height=300), width="stretch")
sh.caveat(
    "ONE means the policy chose exactly one arm; NONE means it declined; MULTIPLE means "
    "it tied. The archive's own `winner` column is NONE for roughly three quarters of "
    "experiments — forcing a winner there would fabricate decisions that were never made."
)

st.divider()
st.subheader("Where the naive rule and ExperimentGuard part ways")

cross = sh.query(
    """
    WITH naive AS (
        SELECT test_id, selection_status, selected_arm_id
        FROM fct_policy_comparison
        WHERE partition = ? AND policy = 'naive_argmax_ctr'
    )
    SELECT n.selection_status AS naive_status, d.decision,
           COUNT(*) AS n,
           SUM(CASE WHEN n.selected_arm_id = d.selected_arm_id THEN 1 ELSE 0 END) AS same_arm
    FROM naive n
    JOIN fct_experiment_decision d ON d.test_id = n.test_id
    GROUP BY 1, 2
    """,
    (partition,),
)

naive_picked = int(cross[cross.naive_status == "ONE"]["n"].sum())
naive_and_launch = int(
    cross[(cross.naive_status == "ONE") & (cross.decision == "LAUNCH")]["n"].sum()
)
insufficient = naive_picked - naive_and_launch

c1, c2, c3 = st.columns(3)
c1.metric(
    "Naive picks a winner",
    f"{naive_picked / total:.1%}",
    help=f"{naive_picked:,} of {int(total):,} experiments.",
)
c2.metric(
    "ExperimentGuard launches",
    f"{naive_and_launch / total:.1%}",
    help="Of the same experiments, those that also clear the reliability policy.",
)
c3.metric(
    "Lacked sufficient evidence",
    f"{insufficient / max(naive_picked, 1):.1%}",
    help="Share of naive selections that the reliability policy would not launch.",
)

st.warning(
    f"**{insufficient / max(naive_picked, 1):.1%} of naive selections lacked sufficient "
    "statistical evidence under this policy.** That is a statement about evidence, not "
    "about truth: these experiments did not establish a worthwhile winner, which is not "
    "the same as establishing that no winner exists.",
    icon=":material/warning:",
)

matrix = (
    cross[cross.naive_status == "ONE"]
    .set_index("decision")["n"]
    .reindex(sh.DECISION_ORDER)
    .fillna(0)
    .astype(int)
)
mf = go.Figure(
    go.Bar(
        x=matrix.values,
        y=matrix.index,
        orientation="h",
        marker=dict(color=sh.BLUE, line=dict(width=0)),
        text=[f"{v:,}" for v in matrix.values],
        textposition="outside",
        hovertemplate="Naive picked a winner; ExperimentGuard says %{y}<br>"
        "%{x:,} experiments<extra></extra>",
    )
)
mf.update_layout(
    xaxis_title="Experiments where the naive rule picked a winner", yaxis=dict(autorange="reversed")
)
mf.update_xaxes(range=[0, matrix.max() * 1.2])
st.plotly_chart(sh.style_fig(mf, height=260, legend=False), width="stretch")

st.divider()
st.subheader("Agreement between policies")
st.caption(
    "Computed only over experiments where **both** policies selected exactly one arm. "
    "The denominator is printed so the rate cannot be read out of context."
)

pairs = [
    ("naive_argmax_ctr", "recorded_first_place"),
    ("naive_argmax_ctr", "editor_winner"),
    ("recorded_first_place", "editor_winner"),
    ("naive_argmax_ctr", "experimentguard"),
]
rows = []
for a, b in pairs:
    r = sh.query(
        """
        WITH l AS (SELECT test_id, selected_arm_id FROM fct_policy_comparison
                   WHERE partition = ? AND policy = ? AND selection_status = 'ONE'),
             r AS (SELECT test_id, selected_arm_id FROM fct_policy_comparison
                   WHERE partition = ? AND policy = ? AND selection_status = 'ONE')
        SELECT COUNT(*) AS denominator,
               SUM(CASE WHEN l.selected_arm_id = r.selected_arm_id THEN 1 ELSE 0 END) AS agreed
        FROM l JOIN r USING (test_id)
        """,
        (partition, a, partition, b),
    ).iloc[0]
    denom = int(r.denominator)
    rows.append(
        {
            "Policy A": POLICY_LABEL[a],
            "Policy B": POLICY_LABEL[b],
            "Both chose one arm": denom,
            "Agreed": int(r.agreed),
            "Agreement": (r.agreed / denom) if denom else float("nan"),
            "Excluded (no single selection)": int(total) - denom,
        }
    )
st.dataframe(
    rows,
    hide_index=True,
    width="stretch",
    column_config={"Agreement": st.column_config.NumberColumn(format="%.1f%%")},
)
