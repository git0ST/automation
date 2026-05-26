-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 008: Article freshness columns (IDEMPOTENT)
--
-- Adds inserted_at + updated_at to articles for proper recency tracking.
-- Without this, the only timestamp on articles is briefing_date (a DATE),
-- which loses intraday resolution — articles dated "May 25" could be 30
-- minutes old or 23 hours old.
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Add timestamp columns ────────────────────────────────────────────────────
ALTER TABLE articles ADD COLUMN IF NOT EXISTS
  inserted_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE articles ADD COLUMN IF NOT EXISTS
  updated_at TIMESTAMPTZ DEFAULT NOW();

-- Backfill nulls from briefing_date (treat as start-of-day)
UPDATE articles
   SET inserted_at = COALESCE(inserted_at, (briefing_date::TIMESTAMPTZ))
 WHERE inserted_at IS NULL;
UPDATE articles
   SET updated_at = COALESCE(updated_at, (briefing_date::TIMESTAMPTZ))
 WHERE updated_at IS NULL;


-- ── Index for fast recency queries ──────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_articles_inserted_at
  ON articles (inserted_at DESC);


-- ── Trigger: auto-update `updated_at` on row change ─────────────────────────
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.set_updated_at() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_articles_updated_at ON articles;
CREATE TRIGGER trg_articles_updated_at
  BEFORE UPDATE ON articles
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();


-- ── Helper view: data freshness summary per source ──────────────────────────
DROP VIEW IF EXISTS v_data_freshness;
CREATE VIEW v_data_freshness
WITH (security_invoker = on) AS
SELECT
  source,
  COUNT(*)                                 AS article_count,
  MAX(inserted_at)                         AS last_inserted,
  EXTRACT(EPOCH FROM (NOW() - MAX(inserted_at))) / 60.0  AS minutes_since_last
FROM articles
WHERE inserted_at IS NOT NULL
GROUP BY source
ORDER BY MAX(inserted_at) DESC;

GRANT SELECT ON v_data_freshness TO anon, authenticated;


-- ── Verification ─────────────────────────────────────────────────────────────
-- SELECT * FROM v_data_freshness;
-- SELECT id, source, briefing_date, inserted_at FROM articles ORDER BY inserted_at DESC LIMIT 5;
