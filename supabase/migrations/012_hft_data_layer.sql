-- Migration 012 — HFT Data Layer
-- Tables: pipeline_snapshots, intraday_bars, trade_signals, earnings_events
-- Run in Supabase SQL Editor (project: jptwbvigtgiffjqnctic)

-- ── Pipeline Snapshots (compressed data lake) ─────────────────────────────────
-- Every pipeline run writes a compressed snapshot for ML / backtesting.
-- Full payload stored as zlib-compressed base64 text; metadata queryable.
CREATE TABLE IF NOT EXISTS pipeline_snapshots (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  snapshot_at     TIMESTAMPTZ DEFAULT NOW(),
  regime          TEXT,
  srs             REAL,
  sentiment_bull  REAL,
  sentiment_bear  REAL,
  item_count      INTEGER DEFAULT 0,
  signal_count    INTEGER DEFAULT 0,
  alert_count     INTEGER DEFAULT 0,
  top_items       JSONB,      -- top 20 by terminal_score (title, source, score, sentiment)
  market_summary  JSONB,      -- all tickers (price, change_pct)
  macro_snapshot  JSONB,      -- FRED values at this moment
  compressed_data TEXT        -- zlib+base64 of full pipeline payload (for ML)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_at     ON pipeline_snapshots (snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_regime ON pipeline_snapshots (regime, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_srs    ON pipeline_snapshots (srs DESC);

ALTER TABLE pipeline_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_snapshots"    ON pipeline_snapshots FOR SELECT USING (true);
CREATE POLICY "service_write_snapshots" ON pipeline_snapshots FOR ALL USING (true);


-- ── Intraday Bars (5-minute OHLCV) ───────────────────────────────────────────
-- Sub-daily price resolution for VWAP, breakout, and momentum signals.
CREATE TABLE IF NOT EXISTS intraday_bars (
  id          BIGSERIAL PRIMARY KEY,
  ticker      TEXT        NOT NULL,
  bar_time    TIMESTAMPTZ NOT NULL,
  open        REAL,
  high        REAL,
  low         REAL,
  close       REAL,
  volume      REAL,
  vwap        REAL,         -- cumulative VWAP for the session
  vwap_dev    REAL,         -- (close - vwap) / vwap * 100  (% deviation)
  vol_ratio   REAL,         -- volume / avg_20bar_volume (unusual volume flag)
  rsi_14      REAL,
  UNIQUE (ticker, bar_time)
);

CREATE INDEX IF NOT EXISTS idx_intraday_ticker ON intraday_bars (ticker, bar_time DESC);
CREATE INDEX IF NOT EXISTS idx_intraday_time   ON intraday_bars (bar_time DESC);

ALTER TABLE intraday_bars ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_intraday"    ON intraday_bars FOR SELECT USING (true);
CREATE POLICY "service_write_intraday" ON intraday_bars FOR ALL USING (true);


-- ── Trade Signals (execution-grade) ──────────────────────────────────────────
-- Synthesized from technical + options + news + regime + fundamentals.
-- Each signal has entry, ATR-based stop, two targets, and Kelly fraction.
CREATE TABLE IF NOT EXISTS trade_signals (
  id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker          TEXT        NOT NULL,
  signal_type     TEXT,       -- breakout | mean_reversion | momentum | options_flow | event
  direction       TEXT,       -- long | short
  entry_price     REAL,
  stop_loss       REAL,       -- ATR(14)-based; max loss per share
  target_1        REAL,       -- 1.5R target
  target_2        REAL,       -- 2.5R target
  atr_14          REAL,
  risk_per_share  REAL,       -- entry - stop_loss
  kelly_fraction  REAL,       -- raw Kelly (uncapped)
  position_pct    REAL,       -- capped position size (% of portfolio)
  confluence      REAL,       -- 0-100 composite signal strength
  regime          TEXT,       -- regime at time of signal
  rationale       JSONB,      -- contributing signals + weights
  fired_at        TIMESTAMPTZ DEFAULT NOW(),
  expires_at      TIMESTAMPTZ,  -- 1 session (4pm ET same day) or next open
  status          TEXT DEFAULT 'open',  -- open | triggered | stopped | expired
  outcome_return  REAL        -- filled in by learning loop
);

CREATE INDEX IF NOT EXISTS idx_trade_signals_ticker  ON trade_signals (ticker, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_signals_status  ON trade_signals (status, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_signals_fired   ON trade_signals (fired_at DESC);

ALTER TABLE trade_signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_trade_signals"    ON trade_signals FOR SELECT USING (true);
CREATE POLICY "service_write_trade_signals" ON trade_signals FOR ALL USING (true);


-- ── Earnings Events ───────────────────────────────────────────────────────────
-- Upcoming earnings dates for event-risk awareness.
CREATE TABLE IF NOT EXISTS earnings_events (
  id            BIGSERIAL PRIMARY KEY,
  ticker        TEXT        NOT NULL,
  earnings_date DATE,
  eps_estimate  REAL,
  rev_estimate  REAL,
  days_away     INTEGER,    -- days until earnings (negative = past)
  fetched_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (ticker, earnings_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_date   ON earnings_events (earnings_date ASC);
CREATE INDEX IF NOT EXISTS idx_earnings_ticker ON earnings_events (ticker);

ALTER TABLE earnings_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_earnings"    ON earnings_events FOR SELECT USING (true);
CREATE POLICY "service_write_earnings" ON earnings_events FOR ALL USING (true);
