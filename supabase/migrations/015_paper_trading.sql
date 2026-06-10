-- 015_paper_trading.sql
-- Auto-mode paper trading book: the system opens virtual positions from its
-- own predictions, manages stops/targets/time-stops, and records realized
-- P&L — position-level ground truth for the learning loop and the UI.
-- Written by the pipeline (service_role); read-only for the app (anon).

CREATE TABLE IF NOT EXISTS paper_trades (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ticker          TEXT NOT NULL,
  direction       TEXT NOT NULL,            -- bullish | bearish
  market          TEXT,                     -- india | us
  source          TEXT,                     -- india_runner | opportunity_runner | …
  horizon         TEXT,
  confidence      NUMERIC,
  entry_price     NUMERIC NOT NULL,
  entry_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  qty             NUMERIC,
  notional        NUMERIC,                  -- account-currency exposure at entry
  stop_price      NUMERIC,
  target_price    NUMERIC,
  time_stop_at    TIMESTAMPTZ,
  status          TEXT NOT NULL DEFAULT 'open',   -- open | closed
  exit_price      NUMERIC,
  exit_at         TIMESTAMPTZ,
  exit_reason     TEXT,                     -- stop | target | time | derisk
  pnl_pct         NUMERIC,
  regime_at_entry TEXT
);

CREATE INDEX IF NOT EXISTS idx_paper_status   ON paper_trades (status, entry_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_exit     ON paper_trades (exit_at DESC);

ALTER TABLE paper_trades ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "anon_read_paper"   ON paper_trades;
DROP POLICY IF EXISTS "service_all_paper" ON paper_trades;
CREATE POLICY "anon_read_paper"   ON paper_trades FOR SELECT TO anon USING (true);
CREATE POLICY "service_all_paper" ON paper_trades FOR ALL TO service_role
  USING (true) WITH CHECK (true);
