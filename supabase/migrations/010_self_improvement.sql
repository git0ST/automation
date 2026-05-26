-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 010: Self-improvement layer  (IDEMPOTENT)
--
-- Adds the infrastructure for the system to learn from its own predictions:
--   1. Tag every prediction with strategy + regime at prediction time
--   2. Store learned model weights, regime-aware
--   3. Track per-strategy, per-regime, per-source hit rates
--
-- After ~14 days of data, weight_optimizer can recommend new component
-- weights based on actual hit rates. Confidence becomes calibrated to
-- the system's observed accuracy, not its theoretical accuracy.
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Add learning columns to predictions ──────────────────────────────────────
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS strategy_name  TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS regime_at_pred TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS srs_at_pred    REAL;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS sector         TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS horizon        TEXT;

CREATE INDEX IF NOT EXISTS idx_predictions_strategy
  ON predictions (strategy_name, predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_regime
  ON predictions (regime_at_pred, predicted_at DESC);


-- ── Model weights table — versioned, regime-aware ───────────────────────────
CREATE TABLE IF NOT EXISTS model_weights (
  id            BIGSERIAL PRIMARY KEY,
  version       TEXT NOT NULL,                -- e.g. "v1.0", "v1.1-learned"
  regime        TEXT,                          -- null = default; else goldilocks/reflation/...
  -- Composite prediction weights (sum to 1.0)
  technical_w   REAL DEFAULT 0.35,
  sentiment_w   REAL DEFAULT 0.25,
  analyst_w     REAL DEFAULT 0.25,
  vol_w         REAL DEFAULT 0.15,
  -- Calibration: confidence multiplier per regime
  conf_multiplier REAL DEFAULT 1.0,
  -- Provenance
  trained_on    INTEGER DEFAULT 0,             -- N predictions used to train
  hit_rate_7d   REAL,                           -- baseline hit rate
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  active        BOOLEAN DEFAULT TRUE,
  notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_model_weights_active
  ON model_weights (active, regime);

ALTER TABLE model_weights ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_read_mw"   ON model_weights;
DROP POLICY IF EXISTS "service_all_mw" ON model_weights;
CREATE POLICY "anon_read_mw"   ON model_weights FOR SELECT TO anon USING (true);
CREATE POLICY "service_all_mw" ON model_weights FOR ALL    TO service_role USING (true) WITH CHECK (true);

-- Seed default weights (matches the original engine — pre-learning baseline)
INSERT INTO model_weights (version, regime, technical_w, sentiment_w, analyst_w, vol_w,
                            conf_multiplier, active, notes)
SELECT 'v1.0-baseline', NULL, 0.35, 0.25, 0.25, 0.15, 1.0, TRUE,
       'Initial weights from spec'
WHERE NOT EXISTS (SELECT 1 FROM model_weights WHERE version = 'v1.0-baseline');


-- ── Per-strategy performance view ────────────────────────────────────────────
DROP VIEW IF EXISTS v_strategy_performance;
CREATE VIEW v_strategy_performance
WITH (security_invoker = on) AS
SELECT
  strategy_name,
  direction,
  COUNT(*)                                                AS n_predictions,
  COUNT(*) FILTER (WHERE return_7d IS NOT NULL)           AS n_settled,
  ROUND(AVG(return_7d)::numeric, 3)                       AS avg_return_7d,
  ROUND(AVG(return_30d)::numeric, 3)                      AS avg_return_30d,
  ROUND(AVG(max_favorable)::numeric, 3)                   AS avg_mfe,
  ROUND(AVG(max_adverse)::numeric, 3)                     AS avg_mae,
  -- Hit rate: bullish call gained, bearish call fell
  ROUND((COUNT(*) FILTER (
    WHERE (direction = 'bullish' AND return_7d > 0)
       OR (direction = 'bearish' AND return_7d < 0)
  )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))::numeric, 3) AS hit_rate_7d,
  ROUND(AVG(confidence_pct)::numeric, 1)                  AS avg_confidence
FROM predictions
WHERE strategy_name IS NOT NULL
GROUP BY strategy_name, direction
ORDER BY n_predictions DESC;

GRANT SELECT ON v_strategy_performance TO anon, authenticated;


-- ── Per-regime performance view ──────────────────────────────────────────────
DROP VIEW IF EXISTS v_regime_performance;
CREATE VIEW v_regime_performance
WITH (security_invoker = on) AS
SELECT
  COALESCE(regime_at_pred, 'unknown')                     AS regime,
  direction,
  COUNT(*)                                                AS n_predictions,
  COUNT(*) FILTER (WHERE return_7d IS NOT NULL)           AS n_settled,
  ROUND(AVG(return_7d)::numeric, 3)                       AS avg_return_7d,
  ROUND((COUNT(*) FILTER (
    WHERE (direction = 'bullish' AND return_7d > 0)
       OR (direction = 'bearish' AND return_7d < 0)
  )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))::numeric, 3) AS hit_rate_7d
FROM predictions
GROUP BY 1, 2
ORDER BY 1, 2;

GRANT SELECT ON v_regime_performance TO anon, authenticated;


-- ── Calibration view (confidence band → actual hit rate) ─────────────────────
DROP VIEW IF EXISTS v_calibration;
CREATE VIEW v_calibration
WITH (security_invoker = on) AS
SELECT
  CASE
    WHEN confidence_pct >= 80 THEN '80-100%'
    WHEN confidence_pct >= 70 THEN '70-79%'
    WHEN confidence_pct >= 60 THEN '60-69%'
    WHEN confidence_pct >= 50 THEN '50-59%'
    ELSE '<50%'
  END AS confidence_band,
  direction,
  COUNT(*)                                          AS n,
  COUNT(*) FILTER (WHERE return_7d IS NOT NULL)     AS n_settled,
  ROUND(AVG(return_7d)::numeric, 3)                 AS avg_return_7d,
  ROUND((COUNT(*) FILTER (
    WHERE (direction = 'bullish' AND return_7d > 0)
       OR (direction = 'bearish' AND return_7d < 0)
  )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))::numeric, 3) AS hit_rate_7d
FROM predictions
WHERE confidence_pct IS NOT NULL
GROUP BY 1, direction
ORDER BY 1, direction;

GRANT SELECT ON v_calibration TO anon, authenticated;


-- ── Recommendation: optimize weights from outcome data ──────────────────────
-- This is the core learning function. Calculates new weights based on which
-- signal components actually predicted moves correctly.
CREATE OR REPLACE FUNCTION public.recommend_model_weights(
  p_min_observations INTEGER DEFAULT 20,
  p_lookback_days    INTEGER DEFAULT 90
)
RETURNS TABLE(
  technical_w   REAL,
  sentiment_w   REAL,
  analyst_w     REAL,
  vol_w         REAL,
  trained_on    INTEGER,
  hit_rate      REAL,
  notes         TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_tech_acc    REAL := 0;
  v_sent_acc    REAL := 0;
  v_analyst_acc REAL := 0;
  v_total       INTEGER := 0;
  v_hit_rate    REAL := 0;
  v_norm        REAL;
BEGIN
  -- For each component, compute accuracy = % of times the component's
  -- direction matched the eventual 7d return direction.

  -- Technical accuracy
  SELECT
    COALESCE(
      (COUNT(*) FILTER (
        WHERE (tech_signal = 'bullish' AND return_7d > 0)
           OR (tech_signal = 'bearish' AND return_7d < 0)
      )::REAL / NULLIF(COUNT(*) FILTER (
        WHERE tech_signal IN ('bullish','bearish') AND return_7d IS NOT NULL
      ), 0)), 0)
  INTO v_tech_acc
  FROM public.predictions
  WHERE predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  -- Sentiment accuracy
  SELECT
    COALESCE(
      (COUNT(*) FILTER (
        WHERE (sent_signal = 'bullish' AND return_7d > 0)
           OR (sent_signal = 'bearish' AND return_7d < 0)
      )::REAL / NULLIF(COUNT(*) FILTER (
        WHERE sent_signal IN ('bullish','bearish') AND return_7d IS NOT NULL
      ), 0)), 0)
  INTO v_sent_acc
  FROM public.predictions
  WHERE predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  -- Analyst accuracy
  SELECT
    COALESCE(
      (COUNT(*) FILTER (
        WHERE (analyst_signal = 'bullish' AND return_7d > 0)
           OR (analyst_signal = 'bearish' AND return_7d < 0)
      )::REAL / NULLIF(COUNT(*) FILTER (
        WHERE analyst_signal IN ('bullish','bearish') AND return_7d IS NOT NULL
      ), 0)), 0)
  INTO v_analyst_acc
  FROM public.predictions
  WHERE predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  -- Overall stats
  SELECT
    COUNT(*) FILTER (WHERE return_7d IS NOT NULL),
    (COUNT(*) FILTER (
      WHERE (direction = 'bullish' AND return_7d > 0)
         OR (direction = 'bearish' AND return_7d < 0)
    )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))
  INTO v_total, v_hit_rate
  FROM public.predictions
  WHERE predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  -- If insufficient data, return baseline weights
  IF v_total < p_min_observations THEN
    RETURN QUERY SELECT 0.35::REAL, 0.25::REAL, 0.25::REAL, 0.15::REAL,
                        v_total, v_hit_rate,
                        ('Not enough data (' || v_total || ' settled, need '
                         || p_min_observations || ')')::TEXT;
    RETURN;
  END IF;

  -- Normalize accuracies to weights, leaving vol_w fixed at 0.15
  v_norm := v_tech_acc + v_sent_acc + v_analyst_acc;
  IF v_norm > 0 THEN
    RETURN QUERY SELECT
      ((v_tech_acc    / v_norm) * 0.85)::REAL,
      ((v_sent_acc    / v_norm) * 0.85)::REAL,
      ((v_analyst_acc / v_norm) * 0.85)::REAL,
      0.15::REAL,
      v_total,
      v_hit_rate,
      ('Learned from ' || v_total || ' settled predictions over '
       || p_lookback_days || ' days')::TEXT;
  ELSE
    RETURN QUERY SELECT 0.35::REAL, 0.25::REAL, 0.25::REAL, 0.15::REAL,
                        v_total, v_hit_rate, 'Zero signal accuracy — using baseline'::TEXT;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.recommend_model_weights(INTEGER, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.recommend_model_weights(INTEGER, INTEGER) TO service_role;


-- ── Verification queries ─────────────────────────────────────────────────────
-- SELECT * FROM model_weights WHERE active = true;
-- SELECT * FROM v_strategy_performance;
-- SELECT * FROM v_regime_performance;
-- SELECT * FROM v_calibration;
-- SELECT * FROM recommend_model_weights(20, 90);
