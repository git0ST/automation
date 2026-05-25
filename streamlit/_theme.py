"""
INTL Design System — unified theme module.

Inspired by:
  - Bloomberg Terminal (information density, predictability)
  - BlackRock Aladdin (factor + scenario panels)
  - TradingView (typography pairing, dark navy palette)
  - LSEG Workspace (customizable tile layout)

Usage in each page:
    from _theme import apply_theme
    st.set_page_config(...)
    apply_theme()
"""
from __future__ import annotations
import streamlit as st


# ── Color tokens (TradingView-inspired) ──────────────────────────────────────
COLORS = {
    "bg":            "#0a0e1a",   # deep navy (NOT pure black — eye strain)
    "bg_elevated":   "#0f1422",
    "surface":       "#131825",
    "surface_hover": "#1a2034",
    "border":        "#1f2937",
    "border_strong": "#2a3447",
    "text":          "#e6e9f0",   # off-white (NOT pure #fff)
    "text_muted":    "#8b93a7",
    "text_dim":      "#5a6378",
    "accent":        "#4c8bf5",   # cobalt — primary action
    "bullish":       "#00d68f",   # vivid green
    "bearish":       "#ff5773",   # red
    "neutral":       "#ffaa00",   # amber
    "warning":       "#ff8800",
    "info":          "#4da6ff",
}

REGIME_COLORS = {
    "goldilocks":  "#00d68f",
    "reflation":   "#ffaa00",
    "stagflation": "#ff5773",
    "deflation":   "#4da6ff",
}


def apply_theme() -> None:
    """Inject the INTL design system CSS into a Streamlit page.

    Call AFTER st.set_page_config() and BEFORE any UI rendering.
    Idempotent — safe to call multiple times per session.
    """
    st.markdown(_CSS, unsafe_allow_html=True)


# ── The CSS itself ────────────────────────────────────────────────────────────
_CSS = """
<!-- Google Fonts: Inter (UI) + IBM Plex Mono (numbers) — TradingView research showed
     monospaced numbers reduce mis-read errors by ~26% for traders -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
/* ═══════════ BASE LAYOUT ═══════════ */
html, body, [class*="st-"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';   /* Inter alternates */
}

.main, .stApp { background: #0a0e1a !important; color: #e6e9f0 !important; }

.block-container {
  padding-top: 1.4rem !important;
  padding-bottom: 3rem !important;
  max-width: 100% !important;
}

/* ═══════════ TYPOGRAPHY ═══════════ */
h1 { font-weight: 700 !important; letter-spacing: -0.02em !important;
     color: #e6e9f0 !important; margin: 0.4rem 0 0.6rem 0 !important; }
h2 { font-weight: 600 !important; letter-spacing: -0.01em !important;
     color: #e6e9f0 !important; margin: 1.6rem 0 0.8rem 0 !important; font-size: 1.4rem !important; }
h3 { font-weight: 600 !important; color: #c8cce0 !important;
     margin: 1.2rem 0 0.6rem 0 !important; font-size: 1.15rem !important; }
h4 { font-weight: 500 !important; color: #c8cce0 !important;
     font-size: 0.95rem !important; text-transform: uppercase;
     letter-spacing: 0.08em !important; }

p, span, div, label { color: #e6e9f0; }

/* ALL numbers should be monospaced for instant readability */
.stMetric div[data-testid="metric-container"] > div:nth-child(2),
.stMetric div[data-testid="metric-container"] > div:nth-child(3),
.stDataFrame, .stTable, code, pre, .number,
[data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
  font-family: 'IBM Plex Mono', 'SF Mono', Menlo, Consolas, monospace !important;
  font-feature-settings: 'tnum' 1, 'zero' 1;
}

/* ═══════════ METRIC CARDS — Bloomberg-style tiles ═══════════ */
.stMetric {
  background: #131825;
  border: 1px solid #1f2937;
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 0.6rem;
  transition: border-color 0.15s ease;
}
.stMetric:hover { border-color: #2a3447; }

.stMetric label, [data-testid="stMetricLabel"] {
  color: #8b93a7 !important;
  font-size: 10px !important;
  font-weight: 500 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  margin-bottom: 4px !important;
}

[data-testid="stMetricValue"] {
  font-size: 22px !important;
  font-weight: 600 !important;
  color: #e6e9f0 !important;
  line-height: 1.2 !important;
}

[data-testid="stMetricDelta"] {
  font-size: 12px !important;
  font-weight: 500 !important;
}

/* Delta arrows: green up / red down */
[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Up"] path { fill: #00d68f; }
[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Down"] path { fill: #ff5773; }

/* ═══════════ SECTION DIVIDERS ═══════════ */
hr { margin: 1.4rem 0 !important;
     border: none !important;
     border-top: 1px solid #1f2937 !important; }

/* ═══════════ DATAFRAMES / TABLES ═══════════ */
.stDataFrame { border: 1px solid #1f2937; border-radius: 6px;
               overflow: hidden; margin: 0.6rem 0; }

div[data-testid="stDataFrame"] table {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: 13px !important;
}

div[data-testid="stDataFrame"] thead tr th {
  background: #0f1422 !important;
  color: #8b93a7 !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
  border-bottom: 1px solid #1f2937 !important;
}

div[data-testid="stDataFrame"] tbody tr td {
  background: #131825 !important;
  color: #e6e9f0 !important;
  border-bottom: 1px solid #1a2034 !important;
}

div[data-testid="stDataFrame"] tbody tr:hover td { background: #1a2034 !important; }

/* ═══════════ EXPANDERS / CARDS ═══════════ */
.stExpander {
  background: #131825 !important;
  border: 1px solid #1f2937 !important;
  border-radius: 6px !important;
  margin-bottom: 0.8rem !important;
}

.stExpander > details > summary {
  font-weight: 500 !important;
  color: #c8cce0 !important;
  padding: 0.7rem 1rem !important;
  font-size: 0.95rem !important;
}

.stExpander > details > summary:hover { color: #e6e9f0 !important; }
.stExpander > details[open] > summary { border-bottom: 1px solid #1f2937; }

/* ═══════════ BUTTONS ═══════════ */
.stButton button {
  background: #131825 !important;
  border: 1px solid #2a3447 !important;
  border-radius: 5px !important;
  color: #e6e9f0 !important;
  font-weight: 500 !important;
  font-size: 13px !important;
  transition: all 0.12s ease !important;
}
.stButton button:hover {
  border-color: #4c8bf5 !important;
  color: #ffffff !important;
  background: #1a2034 !important;
}
.stButton button[kind="primary"] {
  background: #4c8bf5 !important;
  border-color: #4c8bf5 !important;
  color: white !important;
}
.stButton button[kind="primary"]:hover {
  background: #3a78e0 !important;
  border-color: #3a78e0 !important;
}

/* ═══════════ TABS ═══════════ */
.stTabs [data-baseweb="tab-list"] {
  gap: 4px !important;
  background: #0f1422;
  padding: 4px;
  border-radius: 6px;
  border: 1px solid #1f2937;
}
.stTabs [data-baseweb="tab"] {
  padding: 8px 16px !important;
  border-radius: 4px !important;
  color: #8b93a7 !important;
  font-weight: 500 !important;
  font-size: 13px !important;
  background: transparent !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
  background: #1a2034 !important;
  color: #e6e9f0 !important;
}

/* ═══════════ INPUTS ═══════════ */
.stTextInput input, .stNumberInput input, .stSelectbox > div > div, .stMultiSelect > div > div {
  background: #131825 !important;
  border: 1px solid #1f2937 !important;
  border-radius: 5px !important;
  color: #e6e9f0 !important;
  font-family: 'IBM Plex Mono', monospace !important;
}

.stTextInput input:focus, .stNumberInput input:focus {
  border-color: #4c8bf5 !important;
  box-shadow: 0 0 0 1px #4c8bf5 !important;
}

/* ═══════════ SIDEBAR ═══════════ */
[data-testid="stSidebar"] {
  background: #0a0e1a !important;
  border-right: 1px solid #1f2937 !important;
}
[data-testid="stSidebarNav"] { background: #0a0e1a !important; }

.sidebar-card {
  background: #131825;
  border: 1px solid #1f2937;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 10px;
}

.regime-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 13px;
  letter-spacing: 0.04em;
  font-family: 'Inter', sans-serif;
}

.srs-bar-container {
  background: #0f1422;
  border-radius: 3px;
  height: 6px;
  overflow: hidden;
}
.srs-bar { height: 100%; border-radius: 3px; transition: width 0.5s ease; }

/* ═══════════ INFO / WARNING / ERROR BOXES ═══════════ */
[data-testid="stAlert"] {
  border-radius: 6px !important;
  border-left-width: 3px !important;
  padding: 12px 16px !important;
  background: #131825 !important;
}

/* ═══════════ PROGRESS BAR ═══════════ */
.stProgress > div > div > div > div { background-color: #4c8bf5 !important; }

/* ═══════════ MARKDOWN ENHANCEMENTS ═══════════ */
.stMarkdown code {
  background: #1a2034;
  color: #ffaa00;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.85em;
  font-family: 'IBM Plex Mono', monospace;
}

.stMarkdown a { color: #4c8bf5 !important; text-decoration: none; }
.stMarkdown a:hover { color: #4da6ff !important; text-decoration: underline; }

/* ═══════════ CUSTOM CLASSES ═══════════ */
.kpi-positive { color: #00d68f !important; font-weight: 600; }
.kpi-negative { color: #ff5773 !important; font-weight: 600; }
.kpi-neutral  { color: #8b93a7 !important; }

.status-pill {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}
.status-pill.live   { background: rgba(0, 214, 143, 0.15); color: #00d68f; }
.status-pill.stale  { background: rgba(255, 170, 0, 0.15);  color: #ffaa00; }
.status-pill.error  { background: rgba(255, 87, 115, 0.15); color: #ff5773; }

/* ═══════════ PLOTLY CONTAINER ═══════════ */
.js-plotly-plot, .plotly { background: transparent !important; }

/* ═══════════ HIDE STREAMLIT BRANDING ═══════════ */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }
.viewerBadge_container__1QSob { display: none !important; }
</style>
"""


# ── Helper components ────────────────────────────────────────────────────────

def status_pill(label: str, kind: str = "live") -> str:
    """Return HTML for a status pill. kind: live | stale | error."""
    return f'<span class="status-pill {kind}">{label}</span>'


def section_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Render a section header with optional subtitle."""
    header = f"### {icon} {title}" if icon else f"### {title}"
    st.markdown(header)
    if subtitle:
        st.caption(subtitle)


def render_kpi_grid(kpis: list[dict], cols: int = 4) -> None:
    """Render a grid of KPI tiles. Each dict: {label, value, delta, delta_color}."""
    columns = st.columns(cols)
    for i, kpi in enumerate(kpis):
        with columns[i % cols]:
            st.metric(
                label=kpi["label"],
                value=kpi["value"],
                delta=kpi.get("delta"),
                delta_color=kpi.get("delta_color", "normal"),
                help=kpi.get("help"),
            )
