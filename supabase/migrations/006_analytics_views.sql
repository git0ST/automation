-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 006: Analytics views — pre-aggregated daily metrics  (IDEMPOTENT)
--
-- These materialized views speed up dashboard queries from O(N rows) to O(1).
-- Refresh via:
--   SELECT refresh_analytics_views();
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Daily sentiment aggregates per source ───────────────────────────────────
DROP MATERIALIZED VIEW IF EXISTS mv_daily_sentiment;
CREATE MATERIALIZED VIEW mv_daily_sentiment AS
SELECT
  DATE_TRUNC('day', COALESCE(created_at, NOW())) AS day,
  source,
  COUNT(*)                                       AS total,
  COUNT(*) FILTER (WHERE sentiment_label = 'bullish') AS bullish_count,
  COUNT(*) FILTER (WHERE sentiment_label = 'bearish') AS bearish_count,
  COUNT(*) FILTER (WHERE sentiment_label = 'neutral') AS neutral_count,
  AVG(sentiment_score)::REAL                     AS avg_score,
  AVG(terminal_score)::REAL                      AS avg_terminal_score
FROM articles
WHERE created_at IS NOT NULL
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

CREATE INDEX IF NOT EXISTS idx_mv_daily_sentiment_day
  ON mv_daily_sentiment (day DESC);


-- ── Daily signal counts per source ──────────────────────────────────────────
DROP MATERIALIZED VIEW IF EXISTS mv_daily_signals;
CREATE MATERIALIZED VIEW mv_daily_signals AS
SELECT
  DATE_TRUNC('day', COALESCE(created_at, NOW())) AS day,
  source,
  COUNT(*)                                       AS signal_count,
  COUNT(*) FILTER (WHERE sentiment_label = 'bullish') AS bullish,
  COUNT(*) FILTER (WHERE sentiment_label = 'bearish') AS bearish
FROM signals
WHERE created_at IS NOT NULL
GROUP BY 1, 2
ORDER BY 1 DESC, 2;


-- ── Regime persistence (how long in each regime) ────────────────────────────
DROP MATERIALIZED VIEW IF EXISTS mv_regime_runs;
CREATE MATERIALIZED VIEW mv_regime_runs AS
WITH labeled AS (
  SELECT
    captured_at, regime, label, confidence_pct,
    LAG(regime) OVER (ORDER BY captured_at) AS prev_regime
  FROM regime_snapshots
),
runs AS (
  SELECT
    captured_at, regime, label, confidence_pct,
    SUM(CASE WHEN regime = prev_regime OR prev_regime IS NULL THEN 0 ELSE 1 END)
      OVER (ORDER BY captured_at) AS run_id
  FROM labeled
)
SELECT
  run_id,
  regime,
  label,
  MIN(captured_at)                   AS started_at,
  MAX(captured_at)                   AS ended_at,
  COUNT(*)                           AS observations,
  AVG(confidence_pct)::REAL          AS avg_confidence,
  EXTRACT(EPOCH FROM (MAX(captured_at) - MIN(captured_at))) / 86400.0 AS duration_days
FROM runs
GROUP BY run_id, regime, label
ORDER BY MIN(captured_at) DESC;


-- ── Latest values from time-series tables (for fast KPI strip queries) ──────
DROP VIEW IF EXISTS v_latest_metrics;
CREATE OR REPLACE VIEW v_latest_metrics
WITH (security_invoker = on) AS
SELECT
  (SELECT COUNT(*) FROM articles)                                    AS total_articles,
  (SELECT COUNT(*) FROM signals)                                     AS total_signals,
  (SELECT COUNT(*) FROM regime_snapshots)                            AS regime_observations,
  (SELECT COUNT(*) FROM risk_scores)                                 AS risk_observations,
  (SELECT MAX(captured_at) FROM regime_snapshots)                    AS last_regime_update,
  (SELECT MAX(captured_at) FROM risk_scores)                         AS last_risk_update,
  (SELECT COUNT(*) FROM articles WHERE created_at > NOW() - INTERVAL '24 hours') AS articles_24h,
  (SELECT COUNT(*) FROM signals  WHERE created_at > NOW() - INTERVAL '24 hours') AS signals_24h;

GRANT SELECT ON v_latest_metrics TO anon, authenticated;


-- ── Refresh function (call after pipeline run) ──────────────────────────────
CREATE OR REPLACE FUNCTION public.refresh_analytics_views()
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  REFRESH MATERIALIZED VIEW public.mv_daily_sentiment;
  REFRESH MATERIALIZED VIEW public.mv_daily_signals;
  REFRESH MATERIALIZED VIEW public.mv_regime_runs;
  RETURN 'Views refreshed at ' || NOW()::TEXT;
END;
$$;

REVOKE ALL ON FUNCTION public.refresh_analytics_views() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.refresh_analytics_views() FROM anon;
REVOKE ALL ON FUNCTION public.refresh_analytics_views() FROM authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_analytics_views() TO service_role;


-- ── Permissions for materialized views ──────────────────────────────────────
GRANT SELECT ON mv_daily_sentiment, mv_daily_signals, mv_regime_runs
  TO anon, authenticated;


-- ── Verification ────────────────────────────────────────────────────────────
-- SELECT * FROM v_latest_metrics;
-- SELECT * FROM mv_daily_sentiment LIMIT 5;
-- SELECT * FROM mv_regime_runs LIMIT 5;
-- SELECT refresh_analytics_views();
