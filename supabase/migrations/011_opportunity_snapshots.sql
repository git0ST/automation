-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 011: Opportunity scanner snapshots  (IDEMPOTENT)
--
-- Pipeline cron runs the Opportunity Scanner across the watchlist on every
-- run and writes the result here. Streamlit reads from this table → users
-- never wait for a 30-second scan; they always see fresh-from-cron data.
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS opportunity_snapshots (
  id              BIGSERIAL PRIMARY KEY,
  scan_id         TEXT NOT NULL,              -- UUID per scan run (groups all tickers in one scan)
  ticker          TEXT NOT NULL,
  -- Live data
  price           REAL,
  chg_1d          REAL,
  ret_3m          REAL,
  ret_6m          REAL,
  ret_12m         REAL,
  rsi_14          REAL,
  vs_sma_50       REAL,
  vs_sma_200      REAL,
  -- Prediction
  direction       TEXT,                       -- bullish | bearish | neutral
  confidence      REAL,
  rationale       TEXT,
  components      JSONB,                      -- list of {name, direction, strength, weight}
  vol_regime      TEXT,
  tech_votes      INTEGER,
  -- Quant
  quant_score     REAL,
  quant_grade     TEXT,
  factors         JSONB,                      -- {value, growth, profit, momentum, revisions}
  -- Strategy matches
  strategies      JSONB,                      -- list of matched strategy names + horizons
  -- Metadata
  sector          TEXT,
  regime_at_scan  TEXT,
  scanned_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opp_snap_scan_id    ON opportunity_snapshots (scan_id);
CREATE INDEX IF NOT EXISTS idx_opp_snap_scanned_at ON opportunity_snapshots (scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_opp_snap_ticker     ON opportunity_snapshots (ticker, scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_opp_snap_conf       ON opportunity_snapshots (direction, confidence DESC);

ALTER TABLE opportunity_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_opps"   ON opportunity_snapshots;
DROP POLICY IF EXISTS "service_all_opps" ON opportunity_snapshots;
CREATE POLICY "anon_read_opps"   ON opportunity_snapshots FOR SELECT TO anon USING (true);
CREATE POLICY "service_all_opps" ON opportunity_snapshots FOR ALL    TO service_role USING (true) WITH CHECK (true);


-- ── Convenience view: latest scan only ──────────────────────────────────────
DROP VIEW IF EXISTS v_latest_opportunities;
CREATE VIEW v_latest_opportunities
WITH (security_invoker = on) AS
WITH latest_scan AS (
  SELECT scan_id, MAX(scanned_at) AS scanned_at
    FROM opportunity_snapshots
   GROUP BY scan_id
   ORDER BY MAX(scanned_at) DESC
   LIMIT 1
)
SELECT s.*
  FROM opportunity_snapshots s
  JOIN latest_scan l ON s.scan_id = l.scan_id;

GRANT SELECT ON v_latest_opportunities TO anon, authenticated;


-- ── Auto-cleanup: keep only last 30 days of snapshots ───────────────────────
CREATE OR REPLACE FUNCTION public.cleanup_old_snapshots()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  deleted INTEGER;
BEGIN
  DELETE FROM public.opportunity_snapshots
   WHERE scanned_at < NOW() - INTERVAL '30 days';
  GET DIAGNOSTICS deleted = ROW_COUNT;
  RETURN deleted;
END;
$$;

REVOKE ALL ON FUNCTION public.cleanup_old_snapshots() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_old_snapshots() TO service_role;


-- ── Verification ─────────────────────────────────────────────────────────────
-- SELECT scan_id, COUNT(*), MAX(scanned_at) FROM opportunity_snapshots GROUP BY scan_id ORDER BY MAX(scanned_at) DESC LIMIT 5;
-- SELECT * FROM v_latest_opportunities ORDER BY confidence DESC LIMIT 10;
