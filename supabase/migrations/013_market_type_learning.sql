-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 013: Market-type learning layer  (IDEMPOTENT)
--
-- Extends the self-improvement loop with per-market-type awareness:
--   1. Tag predictions with market_type + cross_market_factor
--   2. Per-market performance views for equity vs crypto vs forex vs commodity
--   3. Per-market model weights so the engine learns separately per asset class
--   4. v_market_expectancy: EV-style view for portfolio allocation decisions
--
-- After running this migration:
--   • Every signal fired by signal_engine_v2 is tagged with market_type
--   • recommend_model_weights() continues to work — it reads ALL predictions
--   • New: recommend_market_weights(market_type) gives per-market tuning
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Extend predictions with market context ───────────────────────────────────
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS market_type        TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS cross_mkt_factor   REAL;

-- Backfill market_type for existing equity predictions (no market_type = equity)
UPDATE predictions
  SET market_type = 'equity'
  WHERE market_type IS NULL;

CREATE INDEX IF NOT EXISTS idx_predictions_market_type
  ON predictions (market_type, predicted_at DESC);

CREATE INDEX IF NOT EXISTS idx_predictions_market_regime
  ON predictions (market_type, regime_at_pred, predicted_at DESC);


-- ── Extend model_weights with market_type scoping ────────────────────────────
ALTER TABLE model_weights ADD COLUMN IF NOT EXISTS market_type TEXT;

-- Per-market baselines aligned with MARKET_PROFILES in market_router.py
INSERT INTO model_weights (version, market_type, regime,
  technical_w, sentiment_w, analyst_w, vol_w, conf_multiplier, active, notes)
SELECT v.version, v.mtype, NULL,
       v.tech, v.sent, v.analyst, v.vol, 1.0, TRUE,
       ('Baseline for ' || v.mtype)
FROM (VALUES
  ('v1.0-crypto',    'crypto',    0.45, 0.35, 0.00, 0.20),
  ('v1.0-forex',     'forex',     0.30, 0.15, 0.05, 0.50),
  ('v1.0-commodity', 'commodity', 0.35, 0.20, 0.10, 0.35),
  ('v1.0-index',     'index',     0.40, 0.20, 0.00, 0.40),
  ('v1.0-bond',      'bond',      0.25, 0.10, 0.00, 0.65)
) AS v(version, mtype, tech, sent, analyst, vol)
WHERE NOT EXISTS (
  SELECT 1 FROM model_weights WHERE version = v.version
);


-- ── Per-market performance view ───────────────────────────────────────────────
DROP VIEW IF EXISTS v_market_performance;
CREATE VIEW v_market_performance
WITH (security_invoker = on) AS
SELECT
  COALESCE(market_type, 'equity')                          AS market_type,
  direction,
  COUNT(*)                                                 AS n_predictions,
  COUNT(*) FILTER (WHERE return_7d IS NOT NULL)            AS n_settled,
  ROUND(AVG(return_7d)::numeric, 4)                        AS avg_return_7d,
  ROUND(AVG(return_30d)::numeric, 4)                       AS avg_return_30d,
  ROUND(AVG(max_favorable)::numeric, 4)                    AS avg_mfe,
  ROUND(AVG(max_adverse)::numeric, 4)                      AS avg_mae,
  ROUND((COUNT(*) FILTER (
    WHERE (direction IN ('bullish','long')  AND return_7d > 0)
       OR (direction IN ('bearish','short') AND return_7d < 0)
  )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))::numeric, 3) AS hit_rate_7d,
  ROUND(AVG(confidence_pct)::numeric, 1)                   AS avg_confidence
FROM predictions
GROUP BY 1, 2
ORDER BY 1, 2;

GRANT SELECT ON v_market_performance TO anon, authenticated;


-- ── Per-market expectancy view — EV-style for portfolio allocation ──────────
DROP VIEW IF EXISTS v_market_expectancy;
CREATE VIEW v_market_expectancy
WITH (security_invoker = on) AS
SELECT
  COALESCE(market_type, 'equity')                    AS market_type,
  COALESCE(regime_at_pred, 'unknown')                AS regime,
  COUNT(*) FILTER (WHERE return_7d IS NOT NULL)      AS n_settled,
  ROUND(AVG(return_7d)::numeric, 4)                  AS avg_return_7d,
  ROUND(AVG(max_favorable)::numeric, 4)              AS avg_mfe,
  ROUND(AVG(max_adverse)::numeric, 4)                AS avg_mae,
  -- Profit factor: avg win / avg loss
  ROUND((AVG(return_7d) FILTER (WHERE return_7d > 0) /
    NULLIF(ABS(AVG(return_7d) FILTER (WHERE return_7d < 0)), 0))::numeric, 2) AS profit_factor,
  -- Hit rate
  ROUND((COUNT(*) FILTER (
    WHERE (direction IN ('bullish','long')  AND return_7d > 0)
       OR (direction IN ('bearish','short') AND return_7d < 0)
  )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))::numeric, 3) AS hit_rate,
  -- Expectancy = (hit_rate × avg_win) + ((1-hit_rate) × avg_loss)
  ROUND((
    (COUNT(*) FILTER (
      WHERE (direction IN ('bullish','long')  AND return_7d > 0)
         OR (direction IN ('bearish','short') AND return_7d < 0)
    )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))
    * COALESCE(AVG(return_7d) FILTER (WHERE return_7d > 0), 0)
    +
    (1.0 - (COUNT(*) FILTER (
      WHERE (direction IN ('bullish','long')  AND return_7d > 0)
         OR (direction IN ('bearish','short') AND return_7d < 0)
    )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0)))
    * COALESCE(AVG(return_7d) FILTER (WHERE return_7d < 0), 0)
  )::numeric, 4) AS expectancy
FROM predictions
WHERE return_7d IS NOT NULL
GROUP BY 1, 2
ORDER BY expectancy DESC NULLS LAST;

GRANT SELECT ON v_market_expectancy TO anon, authenticated;


-- ── Per-market weight recommendation function ──────────────────────────────
CREATE OR REPLACE FUNCTION public.recommend_market_weights(
  p_market_type      TEXT DEFAULT 'equity',
  p_min_observations INTEGER DEFAULT 15,
  p_lookback_days    INTEGER DEFAULT 90
)
RETURNS TABLE(
  market_type   TEXT,
  technical_w   REAL,
  sentiment_w   REAL,
  analyst_w     REAL,
  vol_w         REAL,
  trained_on    INTEGER,
  hit_rate      REAL,
  expectancy    REAL,
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
  v_expectancy  REAL := 0;
  v_norm        REAL;
BEGIN
  -- Technical accuracy for this market type
  SELECT COALESCE(
    COUNT(*) FILTER (
      WHERE (tech_signal = 'bullish' AND return_7d > 0)
         OR (tech_signal = 'bearish' AND return_7d < 0)
    )::REAL / NULLIF(COUNT(*) FILTER (
      WHERE tech_signal IN ('bullish','bearish') AND return_7d IS NOT NULL
    ), 0), 0)
  INTO v_tech_acc
  FROM public.predictions
  WHERE COALESCE(market_type, 'equity') = p_market_type
    AND predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  -- Sentiment accuracy
  SELECT COALESCE(
    COUNT(*) FILTER (
      WHERE (sent_signal = 'bullish' AND return_7d > 0)
         OR (sent_signal = 'bearish' AND return_7d < 0)
    )::REAL / NULLIF(COUNT(*) FILTER (
      WHERE sent_signal IN ('bullish','bearish') AND return_7d IS NOT NULL
    ), 0), 0)
  INTO v_sent_acc
  FROM public.predictions
  WHERE COALESCE(market_type, 'equity') = p_market_type
    AND predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  -- Analyst accuracy
  SELECT COALESCE(
    COUNT(*) FILTER (
      WHERE (analyst_signal = 'bullish' AND return_7d > 0)
         OR (analyst_signal = 'bearish' AND return_7d < 0)
    )::REAL / NULLIF(COUNT(*) FILTER (
      WHERE analyst_signal IN ('bullish','bearish') AND return_7d IS NOT NULL
    ), 0), 0)
  INTO v_analyst_acc
  FROM public.predictions
  WHERE COALESCE(market_type, 'equity') = p_market_type
    AND predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  -- Overall settled count and hit rate
  SELECT
    COUNT(*) FILTER (WHERE return_7d IS NOT NULL),
    COALESCE(COUNT(*) FILTER (
      WHERE (direction IN ('bullish','long')  AND return_7d > 0)
         OR (direction IN ('bearish','short') AND return_7d < 0)
    )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0), 0),
    COALESCE(
      (COUNT(*) FILTER (
        WHERE (direction IN ('bullish','long')  AND return_7d > 0)
           OR (direction IN ('bearish','short') AND return_7d < 0)
      )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0))
      * COALESCE(AVG(return_7d) FILTER (WHERE return_7d > 0), 0)
      + (1.0 - (COUNT(*) FILTER (
          WHERE (direction IN ('bullish','long')  AND return_7d > 0)
             OR (direction IN ('bearish','short') AND return_7d < 0)
        )::REAL / NULLIF(COUNT(*) FILTER (WHERE return_7d IS NOT NULL), 0)))
        * COALESCE(AVG(return_7d) FILTER (WHERE return_7d < 0), 0)
    , 0)
  INTO v_total, v_hit_rate, v_expectancy
  FROM public.predictions
  WHERE COALESCE(market_type, 'equity') = p_market_type
    AND predicted_at > NOW() - (p_lookback_days || ' days')::INTERVAL;

  IF v_total < p_min_observations THEN
    RETURN QUERY SELECT
      p_market_type, 0.35::REAL, 0.25::REAL, 0.25::REAL, 0.15::REAL,
      v_total, v_hit_rate, v_expectancy,
      ('Not enough data (' || v_total || '/' || p_min_observations || ')')::TEXT;
    RETURN;
  END IF;

  v_norm := v_tech_acc + v_sent_acc + v_analyst_acc;
  IF v_norm > 0 THEN
    RETURN QUERY SELECT
      p_market_type,
      ((v_tech_acc    / v_norm) * 0.85)::REAL,
      ((v_sent_acc    / v_norm) * 0.85)::REAL,
      ((v_analyst_acc / v_norm) * 0.85)::REAL,
      0.15::REAL,
      v_total, v_hit_rate, v_expectancy,
      ('Learned from ' || v_total || ' ' || p_market_type || ' predictions')::TEXT;
  ELSE
    RETURN QUERY SELECT
      p_market_type, 0.35::REAL, 0.25::REAL, 0.25::REAL, 0.15::REAL,
      v_total, v_hit_rate, v_expectancy,
      'Zero signal accuracy — using baseline'::TEXT;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.recommend_market_weights(TEXT, INTEGER, INTEGER)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.recommend_market_weights(TEXT, INTEGER, INTEGER)
  TO service_role;


-- ── Verification queries ─────────────────────────────────────────────────────
-- SELECT * FROM v_market_performance;
-- SELECT * FROM v_market_expectancy ORDER BY expectancy DESC;
-- SELECT * FROM recommend_market_weights('equity');
-- SELECT * FROM recommend_market_weights('crypto');
-- SELECT * FROM model_weights WHERE active = true ORDER BY market_type, regime;
