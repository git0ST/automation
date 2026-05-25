-- Migration: 002_signals_table.sql
-- Intelligence Terminal v2.0
-- Adds the signals table for insider trades, options flow, congress, FINRA short data.
-- Run in Supabase SQL Editor: https://app.supabase.com/project/jptwbvigtgiffjqnctic/sql

CREATE TABLE IF NOT EXISTS signals (
  id              TEXT PRIMARY KEY,
  source          TEXT NOT NULL,
  title           TEXT NOT NULL,
  url             TEXT,
  preview         TEXT,
  sentiment_label TEXT,
  sentiment_score REAL DEFAULT 0,
  entities        TEXT[]  DEFAULT '{}',
  tags            TEXT[]  DEFAULT '{}',
  payload         JSONB,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_source  ON signals (source, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals (created_at DESC);

ALTER TABLE signals ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='anon_read_signals' AND tablename='signals') THEN
    CREATE POLICY "anon_read_signals" ON signals FOR SELECT USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='service_write_signals' AND tablename='signals') THEN
    CREATE POLICY "service_write_signals" ON signals FOR ALL USING (true);
  END IF;
END $$;

-- Verify
SELECT 'signals table ready' AS status, COUNT(*) AS rows FROM signals;
