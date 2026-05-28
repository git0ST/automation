-- 014_security_rls_hardening.sql
-- Defense-in-depth RLS hardening.
--
-- Problem: several tables granted the public `anon` role full write access
-- (FOR INSERT/ALL ... WITH CHECK (true)). Combined with a publicly reachable
-- app, that let anyone INSERT fake predictions (poisoning the learning loop)
-- or forge/delete alert events.
--
-- These tables are written by the PIPELINE using the service_role key, which
-- bypasses RLS — so removing the anon write grants loses NO functionality while
-- closing the data-poisoning / forgery vectors. Idempotent.

-- ── predictions: pipeline-only writes (UI logging via anon was redundant) ─────
-- Keep anon SELECT (Track Record reads) + service_role ALL (pipeline writes).
DROP POLICY IF EXISTS "anon_write_pred" ON predictions;

-- ── alert_events: machine-generated; anon should READ only ───────────────────
DROP POLICY IF EXISTS "anon_all_events"  ON alert_events;
DROP POLICY IF EXISTS "anon_read_events" ON alert_events;
CREATE POLICY "anon_read_events" ON alert_events
  FOR SELECT TO anon USING (true);
-- service_role bypasses RLS, so the pipeline keeps writing events.

-- ─────────────────────────────────────────────────────────────────────────────
-- NOTE — intentionally NOT locked here (would break in-app editing):
--   * portfolio_positions / portfolio_pnl (migration 004)
--   * alert_rules (migration 009)
-- These are edited by YOU through the app with the anon key. They are now
-- protected by the app password gate (_require_auth in _terminal_chrome.py).
-- To fully close them at the DB layer, switch the app's WRITES to the
-- service_role key (server-side, behind the gate) and replace their anon
-- FOR ALL/INSERT/UPDATE/DELETE policies with SELECT-only. Tracked follow-up.
-- ─────────────────────────────────────────────────────────────────────────────
