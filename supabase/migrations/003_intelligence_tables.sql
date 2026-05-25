-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 003: Intelligence Layer Tables   (IDEMPOTENT — safe to re-run)
-- Regime snapshots + Systemic Risk Score history + Credit spreads
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Regime snapshots ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS regime_snapshots (
  id              BIGSERIAL PRIMARY KEY,
  regime          TEXT NOT NULL,           -- goldilocks | reflation | stagflation | deflation
  label           TEXT NOT NULL,
  color           TEXT,
  description     TEXT,
  confidence_pct  REAL DEFAULT 0,
  growth_score    REAL DEFAULT 0,
  inflation_score REAL DEFAULT 0,
  transition_risk TEXT DEFAULT 'low',      -- low | medium | high
  favors          TEXT[] DEFAULT '{}',
  avoids          TEXT[] DEFAULT '{}',
  signals         JSONB DEFAULT '[]',
  captured_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regime_captured_at ON regime_snapshots (captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_regime_regime      ON regime_snapshots (regime);

ALTER TABLE regime_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_regime"   ON regime_snapshots;
DROP POLICY IF EXISTS "service_all_regime" ON regime_snapshots;

CREATE POLICY "anon_read_regime" ON regime_snapshots
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_regime" ON regime_snapshots
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── Systemic Risk Score history ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_scores (
  id          BIGSERIAL PRIMARY KEY,
  srs         REAL NOT NULL,               -- 0-100 composite score
  level       TEXT NOT NULL,               -- Low | Moderate | Elevated | High
  color       TEXT,
  top_risks   TEXT[] DEFAULT '{}',
  factors     JSONB DEFAULT '[]',
  captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_captured_at ON risk_scores (captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_level       ON risk_scores (level);

ALTER TABLE risk_scores ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_risk"   ON risk_scores;
DROP POLICY IF EXISTS "service_all_risk" ON risk_scores;

CREATE POLICY "anon_read_risk" ON risk_scores
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_risk" ON risk_scores
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── Credit spreads history ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS credit_spreads (
  id          BIGSERIAL PRIMARY KEY,
  series_id   TEXT NOT NULL,               -- BAMLH0A0HYM2, BAMLC0A0CM, etc.
  name        TEXT,
  value       REAL NOT NULL,               -- raw FRED value (percentage points)
  unit        TEXT DEFAULT 'bps',
  stress      TEXT,                        -- benign | caution | elevated | crisis
  period      TEXT,
  captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credit_series      ON credit_spreads (series_id);
CREATE INDEX IF NOT EXISTS idx_credit_captured_at ON credit_spreads (captured_at DESC);

ALTER TABLE credit_spreads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_credit"   ON credit_spreads;
DROP POLICY IF EXISTS "service_all_credit" ON credit_spreads;

CREATE POLICY "anon_read_credit" ON credit_spreads
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_credit" ON credit_spreads
  FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ── Summary view: latest regime + risk ────────────────────────────────────────
-- SECURITY INVOKER ensures the view respects the calling user's RLS.
-- Without it, Postgres defaults to SECURITY DEFINER (creator's perms).

DROP VIEW IF EXISTS v_intelligence_latest;

CREATE OR REPLACE VIEW v_intelligence_latest
WITH (security_invoker = on) AS
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

GRANT SELECT ON v_intelligence_latest TO anon, authenticated;


-- ── Verification (run these to confirm migration succeeded) ───────────────────
-- SELECT * FROM regime_snapshots LIMIT 1;
-- SELECT * FROM risk_scores LIMIT 1;
-- SELECT * FROM credit_spreads LIMIT 1;
