"""Downloadable decision reports, separating the governed decision from what-ifs."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import _shared as sh
from experimentguard import report as rp  # noqa: E402
from experimentguard.decision import evaluate_experiment  # noqa: E402
from experimentguard.stats.frequentist import arm_stat  # noqa: E402

st.set_page_config(page_title="Decision Report", page_icon=":material/description:", layout="wide")
partition = sh.sidebar("Decision Report")
p = sh.policy()

sh.page_header(
    "Decision report",
    "Governed exports",
    "Generate an auditable record for one experiment or export the complete decision set "
    "for the selected partition.",
)

tab_single, tab_bulk = st.tabs(["One experiment", "Whole partition"])

with tab_single:
    ids = sh.query(
        "SELECT test_id FROM fct_experiment_decision WHERE partition = ? "
        "ORDER BY total_impressions DESC LIMIT 400",
        (partition,),
    )["test_id"].tolist()
    default = st.session_state.get("selected_test_id")
    index = ids.index(default) if default in ids else 0
    test_id = st.selectbox("Experiment", ids, index=index)

    row = sh.query("SELECT * FROM fct_experiment_decision WHERE test_id = ?", (test_id,)).iloc[0]
    arms = sh.query(
        """
        SELECT r.arm_id, r.impressions, r.clicks, r.ctr, a.is_reference_arm, a.created_at,
               a.headline, a.eyecatcher_id
        FROM fct_arm_result r JOIN dim_arm a ON a.arm_id = r.arm_id
        WHERE r.test_id = ? ORDER BY a.created_at, r.arm_id
        """,
        (test_id,),
    )

    st.markdown("##### Official decision")
    st.markdown(f"### {row.decision}")
    for reason in str(row.reasons).split(" | "):
        if reason:
            st.markdown(f"- {reason}")

    st.markdown("##### Explore a different threshold")
    st.caption(
        "This produces a scenario, clearly separated from the official decision above. "
        "It never replaces the frozen policy."
    )
    theta = st.slider(
        "Practical significance threshold (relative lift)",
        0.0,
        0.50,
        float(p.practical_threshold),
        0.01,
        format="%.2f",
    )

    scenario_decision = None
    if abs(theta - p.practical_threshold) > 1e-9:
        scenario_policy = p.scenario(practical_threshold=theta)
        result = evaluate_experiment(
            test_id,
            arms["arm_id"].tolist(),
            arms["clicks"].to_numpy(float),
            arms["impressions"].to_numpy(float),
            arms["created_at"].iloc[0],
            scenario_policy,
            reference_arm_id=arms.loc[arms.is_reference_arm, "arm_id"].iloc[0],
            n_distinct_headlines=int(arms["headline"].nunique(dropna=True)),
            n_distinct_eyecatchers=int(arms["eyecatcher_id"].nunique(dropna=True)),
        )
        scenario_decision = str(result.decision)
        c1, c2 = st.columns(2)
        c1.metric("Official (frozen)", row.decision, help=f"threshold {p.practical_threshold:.0%}")
        c2.metric("Scenario", scenario_decision, help=f"threshold {theta:.0%}")
        if scenario_decision != row.decision:
            st.warning(
                f"At a {theta:.0%} threshold this experiment would read "
                f"**{scenario_decision}**, against the official **{row.decision}**. "
                "The official decision is unchanged.",
                icon=":material/science:",
            )
    else:
        scenario_policy = p

    arm_rows = []
    for i, a in enumerate(arms.itertuples()):
        s = arm_stat(int(a.clicks), int(a.impressions))
        arm_rows.append(
            {
                "label": f"Arm {i + 1}" + (" (reference)" if a.is_reference_arm else ""),
                "impressions": int(a.impressions),
                "clicks": int(a.clicks),
                "ctr": s.ctr,
                "ctr_lo": s.ctr_lo,
                "ctr_hi": s.ctr_hi,
                "role": "reference (display only)" if a.is_reference_arm else "challenger",
            }
        )

    html = rp.render_html(
        policy=p,
        test_id=test_id,
        official=str(row.decision),
        reasons=[r for r in str(row.reasons).split(" | ") if r],
        arms=arm_rows,
        summary_rows=rp.summary_rows_from(row),
        scenario=scenario_decision,
        scenario_policy=scenario_policy,
    )

    d1, d2, d3 = st.columns(3)
    d1.download_button(
        "Download HTML",
        html,
        file_name=f"experimentguard_{test_id}.html",
        mime="text/html",
        width="stretch",
    )
    d2.download_button(
        "Download CSV",
        rp.to_csv(pd.DataFrame([row])),
        file_name=f"experimentguard_{test_id}.csv",
        mime="text/csv",
        width="stretch",
    )
    d3.download_button(
        "Download JSON",
        rp.to_json(pd.DataFrame([row]), p),
        file_name=f"experimentguard_{test_id}.json",
        mime="application/json",
        width="stretch",
    )

    with st.expander("Preview the HTML report"):
        # components.v1.html renders inside an iframe, which is what keeps the
        # report's own stylesheet from leaking into the app. st.html does not
        # sandbox, and st.iframe takes a URL rather than a document body, so
        # neither is a substitute here despite the deprecation notice.
        st.components.v1.html(html, height=620, scrolling=True)

with tab_bulk:
    st.markdown(f"Every decision in **{partition}**, with the reasons that produced it.")
    bulk = sh.query(
        "SELECT * FROM fct_experiment_decision WHERE partition = ? ORDER BY total_impressions DESC",
        (partition,),
    )
    st.caption(f"{len(bulk):,} experiments.")
    st.dataframe(bulk.head(200), hide_index=True, width="stretch")

    mix = bulk["decision"].value_counts().reindex(sh.DECISION_ORDER).fillna(0).astype(int)
    summary_html = rp.render_html(
        policy=p,
        test_id=f"{partition} partition",
        summary_rows=[
            ("Experiments", f"{len(bulk):,}"),
            *[(f"Decision: {k}", f"{v:,} ({v / len(bulk):.1%})") for k, v in mix.items()],
            ("Unreliable randomisation", f"{bulk.randomization_unreliable.mean():.1%}"),
            (
                "Median MDE (eligible)",
                sh.pct(bulk.loc[bulk.is_inferentially_eligible, "mde_relative"].median()),
            ),
        ],
    )
    b1, b2, b3 = st.columns(3)
    b1.download_button(
        "Download summary HTML",
        summary_html,
        file_name=f"experimentguard_{partition}_summary.html",
        mime="text/html",
        width="stretch",
    )
    b2.download_button(
        "Download all decisions (CSV)",
        rp.to_csv(bulk),
        file_name=f"experimentguard_{partition}_decisions.csv",
        mime="text/csv",
        width="stretch",
    )
    b3.download_button(
        "Download all decisions (JSON)",
        rp.to_json(bulk, p),
        file_name=f"experimentguard_{partition}_decisions.json",
        mime="application/json",
        width="stretch",
    )
