-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 006: Analytics views — pre-aggregated daily metrics  (IDEMPOTENT)
--
-- Materialized views speed up dashboard queries from O(N rows) to O(1).
-- Refresh via:  SELECT refresh_analytics_views();
--
-- Schema note:
--   articles uses briefing_date (DATE)
--   signals  uses created_at    (TIMESTAMPTZ)
--   regime_snapshots / risk_scores use captured_at (TIMESTAMPTZ)
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Daily sentiment aggregates per source (uses briefing_date) ──────────────
DROP MATERIALIZED VIEW IF EXISTS mv_daily_sentiment;
CREATE MATERIALIZED VIEW mv_daily_sentiment AS
SELECT
  briefing_date                                  AS day,
  source,
  COUNT(*)                                       AS total,
  COUNT(*) FILTER (WHERE sentiment_label = 'bullish') AS bullish_count,
  COUNT(*) FILTER (WHERE sentiment_label = 'bearish') AS bearish_count,
  COUNT(*) FILTER (WHERE sentiment_label = 'neutral') AS neutral_count,
  AVG(sentiment_score)::REAL                     AS avg_score,
  AVG(terminal_score)::REAL                      AS avg_terminal_score
FROM articles
WHERE briefing_date IS NOT NULL
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

CREATE INDEX IF NOT EXISTS idx_mv_daily_sentiment_day
  ON mv_daily_sentiment (day DESC);


-- ── Daily signal counts per source (uses created_at) ────────────────────────
DROP MATERIALIZED VIEW IF EXISTS mv_daily_signals;
CREATE MATERIALIZED VIEW mv_daily_signals AS
SELECT
  DATE_TRUNC('day', created_at)::DATE            AS day,
  source,
  COUNT(*)                                       AS signal_count,
  COUNT(*) FILTER (WHERE sentiment_label = 'bullish') AS bullish,
  COUNT(*) FILTER (WHERE sentiment_label = 'bearish') AS bearish,
  AVG(sentiment_score)::REAL                     AS avg_sentiment_score
FROM signals
WHERE created_at IS NOT NULL
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

CREATE INDEX IF NOT EXISTS idx_mv_daily_signals_day
  ON mv_daily_signals (day DESC);


-- ── Regime persistence runs (how long in each regime) ───────────────────────
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


-- ── Latest values for fast KPI strip ────────────────────────────────────────
DROP VIEW IF EXISTS v_latest_metrics;
CREATE VIEW v_latest_metrics
WITH (security_invoker = on) AS
SELECT
  (SELECT COUNT(*) FROM articles)                                              AS total_articles,
  (SELECT COUNT(*) FROM signals)                                               AS total_signals,
  (SELECT COUNT(*) FROM regime_snapshots)                                      AS regime_observations,
  (SELECT COUNT(*) FROM risk_scores)                                           AS risk_observations,
  (SELECT MAX(captured_at) FROM regime_snapshots)                              AS last_regime_update,
  (SELECT MAX(captured_at) FROM risk_scores)                                   AS last_risk_update,
  (SELECT MAX(briefing_date) FROM articles)                                    AS last_article_date,
  (SELECT COUNT(*) FROM articles WHERE briefing_date >= CURRENT_DATE)          AS articles_today,
  (SELECT COUNT(*) FROM signals  WHERE created_at > NOW() - INTERVAL '24 hours') AS signals_24h;

GRANT SELECT ON v_latest_metrics TO anon, authenticated;


-- ── Refresh function (call after pipeline run, service_role only) ───────────
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


-- ── Permissions ─────────────────────────────────────────────────────────────
GRANT SELECT ON mv_daily_sentiment, mv_daily_signals, mv_regime_runs
  TO anon, authenticated;


-- ── Verification queries ────────────────────────────────────────────────────
-- SELECT * FROM v_latest_metrics;
-- SELECT * FROM mv_daily_sentiment LIMIT 5;
-- SELECT * FROM mv_daily_signals   LIMIT 5;
-- SELECT * FROM mv_regime_runs     LIMIT 5;
-- SELECT refresh_analytics_views();
