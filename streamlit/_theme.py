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
    """Inject the INTL design system CSS + sidebar-toggle visibility JS. Idempotent."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(_SIDEBAR_TOGGLE_JS, unsafe_allow_html=True)


# JS that runs every 500ms to force the sidebar toggle visible, regardless of
# Streamlit version. Survives re-renders that wipe inline styles.
_SIDEBAR_TOGGLE_JS = """
<script>
(function() {
  // Native Streamlit sidebar-toggle elements — multiple selectors for cross-version coverage
  const SELECTORS = [
    '[data-testid="stSidebarCollapsedControl"]',
    '[data-testid="collapsedControl"]',
    '[data-testid="stExpandSidebarButton"]',
    '[data-testid="stSidebarCollapseButton"]',
    'header button[kind="header"]',
    'header button[kind="headerNoPadding"]',
  ];

  // Style applied to the native toggle when it's the collapsed/expand button
  // position:fixed pins it to viewport so browser chrome/tabs can never cover it
  const FIXED_STYLE = `
    position: fixed !important;
    top: 14px !important;
    left: 14px !important;
    background: #4c8bf5 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 8px !important;
    width: 42px !important;
    height: 42px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    visibility: visible !important;
    opacity: 1 !important;
    box-shadow: 0 0 0 2px #4c8bf5, 0 4px 14px rgba(76, 139, 245, 0.5) !important;
    cursor: pointer !important;
    z-index: 999999 !important;
  `;

  // For the close button inside an OPEN sidebar (lives inside the sidebar DOM,
  // so should stay in place — just style it cobalt)
  const INSIDE_STYLE = `
    background: #4c8bf5 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 6px !important;
    width: 36px !important;
    height: 36px !important;
    visibility: visible !important;
    opacity: 1 !important;
    cursor: pointer !important;
  `;

  function paintIcon(el) {
    el.querySelectorAll('svg').forEach(svg => {
      svg.style.color = '#ffffff';
      svg.style.fill = '#ffffff';
      svg.style.opacity = '1';
      svg.style.width = '20px';
      svg.style.height = '20px';
    });
    el.querySelectorAll('svg path, svg g').forEach(p => {
      p.style.fill = '#ffffff';
    });
    el.querySelectorAll('[class*="material-symbol"], [data-testid*="Icon"]').forEach(sym => {
      sym.style.color = '#ffffff';
      sym.style.fontSize = '22px';
      sym.style.opacity = '1';
    });
    // Last-resort fallback character
    if (!el.querySelector('svg') && !el.querySelector('[class*="material"]') && !el.textContent.trim()) {
      el.innerHTML = '<span style="color:white;font-size:20px;font-weight:700;line-height:1">☰</span>';
    }
  }

  function paintToggle(el) {
    if (!el) return;
    // Detect whether this is the collapsed button (lives in <header>) or the
    // close button (lives inside [data-testid="stSidebar"])
    const isInsideSidebar = el.closest('[data-testid="stSidebar"]') !== null;
    el.style.cssText = isInsideSidebar ? INSIDE_STYLE : FIXED_STYLE;
    paintIcon(el);
  }

  function ensureVisible() {
    for (const sel of SELECTORS) {
      document.querySelectorAll(sel).forEach(paintToggle);
    }
  }

  ensureVisible();
  setTimeout(ensureVisible, 300);
  setTimeout(ensureVisible, 1000);
  setTimeout(ensureVisible, 3000);

  const observer = new MutationObserver(() => ensureVisible());
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  }
  setInterval(ensureVisible, 2000);
})();
</script>
"""


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

/* Hide Streamlit chrome — keep header + sidebar toggle visible */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Show the header (contains the sidebar toggle) but hide its content widgets */
header[data-testid="stHeader"] {
  visibility: visible !important;
  background: transparent !important;
  height: 3rem !important;
}
[data-testid="stToolbar"]      { display: none !important; }
[data-testid="stDecoration"]   { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }

/* ═══════════ SIDEBAR TOGGLE — every known selector across Streamlit versions ═══════════ */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"],
header button[kind="header"],
header button[kind="headerNoPadding"] {
  visibility: visible !important;
  opacity: 1 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  background: #4c8bf5 !important;
  color: #ffffff !important;
  border: none !important;
  border-radius: 6px !important;
  width: 40px !important;
  height: 40px !important;
  margin: 6px !important;
  cursor: pointer !important;
  z-index: 9999 !important;
  position: relative !important;
  box-shadow: 0 2px 8px rgba(76, 139, 245, 0.3) !important;
}

[data-testid="stSidebarCollapsedControl"]:hover,
[data-testid="collapsedControl"]:hover,
[data-testid="stExpandSidebarButton"]:hover,
header button[kind="header"]:hover {
  background: #3a78e0 !important;
  box-shadow: 0 4px 12px rgba(76, 139, 245, 0.5) !important;
}

/* Force the icon inside to be white + visible */
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="collapsedControl"] svg,
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stSidebarCollapseButton"] svg,
header button[kind="header"] svg,
header button[kind="headerNoPadding"] svg {
  width: 20px !important;
  height: 20px !important;
  color: #ffffff !important;
  fill: #ffffff !important;
  opacity: 1 !important;
  display: inline-block !important;
}
[data-testid="stSidebarCollapsedControl"] svg path,
[data-testid="collapsedControl"] svg path,
[data-testid="stExpandSidebarButton"] svg path,
[data-testid="stSidebarCollapseButton"] svg path,
header button[kind="header"] svg path,
header button[kind="headerNoPadding"] svg path {
  fill: #ffffff !important;
  stroke: #ffffff !important;
}

/* Material Symbols fallback for the icon */
[data-testid="stSidebarCollapsedControl"] [class*="material-symbol"],
[data-testid="collapsedControl"] [class*="material-symbol"],
header button[kind="header"] [class*="material-symbol"],
header button[kind="headerNoPadding"] [class*="material-symbol"] {
  font-family: 'Material Symbols Rounded' !important;
  font-size: 22px !important;
  color: #ffffff !important;
  font-feature-settings: 'liga' !important;
}

/* ::after fallback — always visible literal arrow if everything else fails */
[data-testid="stSidebarCollapsedControl"]::after,
[data-testid="collapsedControl"]::after {
  content: "☰";
  color: #ffffff;
  font-size: 18px;
  font-weight: 700;
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
}
/* When the SVG renders, hide the fallback */
[data-testid="stSidebarCollapsedControl"]:has(svg)::after,
[data-testid="collapsedControl"]:has(svg)::after,
[data-testid="stSidebarCollapsedControl"]:has([class*="material"])::after,
[data-testid="collapsedControl"]:has([class*="material"])::after {
  content: "" !important;
}
</style>
"""


# ── Helper components ────────────────────────────────────────────────────────

def status_pill(label: str, kind: str = "live") -> str:
    """Return HTML for a status pill. kind: live | stale | error."""
    return f'<span class="status-pill {kind}">{label}</span>'


# Centralized KPI tooltips — single source of truth for hover explanations
KPI_HELP = {
    "market_regime":
        "Aladdin-inspired classification of macro environment into one of 4 quadrants "
        "(Goldilocks / Reflation / Stagflation / Deflation), based on growth + inflation signals.",
    "systemic_risk":
        "Composite 0-100 risk score (SRS) blending VIX, yield curve, credit spreads, "
        "fear & greed, and labor market signals. Higher = more systemic stress.",
    "news_sentiment":
        "Bull/bear % of 200 most recent articles, source-credibility weighted "
        "(Bloomberg/Reuters > general news > social).",
    "alpha_signals":
        "Non-public alpha events: SEC EDGAR insider trades, unusual options flow, "
        "Congressional trades, FINRA short interest, credit spread shifts.",
    "market_tickers":
        "Number of ticker snapshots loaded from FRED + Yahoo Finance for macro indicators.",
    "var_95":
        "Value at Risk (95%): The 1-day loss exceeded only 5% of trading days, "
        "estimated from historical daily returns (no normality assumption).",
    "var_99":
        "Value at Risk (99%): Tail loss estimate — exceeded only 1% of trading days.",
    "cvar_95":
        "Conditional VaR / Expected Shortfall: Average loss in the worst 5% of days. "
        "More robust than VaR for tail-risk reporting.",
    "max_drawdown":
        "Peak-to-trough decline over the period. Captures worst historical loss path.",
    "sharpe":
        "Sharpe ratio: excess return per unit of volatility. ≥1 is good, ≥2 is excellent.",
    "sortino":
        "Sortino ratio: like Sharpe but penalizes only downside volatility — better for asymmetric returns.",
    "annual_vol":
        "Annualised volatility = daily std × √252. Higher = more dispersed returns.",
    "beta":
        "Sensitivity to SPY (S&P 500). β=1 moves with market; β>1 amplifies; β<0 inverse-correlated.",
    "portfolio_var":
        "Portfolio-level VaR using EWMA-weighted covariance for adaptive risk estimation.",
    "portfolio_sharpe":
        "Weighted-portfolio Sharpe ratio over the lookback period.",
    "confidence":
        "How strongly the macro signals agree on the regime classification (0-100%). "
        "Higher = stronger consensus from yield curve, VIX, CPI, unemployment.",
    "transition_risk":
        "Probability of regime shift in coming weeks, based on signal proximity to "
        "quadrant boundaries (low/medium/high).",
}
