"""INTL Design System — unified theme for all pages.

Apply once per page after `st.set_page_config()`.
"""
from __future__ import annotations
import streamlit as st


COLORS = {
    "bg":            "#0a0e1a",
    "bg_elevated":   "#0f1422",
    "surface":       "#131825",
    "surface_hover": "#1a2034",
    "border":        "#1f2937",
    "border_strong": "#2a3447",
    "text":          "#e6e9f0",
    "text_muted":    "#8b93a7",
    "text_dim":      "#5a6378",
    "accent":        "#4c8bf5",
    "bullish":       "#00d68f",
    "bearish":       "#ff5773",
    "neutral":       "#ffaa00",
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
    """Inject the INTL design system CSS. Idempotent."""
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400..700,0..1,-50..200&display=swap" rel="stylesheet">

<style>
/* Base — preserve Material Symbols on icon spans */
html, body, .stApp, [data-testid="stMarkdownContainer"],
p, span, div, label, h1, h2, h3, h4, h5, h6, input, textarea, button {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
}

.material-symbols-rounded, .material-symbols-outlined, .material-icons,
[class*="material-symbol"], [data-testid="stIconMaterial"] {
  font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
  font-feature-settings: 'liga' !important;
}

.main, .stApp { background: #0a0e1a !important; color: #e6e9f0 !important; }

.block-container {
  padding-top: 1.4rem !important;
  padding-bottom: 3rem !important;
  max-width: 100% !important;
}

/* Typography hierarchy */
h1 { font-weight: 700 !important; letter-spacing: -0.02em !important;
     color: #e6e9f0 !important; margin: 0.4rem 0 0.6rem 0 !important; }
h2 { font-weight: 600 !important; letter-spacing: -0.01em !important;
     color: #e6e9f0 !important; margin: 1.6rem 0 0.8rem 0 !important; font-size: 1.4rem !important; }
h3 { font-weight: 600 !important; color: #c8cce0 !important;
     margin: 1.2rem 0 0.6rem 0 !important; font-size: 1.15rem !important; }
h4 { font-weight: 500 !important; color: #c8cce0 !important;
     font-size: 0.95rem !important; text-transform: uppercase;
     letter-spacing: 0.08em !important; }

/* Numbers → IBM Plex Mono for tabular alignment */
.stMetric div[data-testid="metric-container"] > div:nth-child(2),
.stMetric div[data-testid="metric-container"] > div:nth-child(3),
.stDataFrame, .stTable, code, pre,
[data-testid="stMetricValue"], [data-testid="stMetricDelta"] {
  font-family: 'IBM Plex Mono', 'SF Mono', Menlo, Consolas, monospace !important;
  font-feature-settings: 'tnum' 1, 'zero' 1;
}

/* Metric cards */
.stMetric {
  background: #131825;
  border: 1px solid #1f2937;
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 0.6rem;
  transition: border-color 0.15s ease;
  min-height: 90px;
  overflow: hidden;
}
.stMetric:hover { border-color: #2a3447; }

.stMetric label, [data-testid="stMetricLabel"] {
  color: #8b93a7 !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  margin-bottom: 6px !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}

[data-testid="stMetricValue"] {
  font-size: 22px !important;
  font-weight: 600 !important;
  color: #e6e9f0 !important;
  line-height: 1.15 !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}

[data-testid="stMetricDelta"] {
  font-size: 12px !important;
  font-weight: 500 !important;
  white-space: nowrap !important;
}

[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Up"] path { fill: #00d68f; }
[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Down"] path { fill: #ff5773; }

/* Tooltip (help icon) — make it clearly clickable */
[data-testid="stTooltipIcon"] {
  color: #5a6378 !important;
  transition: color 0.15s ease;
}
[data-testid="stTooltipIcon"]:hover { color: #4c8bf5 !important; }

/* Tooltip content */
[role="tooltip"] {
  background: #1a2034 !important;
  border: 1px solid #2a3447 !important;
  color: #e6e9f0 !important;
  font-size: 13px !important;
  line-height: 1.5 !important;
  border-radius: 6px !important;
  padding: 10px 14px !important;
  max-width: 320px !important;
}

/* Section dividers */
hr { margin: 1.4rem 0 !important;
     border: none !important;
     border-top: 1px solid #1f2937 !important; }

/* Dataframes */
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
}

div[data-testid="stDataFrame"] tbody tr td {
  background: #131825 !important;
  color: #e6e9f0 !important;
}

div[data-testid="stDataFrame"] tbody tr:hover td { background: #1a2034 !important; }

/* Expanders */
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

/* Buttons */
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
  background: #1a2034 !important;
}
.stButton button[kind="primary"] {
  background: #4c8bf5 !important;
  border-color: #4c8bf5 !important;
  color: white !important;
}
.stButton button[kind="primary"]:hover {
  background: #3a78e0 !important;
}

/* Tabs */
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

/* Inputs */
.stTextInput input, .stNumberInput input,
.stSelectbox > div > div, .stMultiSelect > div > div {
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

/* Sidebar */
[data-testid="stSidebar"] {
  background: #0a0e1a !important;
  border-right: 1px solid #1f2937 !important;
}
/* Hide Streamlit auto-nav — replaced by custom grouped nav in render_chrome() */
[data-testid="stSidebarNav"] { display: none !important; }

/* ── Custom sidebar nav ─────────────────────────────────────────────── */
.nav-section {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: #3a4060;
  padding: 14px 12px 4px;
  border-top: 1px solid #1f2937;
  margin-top: 4px;
}
.nav-section:first-child { border-top: none; margin-top: 0; }

/* Status strip — regime + SRS always visible */
.nav-status {
  display: flex;
  gap: 0;
  border: 1px solid #1f2937;
  border-radius: 5px;
  overflow: hidden;
  margin: 8px 10px 6px;
  font-family: 'IBM Plex Mono', monospace;
}
.nav-stat {
  flex: 1;
  padding: 6px 8px;
  font-size: 10px;
  background: #0f1422;
  border-right: 1px solid #1f2937;
  line-height: 1.3;
}
.nav-stat:last-child { border-right: none; }
.nav-stat-lbl { font-size: 7.5px; color: #3a4060; letter-spacing: .1em; text-transform: uppercase; }
.nav-stat-val { font-weight: 700; font-size: 12px; }

/* page_link overrides */
[data-testid="stSidebar"] [data-testid="stPageLink"] a,
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
  border-radius: 4px !important;
  font-size: 12.5px !important;
  font-weight: 500 !important;
  color: #8b93a7 !important;
  padding: 5px 12px !important;
  margin: 0 4px !important;
  transition: background .1s, color .1s !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover,
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {
  background: #131825 !important;
  color: #e6e9f0 !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"][aria-current="page"] a,
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] {
  background: #111c34 !important;
  color: #4c8bf5 !important;
  font-weight: 600 !important;
}

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
}

.srs-bar-container {
  background: #0f1422;
  border-radius: 3px;
  height: 6px;
  overflow: hidden;
}
.srs-bar { height: 100%; border-radius: 3px; transition: width 0.5s ease; }

/* Alerts */
[data-testid="stAlert"] {
  border-radius: 6px !important;
  border-left-width: 3px !important;
  padding: 12px 16px !important;
  background: #131825 !important;
}

/* Progress */
.stProgress > div > div > div > div { background-color: #4c8bf5 !important; }

/* Markdown links + inline code */
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

/* Custom utility classes */
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

.js-plotly-plot, .plotly { background: transparent !important; }

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
/* Zero out the header (no sticky bar) WITHOUT display:none — so the sidebar
   expand control, which some Streamlit versions nest inside the header, can
   still show (it's fixed-positioned and overflows the 0-height header). */
[data-testid="stHeader"]       { background: transparent !important; height: 0 !important; }
[data-testid="stToolbar"]      { display: none !important; }
[data-testid="stDecoration"]   { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stAppViewBlockContainer"] { padding-top: 0.5rem !important; }

/* ═══════════ SIDEBAR — collapsible, with a logo toggle ═══════════ */
/* The native collapse/expand stays ENABLED (so the rail opens & closes at
   will). We just restyle Streamlit's toggle into a small frosted-white "logo"
   button pinned top-left. If a future Streamlit renames a testid the toggle
   still works natively — it just falls back to the default chevron. */

/* Expand control (visible when the sidebar is collapsed) — pinned top-left,
   above the (hidden) header, always clickable to bring the rail back. */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"] {
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  position: fixed !important;
  top: 10px !important;
  left: 10px !important;
  z-index: 1000 !important;
}

/* Logo-button look for BOTH controls (expand when collapsed + collapse when
   expanded). Complementary frosted white against the dark theme. */
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"] button,
[data-testid="stExpandSidebarButton"] button,
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarHeader"] button {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 36px !important;
  height: 36px !important;
  padding: 0 !important;
  border-radius: 9px !important;
  background: rgba(245, 247, 250, 0.10) !important;
  border: 1px solid rgba(245, 247, 250, 0.22) !important;
  color: #f5f7fa !important;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.45) !important;
  transition: background .15s ease, border-color .15s ease, transform .15s ease;
}
[data-testid="stSidebarCollapsedControl"] button:hover,
[data-testid="collapsedControl"] button:hover,
[data-testid="stExpandSidebarButton"] button:hover,
[data-testid="stSidebarCollapseButton"]:hover,
[data-testid="stSidebarHeader"] button:hover {
  background: rgba(245, 247, 250, 0.20) !important;
  border-color: rgba(245, 247, 250, 0.45) !important;
  transform: translateY(-1px);
}

/* Swap Streamlit's chevron SVG for a clean glyph: ☰ to open, « to close */
[data-testid="stSidebarCollapsedControl"] button svg,
[data-testid="collapsedControl"] button svg,
[data-testid="stExpandSidebarButton"] button svg,
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarHeader"] button svg {
  display: none !important;
}
[data-testid="stSidebarCollapsedControl"] button::before,
[data-testid="collapsedControl"] button::before,
[data-testid="stExpandSidebarButton"] button::before {
  content: "\2630";   /* ☰ menu — bring the rail into view */
  font-size: 16px; line-height: 1; color: #f5f7fa;
}
[data-testid="stSidebarCollapseButton"]::before,
[data-testid="stSidebarHeader"] button::before {
  content: "\00AB";   /* « — send the rail away */
  font-size: 16px; line-height: 1; color: #f5f7fa;
}

/* Comfortable expanded width — NO !important so native collapse still works */
[data-testid="stSidebar"] { min-width: 256px; }
[data-testid="stSidebarContent"] { visibility: visible; }
</style>
"""


# ── Helper components ────────────────────────────────────────────────────────

def status_pill(label: str, kind: str = "live") -> str:
    """Return HTML for a status pill. kind: live | stale | error."""
    return f'<span class="status-pill {kind}">{label}</span>'


# KPI tooltips moved to _kpi_help.py (single source of truth, how-to-use focused)
