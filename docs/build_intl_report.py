#!/usr/bin/env python3
"""Generate the INTL Terminal executive review PDF (accurate, link-rich)."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, ListFlowable, ListItem,
                                PageBreak)

OUT = "/Users/shivamthakur/Desktop/INTL_Executive_Review.pdf"
GH = "https://github.com/git0ST/automation/blob/main/"

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#0d1530")
INK    = colors.HexColor("#1d2330")
SLATE  = colors.HexColor("#5a6378")
BLUE   = colors.HexColor("#2f6df0")
GREEN  = colors.HexColor("#0a9c63")
RED    = colors.HexColor("#d33a3a")
AMBER  = colors.HexColor("#c47f00")
LIGHT  = colors.HexColor("#eef1f6")
LINE   = colors.HexColor("#d4dae6")

styles = getSampleStyleSheet()
def S(name, **kw):
    styles.add(ParagraphStyle(name, parent=styles["Normal"], **kw))

S("Body", fontName="Helvetica", fontSize=9.3, leading=13.5, textColor=INK, spaceAfter=6)
S("Small", fontName="Helvetica", fontSize=8, leading=11, textColor=SLATE)
S("H1", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=NAVY, spaceBefore=10, spaceAfter=6)
S("H2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=BLUE, spaceBefore=8, spaceAfter=4)
S("Cover", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=NAVY)
S("CoverSub", fontName="Helvetica", fontSize=12, leading=16, textColor=SLATE)
S("Cell", fontName="Helvetica", fontSize=8.4, leading=11, textColor=INK)
S("CellB", fontName="Helvetica-Bold", fontSize=8.4, leading=11, textColor=NAVY)
S("CellW", fontName="Helvetica-Bold", fontSize=8.4, leading=11, textColor=colors.white)
S("Link", fontName="Helvetica", fontSize=8.2, leading=11, textColor=BLUE)

def link(text, path):
    return Paragraph(f'<a href="{GH}{path}" color="#2f6df0">{text}</a>', styles["Link"])

def para(text, style="Body"):
    return Paragraph(text, styles[style])

story = []

# ── COVER ─────────────────────────────────────────────────────────────────────
story += [Spacer(1, 30*mm)]
story.append(Paragraph("INTL Terminal", styles["Cover"]))
story.append(Paragraph("Executive System Review &amp; Cron Health Audit", styles["CoverSub"]))
story.append(Spacer(1, 6*mm))
story.append(HRFlowable(width="100%", thickness=2, color=BLUE))
story.append(Spacer(1, 5*mm))
cover_meta = Table([
    [Paragraph("Prepared", styles["Small"]), Paragraph("14 June 2026", styles["CellB"])],
    [Paragraph("Repository", styles["Small"]),
     Paragraph('<a href="https://github.com/git0ST/automation" color="#2f6df0">github.com/git0ST/automation</a> (branch: main)', styles["Link"])],
    [Paragraph("Scope", styles["Small"]), Paragraph("India-first quantitative portfolio system — data pipeline, calibrated decision engine, auto-mode paper trading, self-learning loop", styles["Cell"])],
    [Paragraph("Audience", styles["Small"]), Paragraph("Owner / Engineering / Investment review", styles["Cell"])],
], colWidths=[28*mm, 132*mm])
cover_meta.setStyle(TableStyle([
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LINEBELOW", (0,0), (-1,-2), 0.4, LINE),
]))
story.append(cover_meta)
story.append(Spacer(1, 8*mm))

# Status banner
banner = Table([[Paragraph("OVERALL STATUS", styles["CellW"]),
                 Paragraph("ARCHITECTURE &amp; LEARNING: SOUND  &nbsp;|&nbsp;  DATA PIPELINE: <b>ACTION REQUIRED</b>", styles["CellW"])]],
               colWidths=[40*mm, 120*mm])
banner.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (0,0), NAVY),
    ("BACKGROUND", (1,0), (1,0), AMBER),
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ("LEFTPADDING", (0,0), (-1,-1), 10),
]))
story.append(banner)
story.append(Spacer(1, 4*mm))
story.append(para("This report opens with the requested cron / data-gap audit (a critical finding), "
                  "then documents the system, its India-first investment layer, the self-learning loop, "
                  "and prioritized next steps. All figures are drawn from verified session data; where the "
                  "live environment could not be re-queried (cron environment offline at time of writing), "
                  "values are labelled <i>last-verified</i>.", "Small"))
story.append(PageBreak())

# ── 1. CRITICAL FINDING ───────────────────────────────────────────────────────
story.append(Paragraph("1.  Cron Health Audit — Critical Finding", styles["H1"]))

crit = Table([[Paragraph("&#9888;  CRITICAL: Scheduled data collection is failing silently", styles["CellW"])]],
             colWidths=[160*mm])
crit.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),RED),
                          ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
                          ("LEFTPADDING",(0,0),(-1,-1),10)]))
story.append(crit)
story.append(Spacer(1, 3*mm))
story.append(para("<b>Root cause.</b> The Python environment is reached via <font face='Courier'>~/anaconda3</font>, "
                  "which is a <b>symlink to a removable SanDisk SSD</b> (<font face='Courier'>/Volumes/SSD1TB</font>). "
                  "When the SSD is unplugged or unmounted at the scheduled cron windows (06:00 / 12:00 / 17:00 IST), "
                  "the interpreter path does not exist and the run aborts instantly under <font face='Courier'>set -e</font> — "
                  "with no alert."))
story.append(para("<b>Evidence (logs).</b> Every scheduled run on 12–13 June produced only:"))
ev = Table([[Paragraph("<font face='Courier' size=7>run_digest.sh: line 23: /Users/shivamthakur/anaconda3/envs/automation/bin/python: No such file or directory</font>", styles["Cell"])]],
           colWidths=[160*mm])
ev.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),LIGHT),("BOX",(0,0),(-1,-1),0.4,LINE),
                        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
                        ("LEFTPADDING",(0,0),(-1,-1),8)]))
story.append(ev)
story.append(Spacer(1, 2*mm))

gap = Table([
    [Paragraph("Window", styles["CellW"]), Paragraph("Completed-stage runs", styles["CellW"]), Paragraph("python-not-found failures", styles["CellW"]), Paragraph("Status", styles["CellW"])],
    [para("27–31 May", "Cell"), para("up to 4/day", "Cell"), para("0", "Cell"), Paragraph("<font color='#0a9c63'><b>healthy</b></font>", styles["Cell"])],
    [para("31 May → 11 Jun", "Cell"), para("0 (machine reboot dropped job)", "Cell"), para("—", "Cell"), Paragraph("<font color='#d33a3a'><b>11-day gap</b></font>", styles["Cell"])],
    [para("11 Jun", "Cell"), para("4", "Cell"), para("2", "Cell"), Paragraph("<font color='#c47f00'><b>partial</b></font>", styles["Cell"])],
    [para("12 Jun", "Cell"), para("0", "Cell"), para("3", "Cell"), Paragraph("<font color='#d33a3a'><b>total failure</b></font>", styles["Cell"])],
    [para("13 Jun", "Cell"), para("0", "Cell"), para("3", "Cell"), Paragraph("<font color='#d33a3a'><b>total failure</b></font>", styles["Cell"])],
], colWidths=[40*mm, 50*mm, 45*mm, 25*mm])
gap.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,0),NAVY),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, LIGHT]),
    ("GRID",(0,0),(-1,-1),0.4,LINE), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
    ("LEFTPADDING",(0,0),(-1,-1),6),
]))
story.append(gap)
story.append(Spacer(1, 3*mm))

story.append(Paragraph("Why it matters", styles["H2"]))
story.append(para("Calibration, weight-learning and the paper-trading book all depend on uninterrupted collection. "
                  "Each silent gap starves the very mechanisms that make the system accurate. The earlier "
                  "11-day outage already cost more measured accuracy than any model defect to date."))

story.append(Paragraph("Mitigation shipped this session", styles["H2"]))
story.append(ListFlowable([
    ListItem(para("<b>Mount-aware, fail-loud runner.</b> The runner now searches a candidate interpreter list "
                  "(internal disk first, SSD last), attempts <font face='Courier'>diskutil mount SSD1TB</font> if missing, "
                  "and on failure writes a <font face='Courier'>CRON_ALERT.log</font> line and exits 70 — a gap can never "
                  "again pass unnoticed. &nbsp;[commit cfec854]", "Cell")),
    ListItem(para("<b>Reboot resilience confirmed.</b> Both launchd jobs carry <font face='Courier'>RunAtLoad=true</font>, "
                  "so a restart resumes collection.", "Cell")),
], bulletType="bullet", start="square", leftIndent=10))
story.append(Spacer(1, 2*mm))

rec = Table([[Paragraph("RECOMMENDED PERMANENT FIX", styles["CellW"]),
              Paragraph("Relocate the Python environment off removable media onto the internal disk "
                        "(<b>43&nbsp;GB free</b> — ample). This makes the schedule immune to the SSD being unplugged. "
                        "Alternative: keep the SanDisk SSD permanently connected and disable its auto-unmount.", styles["Cell"])]],
            colWidths=[42*mm, 118*mm])
rec.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),GREEN),("BACKGROUND",(1,0),(1,0),LIGHT),
                         ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("BOX",(0,0),(-1,-1),0.4,LINE),
                         ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
                         ("LEFTPADDING",(0,0),(-1,-1),8)]))
story.append(rec)
story.append(Spacer(1, 2*mm))
story.append(Table([[para("Reference file:", "Small"), link("run_digest.sh", "run_digest.sh")]],
                   colWidths=[28*mm, 60*mm]))
story.append(PageBreak())

# ── 2. ARCHITECTURE ───────────────────────────────────────────────────────────
story.append(Paragraph("2.  System Architecture", styles["H1"]))
story.append(para("Three independent runtimes share one calibrated decision engine — no logic is duplicated."))
arch = Table([
    [Paragraph("Runtime", styles["CellW"]), Paragraph("Role", styles["CellW"]), Paragraph("Writes", styles["CellW"])],
    [para("Headless cron (Mac · launchd)", "CellB"), para("16-source pipeline → US + India scans → predictions → outcome correlation → weight tuning → paper trading", "Cell"), para("Supabase (service key)", "Cell")],
    [para("Streamlit Cloud app", "CellB"), para("Read-only UI behind a password gate; India Invest, India Intraday, My Plan, Paper Trading, Track Record", "Cell"), para("Reads (anon key)", "Cell")],
    [para("Offline ML", "CellB"), para("Local feature corpus (44 features/row) + daily labeling job; first supervised model", "Cell"), para("Local JSONL", "Cell")],
], colWidths=[42*mm, 92*mm, 26*mm])
arch.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,0),NAVY),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, LIGHT]),
    ("GRID",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"TOP"),
    ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),6),
]))
story.append(arch)
story.append(Spacer(1, 3*mm))

story.append(Paragraph("Decision engine — 6-step calibrated pipeline", styles["H2"]))
story.append(para("Each step is grounded in established quant practice (file: "
                  '<a href="' + GH + 'streamlit/_stock_analysis.py" color="#2f6df0">streamlit/_stock_analysis.py</a>):'))
eng = Table([
    [para("1", "CellB"), para("Regime-conditional weights", "Cell"), para("weights keyed to the live market regime", "Cell")],
    [para("2", "CellB"), para("5-signal weighted vote", "Cell"), para("technical · quant factors · analyst · sentiment · sector", "Cell")],
    [para("3", "CellB"), para("Agreement × strength", "Cell"), para("corroboration raises, disagreement cuts conviction", "Cell")],
    [para("4", "CellB"), para("Volatility targeting", "Cell"), para("conviction scaled inversely to realized vol", "Cell")],
    [para("5", "CellB"), para("Systemic-risk haircut", "Cell"), para("US SRS / India VIX trims conviction in stress", "Cell")],
    [para("6", "CellB"), para("Empirical calibration", "Cell"), para("stated confidence pulled to observed hit-rate", "Cell")],
], colWidths=[8*mm, 48*mm, 104*mm])
eng.setStyle(TableStyle([("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white, LIGHT]),
                         ("GRID",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                         ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),6)]))
story.append(eng)
story.append(Spacer(1, 2*mm))
story.append(para("Beyond the directional call: a holding-horizon inference, an explicit AVOID screen, and "
                  "quarter-Kelly position sizing under a 60% gross-exposure cap with volatility-scaled stops.", "Small"))
story.append(PageBreak())

# ── 3. INDIA-FIRST LAYER ──────────────────────────────────────────────────────
story.append(Paragraph("3.  India-First Investment Layer", styles["H1"]))
story.append(para("Portfolio growth is a positional problem, so the full engine now runs on the NSE with India-native "
                  "inputs: yfinance NSE fundamentals (P/E, ROE, growth, margins, 30–40-analyst consensus per name), "
                  "India VIX mapped onto the risk haircut, and the NIFTY SMA50/200 trend regime gating shorts."))
pages = Table([
    [Paragraph("Surface", styles["CellW"]), Paragraph("Purpose", styles["CellW"]), Paragraph("Source", styles["CellW"])],
    [para("My Plan", "CellB"), para("Beginner cockpit: core-satellite allocation with live evidence gates + system-health grade", "Cell"), link("0_My_Plan.py", "streamlit/pages/0_My_Plan.py")],
    [para("India Invest", "CellB"), para("NIFTY 50 positional BUY list, factor grades, analyst upside, rupee Kelly sizing, holdings review", "Cell"), link("0_India_Invest.py", "streamlit/pages/0_India_Invest.py")],
    [para("India Intraday", "CellB"), para("Live NSE setups: VWAP, opening-range breakout, RVOL, ATR stops, session discipline", "Cell"), link("0_India_Intraday.py", "streamlit/pages/0_India_Intraday.py")],
    [para("Paper Trading", "CellB"), para("Auto-mode virtual book: equity curve, open risk, closed ledger, adaptation state", "Cell"), link("B_Paper_Trading.py", "streamlit/pages/B_Paper_Trading.py")],
], colWidths=[28*mm, 100*mm, 32*mm])
pages.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
                           ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, LIGHT]),
                           ("GRID",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"TOP"),
                           ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),6)]))
story.append(pages)
story.append(Spacer(1, 3*mm))

story.append(Paragraph("Live India read (last-verified, 13 Jun)", styles["H2"]))
story.append(para("Regime: <b>NIFTY BEAR · India VIX 15.6</b> — the engine correctly compressed conviction "
                  "(no name above 55%), ranking quality-at-a-discount as best risk/reward:"))
buys = Table([
    [Paragraph("Name", styles["CellW"]), Paragraph("Quant", styles["CellW"]), Paragraph("Analyst upside", styles["CellW"]), Paragraph("Analysts", styles["CellW"]), Paragraph("Note", styles["CellW"])],
    [para("ICICI Bank", "CellB"), para("B (65)", "Cell"), para("+31%", "Cell"), para("40", "Cell"), para("strongest consensus gap", "Cell")],
    [para("Shriram Finance", "CellB"), para("B (70)", "Cell"), para("+30%", "Cell"), para("32", "Cell"), para("best quant score", "Cell")],
    [para("NTPC", "CellB"), para("B (63)", "Cell"), para("+23%", "Cell"), para("28", "Cell"), para("defensive utility", "Cell")],
    [para("Adani Ports", "CellB"), para("B (65)", "Cell"), para("+7%", "Cell"), para("25", "Cell"), para("only strong momentum (+28% 3m)", "Cell")],
    [para("Axis Bank", "CellB"), para("C+ (58)", "Cell"), para("+23%", "Cell"), para("39", "Cell"), para("financials theme", "Cell")],
], colWidths=[34*mm, 22*mm, 28*mm, 20*mm, 56*mm])
buys.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),GREEN),
                          ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, LIGHT]),
                          ("GRID",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                          ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),6)]))
story.append(buys)
story.append(Spacer(1, 2*mm))
story.append(para("<b>Sizing discipline:</b> stage into the top names at the page's quarter-Kelly sizes, honor "
                  "volatility-scaled stops, keep total deployment under the 60% gross cap, and do not short in a bear "
                  "trend (the system measured its own bearish calls at a 3% hit rate). Core index SIP remains the "
                  "primary stable-growth engine, untouched by signal quality.", "Small"))
story.append(PageBreak())

# ── 4. LEARNING & ADAPTATION ──────────────────────────────────────────────────
story.append(Paragraph("4.  Self-Learning &amp; Market Adaptation", styles["H1"]))
story.append(para("The loop was executed this session: <b>240 predictions settled</b> against realized 7-day returns, "
                  "weights re-tuned and activated (v1.1-learned), and empirical calibration verified live. "
                  "File: " + f'<a href="{GH}shared/learning_loop.py" color="#2f6df0">shared/learning_loop.py</a>.'))

story.append(Paragraph("Calibration — stated confidence vs measured reality (last-verified)", styles["H2"]))
cal = Table([
    [Paragraph("Band / direction", styles["CellW"]), Paragraph("Settled", styles["CellW"]), Paragraph("Hit rate", styles["CellW"]), Paragraph("Engine response", styles["CellW"])],
    [para("Bullish 60–69%", "CellB"), para("45", "Cell"), Paragraph("<font color='#0a9c63'><b>80%</b></font>", styles["Cell"]), para("sweet spot — trusted", "Cell")],
    [para("Bullish 70–79%", "CellB"), para("20", "Cell"), Paragraph("<font color='#0a9c63'><b>75%</b></font>", styles["Cell"]), para("well-calibrated, untouched", "Cell")],
    [para("Bullish 80–100%", "CellB"), para("15", "Cell"), Paragraph("<font color='#d33a3a'><b>0%</b></font>", styles["Cell"]), para("over-confident band → cut to ~62%", "Cell")],
    [para("Bearish (all)", "CellB"), para("67", "Cell"), Paragraph("<font color='#d33a3a'><b>3%</b></font>", styles["Cell"]), para("anti-predictive → conviction slashed", "Cell")],
], colWidths=[40*mm, 22*mm, 24*mm, 74*mm])
cal.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
                         ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, LIGHT]),
                         ("GRID",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                         ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),6)]))
story.append(cal)
story.append(Spacer(1, 2*mm))
story.append(para("Net effect: the calibration is self-correcting — the long book delivered <b>+3.3% vs SPY −2.0%</b> "
                  "(≈ +5.3pp alpha) over the window, while the system now declines the call types it measured itself "
                  "failing at. The very next scan logged 9 selective calls instead of ~50.", "Small"))

story.append(Paragraph("Auto-mode paper trading + adaptation", styles["H2"]))
story.append(para("Every cron pass the system now <b>acts on its own calls virtually</b> — opening positions, managing "
                  "stop / target / time-stops, and recording realized P&amp;L (file: "
                  f'<a href="{GH}shared/paper_trader.py" color="#2f6df0">shared/paper_trader.py</a>). '
                  "First live cycle opened 4 positions (JNJ, BAC, LIN, MRK) from the calibrated calls."))
story.append(ListFlowable([
    ListItem(para("<b>Regime-flip de-risking</b> — NIFTY trend tracked across runs; a flip triggers a 3-day half-Kelly window with a raised entry bar.", "Cell")),
    ListItem(para("<b>Volatility brake</b> — India VIX &gt; 25 forces a 2-day de-risk.", "Cell")),
    ListItem(para("<b>Self-throttling entry bar</b> — rolling 20-trade hit-rate moves the confidence threshold (bounded 50–70%): trade less when cold, press when hot.", "Cell")),
], bulletType="bullet", start="square", leftIndent=10))
story.append(Spacer(1, 2*mm))
story.append(para("Supervised ML: a first model trains on the 1,188-row labeled corpus (file: "
                  f'<a href="{GH}scripts/train_model.py" color="#2f6df0">scripts/train_model.py</a>). '
                  "It is <b>deliberately gated out of production</b> — with only a few distinct collection days the "
                  "purged test is empty and the high AUC reflects memorization, not skill. A ≥30-distinct-day gate "
                  "blocks live wiring. This is exactly why fixing the cron gap (Section 1) is the top priority.", "Small"))
story.append(PageBreak())

# ── 5. ARTIFACTS / LINKS ──────────────────────────────────────────────────────
story.append(Paragraph("5.  Artifacts &amp; Source Links", styles["H1"]))
story.append(para("All paths are clickable and resolve to the <font face='Courier'>main</font> branch."))
def arow(name, path, desc):
    return [link(name, path), para(desc, "Cell")]
arts = Table([
    [Paragraph("File", styles["CellW"]), Paragraph("What it is", styles["CellW"])],
    arow("shared/india_swing.py", "shared/india_swing.py", "NIFTY 50 positional engine (fundamentals + analyst consensus + India VIX)"),
    arow("shared/india_market.py", "shared/india_market.py", "NSE universe + IST trading-session state machine"),
    arow("shared/paper_trader.py", "shared/paper_trader.py", "Auto-mode paper book + market-shift adaptation controller"),
    arow("shared/system_health.py", "shared/system_health.py", "Uptime / learning / paper health → GREEN-AMBER-RED grade"),
    arow("shared/learning_loop.py", "shared/learning_loop.py", "Outcome correlation, weight tuning, calibration map"),
    arow("shared/data_lake.py", "shared/data_lake.py", "44-feature ML corpus + labeling"),
    arow("shared/breeze_client.py", "shared/breeze_client.py", "ICICI Breeze live quotes + hard-gated order tickets"),
    arow("streamlit/_stock_analysis.py", "streamlit/_stock_analysis.py", "6-step calibrated prediction engine"),
    arow("scripts/train_model.py", "scripts/train_model.py", "First supervised model (purged eval, live-wiring gate)"),
    arow("scripts/label_features.py", "scripts/label_features.py", "Daily labeling job (forward-return labels)"),
    arow("supabase/migrations/015_paper_trading.sql", "supabase/migrations/015_paper_trading.sql", "Paper-trades table (RLS: anon-read / service-write)"),
    arow("run_digest.sh", "run_digest.sh", "Cron runner — now mount-aware &amp; fail-loud"),
], colWidths=[68*mm, 92*mm])
arts.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
                          ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, LIGHT]),
                          ("GRID",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                          ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),6)]))
story.append(arts)
story.append(Spacer(1, 3*mm))

story.append(Paragraph("Key commits this session (most recent first)", styles["H2"]))
commits = Table([
    [Paragraph("Hash", styles["CellW"]), Paragraph("Change", styles["CellW"])],
    [para("cfec854", "CellB"), para("cron runner mount-aware + fails loudly (this audit's fix)", "Cell")],
    [para("7604caa", "CellB"), para("My Plan page — core-satellite plan with evidence gates + health", "Cell")],
    [para("4f56ab2", "CellB"), para("auto-mode paper trading with market-shift adaptation", "Cell")],
    [para("58611b1", "CellB"), para("India-first portfolio layer — swing engine, daily cron, Invest page", "Cell")],
    [para("349eefa", "CellB"), para("execute the learning loop — settle outcomes, learn weights, first model", "Cell")],
    [para("ad3da2c", "CellB"), para("ICICI Breeze integration — live quotes + hard-gated order tickets", "Cell")],
], colWidths=[24*mm, 136*mm])
commits.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),
                             ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, LIGHT]),
                             ("GRID",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                             ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),6)]))
story.append(commits)
story.append(PageBreak())

# ── 6. RECOMMENDATIONS ────────────────────────────────────────────────────────
story.append(Paragraph("6.  Prioritized Next Steps", styles["H1"]))
def prio(rank, color, title, body):
    t = Table([[Paragraph(rank, styles["CellW"]), Paragraph("<b>"+title+"</b><br/>"+body, styles["Cell"])]],
              colWidths=[16*mm, 144*mm])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(0,0),color),("BACKGROUND",(1,0),(1,0),colors.white),
                           ("BOX",(0,0),(-1,-1),0.4,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                           ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),("LEFTPADDING",(0,0),(-1,-1),8)]))
    return t
story.append(prio("P0", RED, "Eliminate the data gap (owner action).",
                  "Relocate the conda env to internal disk (43&nbsp;GB free) OR keep the SanDisk SSD permanently connected. "
                  "Until then, the mount-aware runner will alert via CRON_ALERT.log instead of failing silently."))
story.append(Spacer(1, 2*mm))
story.append(prio("P0", RED, "Keep the Mac awake during cron windows (06:00 / 12:00 / 17:00 IST).",
                  "Uptime is the single largest driver of accuracy — the My Plan health strip now grades this GREEN/AMBER/RED."))
story.append(Spacer(1, 2*mm))
story.append(prio("P1", AMBER, "Run Supabase migration 015 (paper_trades).",
                  "Makes the auto-mode paper book visible in the cloud app; the cron already writes it to a local fallback."))
story.append(Spacer(1, 2*mm))
story.append(prio("P1", AMBER, "Static IP &rarr; ICICI Breeze keys.",
                  "Unlocks real-time NSE pricing and a HOLD/ADD/TRIM review of your actual holdings. Integration is built and hard-gated."))
story.append(Spacer(1, 2*mm))
story.append(prio("P2", BLUE, "Let the system prove itself (~3–4 weeks), then decide.",
                  "Start the core index SIP now (needs no proof). The satellite stays on paper until the My Plan evidence gates pass; "
                  "do not change the engine mid-measurement so the paper book's verdict stays attributable."))
story.append(Spacer(1, 5*mm))
story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))
story.append(Spacer(1, 2*mm))
story.append(para("Bottom line: the decision engine, learning loop and India-first investment layer are sound and "
                  "measurably self-improving. The one thing standing between this system and stable, accurate output "
                  "is uninterrupted data collection — now made visible and recoverable, and one owner action away from "
                  "permanent.", "Small"))

# ── Footer ────────────────────────────────────────────────────────────────────
def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.4)
    canvas.line(20*mm, 14*mm, 190*mm, 14*mm)
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(SLATE)
    canvas.drawString(20*mm, 9*mm, "INTL Terminal — Executive Review · 14 Jun 2026 · github.com/git0ST/automation")
    canvas.drawRightString(190*mm, 9*mm, f"Page {doc.page}")
    canvas.restoreState()

doc = SimpleDocTemplate(OUT, pagesize=A4,
                        leftMargin=20*mm, rightMargin=20*mm,
                        topMargin=18*mm, bottomMargin=20*mm,
                        title="INTL Terminal — Executive System Review",
                        author="INTL Terminal")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("WROTE", OUT)
