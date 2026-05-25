-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 003: Intelligence Layer Tables
-- Regime snapshots + Systemic Risk Score history
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Regime snapshots ─────────────────────────────────────────────────────────
-- Stores BlackRock Aladdin-style regime classifications over time.
-- Enables backtesting, regime transition tracking, and historical analytics.

CREATE TABLE IF NOT EXISTS regime_snapshots (
  id              BIGSERIAL PRIMARY KEY,
  regime          TEXT NOT NULL,           -- goldilocks | reflation | stagflation | deflation
  label           TEXT NOT NULL,           -- Display label
  color           TEXT,
  description     TEXT,
  confidence_pct  REAL DEFAULT 0,
  growth_score    REAL DEFAULT 0,
  inflation_score REAL DEFAULT 0,
  transition_risk TEXT DEFAULT 'low',      -- low | medium | high
  favors          TEXT[] DEFAULT '{}',
  avoids          TEXT[] DEFAULT '{}',
  signals         JSONB DEFAULT '[]',      -- MacroSignal array
  captured_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regime_captured_at ON regime_snapshots (captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_regime_regime       ON regime_snapshots (regime);

-- Row-level security
ALTER TABLE regime_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_regime" ON regime_snapshots
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_regime" ON regime_snapshots
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── Systemic Risk Score history ───────────────────────────────────────────────
-- Tracks the composite Systemic Risk Score (0-100) and its factor breakdown.
-- Enables risk trend analysis and anomaly detection.

CREATE TABLE IF NOT EXISTS risk_scores (
  id          BIGSERIAL PRIMARY KEY,
  srs         REAL NOT NULL,               -- 0-100 composite score
  level       TEXT NOT NULL,               -- Low | Moderate | Elevated | High
  color       TEXT,
  top_risks   TEXT[] DEFAULT '{}',         -- Top risk narrative strings
  factors     JSONB DEFAULT '[]',          -- RiskFactor array with scores + weights
  captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_captured_at ON risk_scores (captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_level        ON risk_scores (level);

-- Row-level security
ALTER TABLE risk_scores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_risk" ON risk_scores
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_risk" ON risk_scores
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── Credit spreads history ─────────────────────────────────────────────────────
-- Stores ICE BofA credit spread readings (HY OAS, IG OAS, TED, etc.)
-- for trend tracking and regime input auditing.

CREATE TABLE IF NOT EXISTS credit_spreads (
  id          BIGSERIAL PRIMARY KEY,
  series_id   TEXT NOT NULL,               -- BAMLH0A0HYM2, BAMLC0A0CM, etc.
  name        TEXT,
  value       REAL NOT NULL,               -- Raw FRED value (percentage points)
  unit        TEXT DEFAULT 'bps',
  stress      TEXT,                        -- benign | caution | elevated | crisis
  period      TEXT,                        -- FRED reporting period (YYYY-MM-DD)
  captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credit_series     ON credit_spreads (series_id);
CREATE INDEX IF NOT EXISTS idx_credit_captured_at ON credit_spreads (captured_at DESC);

ALTER TABLE credit_spreads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_credit" ON credit_spreads
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_credit" ON credit_spreads
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── Summary view: latest regime + risk ───────────────────────────────────────
-- Convenience view returning the most recent snapshot of each.

CREATE OR REPLACE VIEW v_intelligence_latest AS
SELECT
  r.regime,
  r.label           AS regime_label,
  r.confidence_pct,
  r.transition_risk,
  r.growth_score,
  r.inflation_score,
  r.favors,
  r.captured_at     AS regime_at,
  k.srs,
  k.level           AS risk_level,
  k.top_risks,
  k.captured_at     AS risk_at
FROM
  (SELECT * FROM regime_snapshots ORDER BY captured_at DESC LIMIT 1) r
  CROSS JOIN
  (SELECT * FROM risk_scores ORDER BY captured_at DESC LIMIT 1) k;

GRANT SELECT ON v_intelligence_latest TO anon;
