-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 007: Adaptive relevance learning  (IDEMPOTENT)
--
-- Foundation for the adaptive scoring system. Tracks which articles correlated
-- with subsequent market moves so the relevance classifier can be auto-tuned.
--
-- Workflow:
--   1. Pipeline scores article → writes to relevance_observations
--   2. Daily job correlates article entities with next-N-day ticker returns
--   3. update_entity_weights() recomputes per-entity predictive power
--   4. Pipeline reads entity_weights to adjust article scores
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Relevance observations: every scored article with its entities ───────────
CREATE TABLE IF NOT EXISTS relevance_observations (
  id              BIGSERIAL PRIMARY KEY,
  article_id      TEXT NOT NULL,
  source          TEXT,
  title           TEXT,
  url             TEXT,
  finance_score   REAL,
  tier_matches    TEXT[],                  -- ["strong:earnings", "ticker:NVDA", ...]
  entities        JSONB,                   -- {people:[], orgs:[], tickers:[]}
  sentiment_label TEXT,
  observed_at     TIMESTAMPTZ DEFAULT NOW(),
  -- Outcome (filled by correlation job, day +1/+3/+7 after observation)
  next_1d_return  REAL,
  next_3d_return  REAL,
  next_7d_return  REAL,
  abs_move_max    REAL                     -- max |return| over 7d window
);

CREATE INDEX IF NOT EXISTS idx_rel_obs_observed_at
  ON relevance_observations (observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_rel_obs_article_id
  ON relevance_observations (article_id);

ALTER TABLE relevance_observations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_rel_obs"     ON relevance_observations;
DROP POLICY IF EXISTS "service_all_rel_obs"   ON relevance_observations;
CREATE POLICY "anon_read_rel_obs"   ON relevance_observations FOR SELECT TO anon USING (true);
CREATE POLICY "service_all_rel_obs" ON relevance_observations FOR ALL    TO service_role USING (true) WITH CHECK (true);


-- ── Entity weights: learned predictive power per entity ─────────────────────
-- Updated by daily job that aggregates relevance_observations.
-- Used by finance_filter at scoring time to up/down-weight entities that have
-- historically preceded large market moves (or didn't).
CREATE TABLE IF NOT EXISTS entity_weights (
  entity          TEXT PRIMARY KEY,        -- e.g. "person:elon musk", "org:openai"
  entity_type     TEXT,                    -- person | org | ticker | keyword
  observation_count INTEGER DEFAULT 0,
  avg_abs_move_7d REAL DEFAULT 0,          -- avg |return| over 7d
  hit_rate        REAL DEFAULT 0,          -- % of observations w/ ≥1% move
  current_weight  REAL DEFAULT 1.0,        -- multiplier applied at scoring time
  last_updated    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_weights_type
  ON entity_weights (entity_type, current_weight DESC);

ALTER TABLE entity_weights ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_ent_w"     ON entity_weights;
DROP POLICY IF EXISTS "service_all_ent_w"   ON entity_weights;
CREATE POLICY "anon_read_ent_w"   ON entity_weights FOR SELECT TO anon USING (true);
CREATE POLICY "service_all_ent_w" ON entity_weights FOR ALL    TO service_role USING (true) WITH CHECK (true);


-- ── Update function: recompute entity weights from observations ─────────────
-- Call daily after market close.
CREATE OR REPLACE FUNCTION public.update_entity_weights()
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  updated_count INTEGER;
BEGIN
  -- Aggregate observations by entity over the last 90 days
  WITH expanded AS (
    SELECT
      jsonb_array_elements_text(
        COALESCE(entities -> 'people', '[]'::jsonb) ||
        COALESCE(entities -> 'orgs',    '[]'::jsonb) ||
        COALESCE(entities -> 'tickers', '[]'::jsonb)
      ) AS entity_name,
      abs_move_max,
      observed_at
    FROM public.relevance_observations
    WHERE observed_at > NOW() - INTERVAL '90 days'
      AND abs_move_max IS NOT NULL
  ),
  aggregated AS (
    SELECT
      entity_name,
      COUNT(*)                                              AS n,
      AVG(abs_move_max)::REAL                               AS avg_move,
      (COUNT(*) FILTER (WHERE abs_move_max >= 0.01))::REAL
        / NULLIF(COUNT(*), 0)::REAL                         AS hit_rate
    FROM expanded
    GROUP BY entity_name
    HAVING COUNT(*) >= 3
  )
  INSERT INTO public.entity_weights (entity, entity_type, observation_count,
                                     avg_abs_move_7d, hit_rate, current_weight,
                                     last_updated)
  SELECT
    entity_name,
    -- Heuristic type detection
    CASE
      WHEN entity_name ~ '^[A-Z]{1,5}$' OR entity_name ~ '^\^' THEN 'ticker'
      WHEN entity_name LIKE '% %' THEN 'person'
      ELSE 'org'
    END,
    n,
    avg_move,
    hit_rate,
    -- Weight = 1.0 + 0.5 * hit_rate (cap [0.5, 1.75])
    GREATEST(0.5, LEAST(1.75, 1.0 + 0.5 * COALESCE(hit_rate, 0))),
    NOW()
  FROM aggregated
  ON CONFLICT (entity) DO UPDATE
    SET observation_count = EXCLUDED.observation_count,
        avg_abs_move_7d   = EXCLUDED.avg_abs_move_7d,
        hit_rate          = EXCLUDED.hit_rate,
        current_weight    = EXCLUDED.current_weight,
        last_updated      = NOW();

  GET DIAGNOSTICS updated_count = ROW_COUNT;
  RETURN 'Updated ' || updated_count || ' entity weights at ' || NOW()::TEXT;
END;
$$;

REVOKE ALL ON FUNCTION public.update_entity_weights() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.update_entity_weights() TO service_role;


-- ── Verification ─────────────────────────────────────────────────────────────
-- SELECT * FROM relevance_observations LIMIT 5;
-- SELECT * FROM entity_weights ORDER BY current_weight DESC LIMIT 10;
-- SELECT update_entity_weights();
