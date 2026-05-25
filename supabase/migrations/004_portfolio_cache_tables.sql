-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 004: Portfolio positions + API cache
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════

-- ── Portfolio positions ───────────────────────────────────────────────────────
-- Stores user-defined stock/crypto positions for P&L tracking.
-- One row per ticker (upsert on conflict).

CREATE TABLE IF NOT EXISTS portfolio_positions (
  id          BIGSERIAL PRIMARY KEY,
  ticker      TEXT NOT NULL UNIQUE,        -- e.g. NVDA, BTC-USD
  shares      REAL NOT NULL DEFAULT 0,
  avg_cost    REAL NOT NULL DEFAULT 0,     -- average cost per share (USD)
  notes       TEXT DEFAULT '',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_ticker     ON portfolio_positions (ticker);
CREATE INDEX IF NOT EXISTS idx_portfolio_updated_at ON portfolio_positions (updated_at DESC);

-- Row-level security: anon can read, service role can write
ALTER TABLE portfolio_positions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_portfolio" ON portfolio_positions
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_portfolio" ON portfolio_positions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Allow the anon key to insert/update (Streamlit uses anon key via supabase-js)
-- In production, replace this with auth.uid() checks for multi-user support.
CREATE POLICY "anon_write_portfolio" ON portfolio_positions
  FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY "anon_update_portfolio" ON portfolio_positions
  FOR UPDATE TO anon USING (true) WITH CHECK (true);

CREATE POLICY "anon_delete_portfolio" ON portfolio_positions
  FOR DELETE TO anon USING (true);


-- ── API response cache ────────────────────────────────────────────────────────
-- Supabase-backed L2 cache for rate_limiter.py.
-- Prevents redundant API calls across pipeline runs and Streamlit sessions.
-- TTL is enforced by the application (not DB); stale rows cleaned up on insert.

CREATE TABLE IF NOT EXISTS api_cache (
  cache_key   TEXT PRIMARY KEY,            -- e.g. "yfinance:NVDA:1y"
  data        JSONB NOT NULL,              -- cached response payload
  source      TEXT,                        -- which API / source name
  ttl_hours   REAL DEFAULT 1,              -- intended TTL (informational)
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  expires_at  TIMESTAMPTZ                  -- computed by app: NOW() + ttl_hours * interval
);

CREATE INDEX IF NOT EXISTS idx_api_cache_source     ON api_cache (source);
CREATE INDEX IF NOT EXISTS idx_api_cache_expires_at ON api_cache (expires_at);

ALTER TABLE api_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_cache" ON api_cache
  FOR SELECT TO anon USING (true);

CREATE POLICY "service_all_cache" ON api_cache
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Anon can also write cache (used by Streamlit sessions)
CREATE POLICY "anon_write_cache" ON api_cache
  FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY "anon_update_cache" ON api_cache
  FOR UPDATE TO anon USING (true) WITH CHECK (true);


-- ── Cleanup function for expired cache rows ───────────────────────────────────
-- Call periodically via pg_cron or your pipeline:
--   SELECT cleanup_expired_cache();

CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  DELETE FROM api_cache WHERE expires_at < NOW();
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

-- Grant execution to service role and anon
GRANT EXECUTE ON FUNCTION cleanup_expired_cache() TO service_role;
GRANT EXECUTE ON FUNCTION cleanup_expired_cache() TO anon;


-- ── Summary: tables added in this migration ───────────────────────────────────
-- portfolio_positions  — user stock/crypto positions for Streamlit Portfolio page
-- api_cache            — shared API response cache across pipeline + dashboard
