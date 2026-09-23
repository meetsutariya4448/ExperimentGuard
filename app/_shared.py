"""Shared data access, palette and formatting for the ExperimentGuard app.

Palette note: every multi-series set below was checked with the dataviz validator in
both light and dark modes rather than chosen by eye.

* Decision mix is drawn as a **single hue** with the decision on the axis. Colouring
  four decision states by hue would be redundant encoding, and the semantically
  obvious green/orange/red set fails CVD separation (red vs orange measures
  Delta E 7.1, well under the 15 floor).
* Policy comparison uses canonical categorical slots 1-4, which pass every gate in
  both modes on the adjacent pairlist.
* The randomisation audit uses blue vs red, which passes in both modes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from experimentguard.config import DUCKDB_PATH, load_frozen_policy, policy_checksum  # noqa: E402

DECISION_ORDER = ["LAUNCH", "CONTINUE", "NO_MEANINGFUL_WIN", "INVALID"]

# Single sequential hue (blue) for one-series charts.
BLUE = "#2a78d6"
BLUE_LIGHT = "#9ec5f4"
# Canonical categorical slots 1-4 - validated on the adjacent pairlist, both modes.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
# Two-series audit palette.
AUDIT = {"reliable": "#2a78d6", "unreliable": "#d03b3b"}
INK = "#1a1a18"
MUTED = "#6b6b64"
GRID = "#e8e8e3"

DECISION_HELP = {
    "LAUNCH": "One arm beat every other arm by more than the threshold, after "
    "multiplicity adjustment within the experiment.",
    "CONTINUE": "Still compatible with a worthwhile effect. Not evidence of no effect - "
    "more sample is needed to decide.",
    "NO_MEANINGFUL_WIN": "A worthwhile win is ruled out by the descriptive bounds.",
    "INVALID": "Cannot support causal inference - the documented randomisation window, "
    "an integrity failure, or too few usable arms.",
}


@st.cache_resource
def _connection():
    if not DUCKDB_PATH.exists():
        st.error(f"No warehouse at {DUCKDB_PATH}. Run `make ingest && make analyze` first.")
        st.stop()
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


@st.cache_data(ttl=600)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return _connection().execute(sql, list(params)).df()


@st.cache_data(ttl=600)
def available_partitions() -> list[str]:
    try:
        df = query("SELECT DISTINCT partition FROM fct_experiment_decision ORDER BY 1")
    except duckdb.Error:
        return []
    return df["partition"].tolist()


def policy():
    return load_frozen_policy()


def sidebar(page: str) -> str:
    """Shared sidebar. Returns the selected partition."""
    p = policy()
    st.sidebar.title("ExperimentGuard")
    st.sidebar.caption(page)

    parts = available_partitions()
    if not parts:
        st.sidebar.error("No analysis tables. Run `make analyze`.")
        st.stop()

    default = parts.index("exploratory") if "exploratory" in parts else 0
    partition = st.sidebar.selectbox("Partition", parts, index=default)
    if partition == "holdout":
        st.sidebar.warning(
            "Holdout is once-only evidence. Treat anything read here as final.",
            icon=":material/lock:",
        )

    st.sidebar.divider()
    st.sidebar.markdown("**Frozen policy**")
    st.sidebar.markdown(
        f"- version `{p.policy_version}`\n"
        f"- threshold **{p.practical_threshold:.0%}** relative lift\n"
        f"- **{p.multiplicity_method}** within experiment\n"
        f"- checksum `{policy_checksum()[:12]}…`"
    )
    st.sidebar.caption(
        "Official decisions come from this frozen contract. Any threshold you change "
        "on a page produces a clearly-labelled scenario, never the official result."
    )
    return partition


def style_fig(fig, *, height: int = 360, legend: bool = True):
    """Recessive axes, generous margins, tabular numerals in hover."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif",
            size=13,
            color=INK,
        ),
        hoverlabel=dict(font_size=13, bgcolor="white", bordercolor=GRID),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        bargap=0.28,
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        linecolor=GRID,
        ticks="outside",
        tickcolor=GRID,
        title_font_color=MUTED,
        tickfont_color=MUTED,
    )
    fig.update_yaxes(
        gridcolor=GRID,
        zeroline=False,
        linecolor="rgba(0,0,0,0)",
        title_font_color=MUTED,
        tickfont_color=MUTED,
    )
    return fig


def pct(value, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def caveat(text: str) -> None:
    st.caption(f":material/info: {text}")
