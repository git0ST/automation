-- ══════════════════════════════════════════════════════════════════════════════
-- Migration 005: Security Hardening   (IDEMPOTENT — safe to re-run)
--
-- Fixes Supabase Security Advisor warnings:
--   ✓ v_intelligence_latest:  SECURITY DEFINER → SECURITY INVOKER
--   ✓ cleanup_expired_cache:  mutable search_path → pinned; anon access revoked
--   ✓ rls_auto_enable:        execute revoked from anon/authenticated (if exists)
--
-- The "always true" RLS warnings are INTENTIONAL design choices for this
-- single-user app (no Supabase Auth) and documented below.
--
-- Run in Supabase SQL editor:
--   https://supabase.com/dashboard/project/jptwbvigtgiffjqnctic/sql/new
-- ══════════════════════════════════════════════════════════════════════════════


-- ── 1. v_intelligence_latest — switch to SECURITY INVOKER ────────────────────
-- A SECURITY DEFINER view bypasses RLS of the calling user and runs as the
-- view creator. SECURITY INVOKER makes the view respect the caller's RLS.

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


-- ── 2. cleanup_expired_cache — pin search_path + revoke anon access ──────────
-- (a) Mutable search_path is a privilege-escalation vector: an attacker could
--     SET search_path = 'evil_schema' to make the function reference malicious
--     tables. Pinning to '' + fully-qualifying objects fixes this.
-- (b) Function shouldn't be callable by anon/authenticated — it's an internal
--     maintenance task for the pipeline (uses service_role).

CREATE OR REPLACE FUNCTION public.cleanup_expired_cache()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''                       -- ← prevents search_path attacks
AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  DELETE FROM public.api_cache             -- ← fully qualified now
    WHERE expires_at < NOW();
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

-- Revoke public access — only service_role should be calling this
REVOKE ALL ON FUNCTION public.cleanup_expired_cache() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.cleanup_expired_cache() FROM anon;
REVOKE ALL ON FUNCTION public.cleanup_expired_cache() FROM authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_expired_cache() TO service_role;


-- ── 3. rls_auto_enable (if it exists) — revoke anon access ───────────────────
-- This function may have been auto-created by an earlier setup script or
-- Supabase template. If it exists, lock down its execute permissions.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE n.nspname = 'public' AND p.proname = 'rls_auto_enable'
  ) THEN
    EXECUTE 'REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM PUBLIC';
    EXECUTE 'REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM anon';
    EXECUTE 'REVOKE ALL ON FUNCTION public.rls_auto_enable() FROM authenticated';
    RAISE NOTICE 'Locked down rls_auto_enable() permissions';
  ELSE
    RAISE NOTICE 'rls_auto_enable() does not exist — no action needed';
  END IF;
END $$;


-- ══════════════════════════════════════════════════════════════════════════════
-- DESIGN NOTE: The remaining "RLS Policy Always True" warnings
-- ══════════════════════════════════════════════════════════════════════════════
-- The Supabase linter flags these as warnings:
--
--   • articles, briefings, fear_greed, macro_indicators, market_snapshots, alerts:
--       service_write_* policies use USING (true) for FOR ALL
--       → INTENTIONAL: pipeline cron writes with service_role, which bypasses
--         RLS anyway. These policies are belt-and-braces for clarity.
--
--   • portfolio_positions:
--       anon can INSERT/UPDATE/DELETE without restrictions
--       → INTENTIONAL for single-user mode (no Supabase Auth). When you add
--         multi-user auth via Supabase Auth, replace these with:
--           CREATE POLICY anon_rw_own_portfolio ON portfolio_positions
--             FOR ALL TO authenticated
--             USING (user_id = auth.uid())
--             WITH CHECK (user_id = auth.uid());
--
--   • api_cache:
--       anon can INSERT/UPDATE freely
--       → INTENTIONAL: Streamlit uses anon key to write cache entries.
--         Cache rows are bounded by TTL and cleanup_expired_cache().
--
-- If you migrate to Supabase Auth later, the migrations to tighten these
-- will be in a future migration 006_multi_user_auth.sql
-- ══════════════════════════════════════════════════════════════════════════════


-- ── Verification queries ──────────────────────────────────────────────────────
-- Run these to confirm migration 005 succeeded:

-- (a) View should now be security_invoker = true
-- SELECT relname, reloptions FROM pg_class WHERE relname = 'v_intelligence_latest';
-- Expected: reloptions contains "security_invoker=on"

-- (b) Function should have search_path pinned
-- SELECT proname, proconfig FROM pg_proc WHERE proname = 'cleanup_expired_cache';
-- Expected: proconfig = {"search_path="}

-- (c) Anon should NOT have EXECUTE on cleanup_expired_cache
-- SELECT grantee, privilege_type FROM information_schema.routine_privileges
--   WHERE routine_name = 'cleanup_expired_cache';
-- Expected: only service_role appears
