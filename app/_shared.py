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
from html import escape
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

NAV_ITEMS = (
    ("/", "Overview", "dashboard", "Overview"),
    ("/Experiment_Explorer", "Experiment explorer", "search", "Experiment Explorer"),
    ("/Reliability_Dashboard", "Reliability dashboard", "monitoring", "Reliability Dashboard"),
    ("/Policy_Comparison", "Policy comparison", "compare_arrows", "Policy Comparison"),
    ("/Randomization_Audit", "Randomisation audit", "fact_check", "Randomization Audit"),
    ("/Decision_Report", "Decision report", "description", "Decision Report"),
)

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


def inject_styles() -> None:
    """Apply the product shell and responsive visual system on every page."""
    st.html(
        """
        <style>
        :root {
            --eg-ink: #172126;
            --eg-muted: #617078;
            --eg-border: #dbe3e7;
            --eg-surface: #ffffff;
            --eg-canvas: #f6f8f9;
            --eg-sidebar: #142126;
            --eg-sidebar-soft: #203238;
            --eg-teal: #0f766e;
            --eg-teal-bright: #2dd4bf;
            --eg-amber: #b7791f;
            --eg-red: #bd3f3a;
        }

        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial,
                sans-serif;
        }

        .stApp, [data-testid="stAppViewContainer"] {
            background: var(--eg-canvas);
            color: var(--eg-ink);
        }

        [data-testid="stHeader"] {
            background: transparent;
            height: 2.5rem;
        }

        [data-testid="stDecoration"], [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .block-container {
            max-width: 1360px;
            padding: 3.25rem 3rem 5rem;
        }

        h1, h2, h3, h4, h5, h6 {
            color: var(--eg-ink);
            letter-spacing: 0;
        }

        h2 {
            font-size: 1.45rem !important;
            line-height: 1.3 !important;
            margin-top: 0.5rem !important;
        }

        h3 {
            font-size: 1.12rem !important;
            line-height: 1.35 !important;
        }

        p, li {
            line-height: 1.65;
        }

        hr {
            border-color: var(--eg-border) !important;
            margin: 2.25rem 0 !important;
        }

        .eg-page-header {
            max-width: 920px;
            margin: 0 0 1.75rem;
        }

        .eg-eyebrow {
            color: var(--eg-teal);
            font-size: 0.74rem;
            font-weight: 750;
            letter-spacing: 0.08em;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
        }

        .eg-page-title {
            color: var(--eg-ink);
            font-size: clamp(2rem, 3vw, 2.75rem);
            font-weight: 760;
            letter-spacing: 0;
            line-height: 1.08;
            margin: 0;
        }

        .eg-page-deck {
            color: var(--eg-muted);
            font-size: 1.02rem;
            line-height: 1.62;
            margin: 0.75rem 0 0;
            max-width: 820px;
        }

        div[data-testid="stMetric"] {
            background: var(--eg-surface);
            border: 1px solid var(--eg-border);
            border-top: 3px solid var(--eg-teal);
            border-radius: 6px;
            box-shadow: 0 1px 2px rgba(18, 33, 38, 0.04);
            min-height: 108px;
            padding: 0.9rem 1rem 0.8rem;
        }

        [data-testid="stMetricLabel"] {
            color: var(--eg-muted);
            font-size: 0.73rem;
            font-weight: 700;
            letter-spacing: 0.045em;
            text-transform: uppercase;
        }

        [data-testid="stMetricValue"] {
            color: var(--eg-ink);
            font-size: 1.85rem;
            font-variant-numeric: tabular-nums;
            font-weight: 700;
            letter-spacing: 0;
        }

        [data-testid="stMetricDelta"] {
            font-size: 0.76rem;
        }

        [data-testid="stPlotlyChart"] {
            background: var(--eg-surface);
            border: 1px solid var(--eg-border);
            border-radius: 6px;
            box-shadow: 0 1px 2px rgba(18, 33, 38, 0.03);
            padding: 0.55rem 0.65rem 0.25rem;
        }

        [data-testid="stDataFrame"] {
            background: var(--eg-surface);
            border: 1px solid var(--eg-border);
            border-radius: 6px;
            overflow: hidden;
        }

        [data-testid="stAlert"] {
            border-radius: 6px;
            border-width: 1px;
            box-shadow: none;
        }

        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-baseweb="textarea"] > div {
            background: var(--eg-surface);
            border-color: var(--eg-border);
            border-radius: 6px;
            box-shadow: none;
        }

        [data-baseweb="tab-list"] {
            background: #e8edef;
            border-radius: 6px;
            gap: 0.2rem;
            padding: 0.25rem;
            width: fit-content;
        }

        [data-baseweb="tab"] {
            border-radius: 4px;
            color: var(--eg-muted);
            font-weight: 650;
            padding: 0.45rem 0.9rem;
        }

        [aria-selected="true"][data-baseweb="tab"] {
            background: var(--eg-surface);
            color: var(--eg-ink);
            box-shadow: 0 1px 2px rgba(18, 33, 38, 0.08);
        }

        [data-testid="stDownloadButton"] button,
        [data-testid="stLinkButton"] a {
            border-color: var(--eg-border);
            border-radius: 6px;
            font-weight: 650;
            min-height: 2.65rem;
        }

        [data-testid="stDownloadButton"] button:hover,
        [data-testid="stLinkButton"] a:hover {
            border-color: var(--eg-teal);
            color: var(--eg-teal);
        }

        .eg-decision-list {
            border-top: 1px solid var(--eg-border);
        }

        .eg-decision-row {
            align-items: flex-start;
            border-bottom: 1px solid var(--eg-border);
            display: grid;
            gap: 0.85rem;
            grid-template-columns: 10px 145px 1fr;
            padding: 0.8rem 0;
        }

        .eg-decision-dot {
            border-radius: 50%;
            height: 8px;
            margin-top: 0.5rem;
            width: 8px;
        }

        .eg-decision-name {
            color: var(--eg-ink);
            font-size: 0.78rem;
            font-weight: 760;
            line-height: 1.5;
        }

        .eg-decision-copy {
            color: var(--eg-muted);
            font-size: 0.86rem;
            line-height: 1.55;
        }

        section[data-testid="stSidebar"] {
            background: var(--eg-sidebar);
            border-right: 1px solid #25383e;
            color: #eaf0f2;
        }

        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding: 1.35rem 0.8rem 1.5rem;
        }

        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] small {
            color: #d6e0e3;
        }

        .eg-brand {
            align-items: center;
            display: flex;
            gap: 0.75rem;
            margin: 0.15rem 0.35rem 1.5rem;
        }

        .eg-brand-mark {
            align-items: center;
            background: var(--eg-teal-bright);
            border-radius: 6px;
            color: #102126;
            display: flex;
            font-size: 0.74rem;
            font-weight: 850;
            height: 34px;
            justify-content: center;
            width: 34px;
        }

        .eg-brand-name {
            color: #ffffff;
            font-size: 1rem;
            font-weight: 760;
            line-height: 1.2;
        }

        .eg-brand-tagline {
            color: #94a6ac;
            font-size: 0.7rem;
            line-height: 1.3;
            margin-top: 0.18rem;
        }

        .eg-sidebar-label {
            color: #80959c;
            font-size: 0.64rem;
            font-weight: 760;
            letter-spacing: 0.09em;
            margin: 1.25rem 0.45rem 0.45rem;
            text-transform: uppercase;
        }

        .eg-nav-link {
            align-items: center;
            border-left: 3px solid transparent;
            border-radius: 5px;
            color: #c9d5d8;
            display: flex;
            font-size: 0.84rem;
            font-weight: 590;
            gap: 0.65rem;
            margin: 0.08rem 0;
            padding: 0.52rem 0.65rem;
            text-decoration: none !important;
        }

        .eg-nav-link:hover {
            background: var(--eg-sidebar-soft);
            color: #ffffff;
        }

        .eg-nav-link.active {
            background: #263d44;
            border-left-color: var(--eg-teal-bright);
            color: #ffffff;
        }

        .eg-nav-icon {
            color: inherit;
            font-family: "Material Symbols Rounded";
            font-size: 1.05rem;
            font-weight: normal;
            line-height: 1;
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background: var(--eg-sidebar-soft);
            border-color: #40545b;
            color: #ffffff;
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] svg,
        section[data-testid="stSidebar"] div[data-baseweb="select"] span {
            color: #ffffff;
        }

        .eg-policy {
            background: #1b2c32;
            border: 1px solid #31464d;
            border-radius: 6px;
            margin-top: 0.35rem;
            padding: 0.8rem 0.85rem;
        }

        .eg-policy-head {
            align-items: center;
            border-bottom: 1px solid #31464d;
            color: #ffffff;
            display: flex;
            font-size: 0.78rem;
            font-weight: 720;
            justify-content: space-between;
            margin-bottom: 0.55rem;
            padding-bottom: 0.55rem;
        }

        .eg-lock {
            color: var(--eg-teal-bright);
            font-size: 0.61rem;
            font-weight: 800;
            letter-spacing: 0.08em;
        }

        .eg-policy-row {
            color: #9eb0b5;
            display: flex;
            font-size: 0.72rem;
            justify-content: space-between;
            line-height: 1.8;
        }

        .eg-policy-row strong {
            color: #edf4f5;
            font-weight: 650;
        }

        section[data-testid="stSidebar"] [data-testid="stLinkButton"] a {
            background: transparent;
            border-color: #40545b;
            color: #d6e0e3;
            margin-top: 0.75rem;
        }

        @media (max-width: 768px) {
            .block-container {
                padding: 4rem 1rem 3rem;
            }

            .eg-page-title {
                font-size: 2rem;
            }

            .eg-page-deck {
                font-size: 0.94rem;
            }

            div[data-testid="stMetric"] {
                min-height: 94px;
            }

            .eg-decision-row {
                grid-template-columns: 10px 1fr;
            }

            .eg-decision-copy {
                grid-column: 2;
            }
        }
        </style>
        """
    )


def page_header(title: str, eyebrow: str, description: str | None = None) -> None:
    description_html = f'<p class="eg-page-deck">{escape(description)}</p>' if description else ""
    st.html(
        f"""
        <header class="eg-page-header">
            <div class="eg-eyebrow">{escape(eyebrow)}</div>
            <h1 class="eg-page-title">{escape(title)}</h1>
            {description_html}
        </header>
        """
    )


def decision_legend() -> None:
    colours = {
        "LAUNCH": "#0f766e",
        "CONTINUE": "#2563eb",
        "NO_MEANINGFUL_WIN": "#b7791f",
        "INVALID": "#bd3f3a",
    }
    rows = "".join(
        f"""
        <div class="eg-decision-row">
            <span class="eg-decision-dot" style="background:{colours[name]}"></span>
            <span class="eg-decision-name">{escape(name)}</span>
            <span class="eg-decision-copy">{escape(DECISION_HELP[name])}</span>
        </div>
        """
        for name in DECISION_ORDER
    )
    st.html(f'<div class="eg-decision-list">{rows}</div>')


def sidebar(page: str) -> str:
    """Shared sidebar. Returns the selected partition."""
    inject_styles()
    p = policy()
    nav_html = "".join(
        f"""
        <a class="eg-nav-link{" active" if page == page_key else ""}"
           href="{route}" target="_self">
            <span class="eg-nav-icon">{icon}</span><span>{escape(label)}</span>
        </a>
        """
        for route, label, icon, page_key in NAV_ITEMS
    )
    st.sidebar.html(
        """
        <div class="eg-brand">
            <div class="eg-brand-mark">EG</div>
            <div>
                <div class="eg-brand-name">ExperimentGuard</div>
                <div class="eg-brand-tagline">Evidence before launch</div>
            </div>
        </div>
        <div class="eg-sidebar-label">Workspace</div>
        """
        + nav_html
    )

    parts = available_partitions()
    if not parts:
        st.sidebar.error("No analysis tables. Run `make analyze`.")
        st.stop()

    default = parts.index("exploratory") if "exploratory" in parts else 0
    st.sidebar.html('<div class="eg-sidebar-label">Data scope</div>')
    partition = st.sidebar.selectbox("Analysis partition", parts, index=default, key="partition")
    if partition == "holdout":
        st.sidebar.warning(
            "Holdout is once-only evidence. Treat anything read here as final.",
            icon=":material/lock:",
        )

    st.sidebar.html('<div class="eg-sidebar-label">Governance</div>')
    st.sidebar.html(
        f"""
        <div class="eg-policy">
            <div class="eg-policy-head">
                <span>Frozen policy</span><span class="eg-lock">LOCKED</span>
            </div>
            <div class="eg-policy-row"><span>Version</span><strong>{escape(p.policy_version)}</strong></div>
            <div class="eg-policy-row"><span>Lift threshold</span><strong>{p.practical_threshold:.0%}</strong></div>
            <div class="eg-policy-row"><span>Correction</span><strong>{escape(p.multiplicity_method.title())}</strong></div>
            <div class="eg-policy-row"><span>Checksum</span><strong>{policy_checksum()[:10]}…</strong></div>
        </div>
        """
    )
    st.sidebar.caption("Scenario changes never overwrite the official decision contract.")
    st.sidebar.link_button(
        "View source",
        "https://github.com/meetsutariya4448/ExperimentGuard",
        icon=":material/code:",
        width="stretch",
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
