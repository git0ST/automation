-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 009: Prediction track record + alerts  (IDEMPOTENT)
--
-- Logs every prediction the system makes so we can:
--   1. Show users a backtest: "Our bullish calls returned +X% on avg over Y days"
--   2. Calibrate confidence: do 80%-confidence calls actually beat 60%-confidence?
--   3. Tune adaptive weights based on what predicted moves and what didn't
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Prediction log ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
  id              BIGSERIAL PRIMARY KEY,
  ticker          TEXT NOT NULL,
  direction       TEXT NOT NULL,             -- bullish | bearish | neutral
  confidence_pct  REAL NOT NULL,
  source_page     TEXT,                      -- opportunities | stock_detail | scan
  predicted_at    TIMESTAMPTZ DEFAULT NOW(),
  price_at_pred   REAL,                      -- price when prediction was made
  -- Composite components for calibration
  tech_signal     TEXT,                      -- bullish | bearish | neutral
  tech_strength   REAL,
  sent_signal     TEXT,
  sent_strength   REAL,
  analyst_signal  TEXT,
  analyst_strength REAL,
  vol_regime      TEXT,                      -- elevated | normal | compressed
  quant_score     REAL,
  quant_grade     TEXT,
  -- Outcomes (filled by daily correlation job)
  return_1d       REAL,
  return_3d       REAL,
  return_7d       REAL,
  return_30d      REAL,
  max_favorable   REAL,                      -- MFE — best move in direction
  max_adverse     REAL,                      -- MAE — worst move against
  correlated_at   TIMESTAMPTZ                -- when outcomes were filled
);

CREATE INDEX IF NOT EXISTS idx_predictions_ticker
  ON predictions (ticker, predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_predicted_at
  ON predictions (predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_direction_conf
  ON predictions (direction, confidence_pct DESC);

ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_pred"     ON predictions;
DROP POLICY IF EXISTS "anon_write_pred"    ON predictions;
DROP POLICY IF EXISTS "service_all_pred"   ON predictions;
CREATE POLICY "anon_read_pred"   ON predictions FOR SELECT TO anon USING (true);
CREATE POLICY "anon_write_pred"  ON predictions FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "service_all_pred" ON predictions FOR ALL    TO service_role USING (true) WITH CHECK (true);


-- ── Alert rules ──────────────────────────────────────────────────────────────
-- User-defined alert conditions. Triggered server-side or by Streamlit poll.
CREATE TABLE IF NOT EXISTS alert_rules (
  id              BIGSERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  rule_type       TEXT NOT NULL,             -- price_above | price_below | rsi_above |
                                              -- rsi_below | srs_above | sentiment_shift |
                                              -- hot_entity | regime_change
  ticker          TEXT,                      -- nullable for macro alerts
  threshold       REAL,
  active          BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  last_triggered  TIMESTAMPTZ,
  triggered_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alert_rules_active ON alert_rules (active, ticker);

ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_all_alerts" ON alert_rules;
CREATE POLICY "anon_all_alerts" ON alert_rules FOR ALL TO anon USING (true) WITH CHECK (true);


-- ── Triggered alerts log ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_events (
  id           BIGSERIAL PRIMARY KEY,
  rule_id      BIGINT REFERENCES alert_rules(id) ON DELETE CASCADE,
  ticker       TEXT,
  message      TEXT NOT NULL,
  level        TEXT DEFAULT 'info',         -- info | warning | critical
  data         JSONB,
  triggered_at TIMESTAMPTZ DEFAULT NOW(),
  acknowledged BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_alert_events_triggered
  ON alert_events (triggered_at DESC, acknowledged);

ALTER TABLE alert_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_all_events" ON alert_events;
CREATE POLICY "anon_all_events" ON alert_events FOR ALL TO anon USING (true) WITH CHECK (true);


-- ── Correlation function: fill outcomes from yfinance after N days ──────────
-- Note: actually pulling forward prices requires Python — this SQL function is
-- a placeholder that the pipeline calls to fill returns from market_snapshots.
CREATE OR REPLACE FUNCTION public.correlate_predictions()
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  rec     RECORD;
  px_now  REAL;
  updated INTEGER := 0;
BEGIN
  FOR rec IN
    SELECT id, ticker, predicted_at, price_at_pred
      FROM public.predictions
     WHERE correlated_at IS NULL
       AND predicted_at < NOW() - INTERVAL '1 day'
       AND price_at_pred IS NOT NULL
       AND price_at_pred > 0
     LIMIT 200
  LOOP
    SELECT close INTO px_now
      FROM public.market_snapshots
     WHERE ticker = rec.ticker
       AND snapshot_at >= rec.predicted_at + INTERVAL '1 day'
     ORDER BY snapshot_at ASC
     LIMIT 1;

    IF px_now IS NOT NULL AND px_now > 0 THEN
      UPDATE public.predictions
         SET return_1d     = (px_now / rec.price_at_pred - 1) * 100,
             correlated_at = NOW()
       WHERE id = rec.id;
      updated := updated + 1;
    END IF;
  END LOOP;
  RETURN 'Correlated ' || updated || ' predictions at ' || NOW()::TEXT;
END;
$$;

REVOKE ALL ON FUNCTION public.correlate_predictions() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.correlate_predictions() TO service_role;


-- ── Hit-rate summary view ────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_prediction_stats;
CREATE VIEW v_prediction_stats
WITH (security_invoker = on) AS
SELECT
  direction,
  CASE WHEN confidence_pct >= 75 THEN 'High (75+)'
       WHEN confidence_pct >= 60 THEN 'Medium (60-74)'
       WHEN confidence_pct >= 40 THEN 'Low (40-59)'
       ELSE 'Very low (<40)' END AS confidence_band,
  COUNT(*)                                    AS n_predictions,
  ROUND(AVG(return_1d)::numeric, 3)           AS avg_return_1d,
  ROUND(AVG(return_7d)::numeric, 3)           AS avg_return_7d,
  ROUND(AVG(return_30d)::numeric, 3)          AS avg_return_30d,
  COUNT(*) FILTER (
    WHERE (direction = 'bullish' AND return_7d > 0)
       OR (direction = 'bearish' AND return_7d < 0)
  )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0)
                                              AS hit_rate_7d
FROM predictions
WHERE return_1d IS NOT NULL
GROUP BY direction, confidence_band;

GRANT SELECT ON v_prediction_stats TO anon, authenticated;


-- ── Verification ─────────────────────────────────────────────────────────────
-- SELECT * FROM predictions ORDER BY predicted_at DESC LIMIT 5;
-- SELECT * FROM v_prediction_stats;
-- SELECT * FROM alert_rules WHERE active = true;
-- SELECT * FROM alert_events ORDER BY triggered_at DESC LIMIT 10;
