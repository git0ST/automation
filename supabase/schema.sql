-- Intelligence Terminal — Supabase Schema
-- Run this in the Supabase SQL Editor to initialize the project.
-- Project ref: jptwbvigtgiffjqnctic

-- ── Articles ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS articles (
  id              TEXT PRIMARY KEY,
  source          TEXT NOT NULL,
  title           TEXT NOT NULL,
  url             TEXT UNIQUE NOT NULL,
  preview         TEXT,
  score           REAL    DEFAULT 0,
  terminal_score  REAL    DEFAULT 0,
  sentiment_score REAL,             -- VADER compound: -1 to 1
  sentiment_label TEXT,             -- bearish / neutral / bullish
  tags            TEXT[]  DEFAULT '{}',
  sector          TEXT,
  meta            TEXT,
  entities        TEXT[]  DEFAULT '{}',  -- detected ticker / company names
  briefing_date   DATE    DEFAULT CURRENT_DATE,
  fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_date   ON articles (briefing_date DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles (source);
CREATE INDEX IF NOT EXISTS idx_articles_score  ON articles (terminal_score DESC);

-- Enable row-level security (allow anon read for the web terminal)
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_articles" ON articles FOR SELECT USING (true);
CREATE POLICY "service_write_articles" ON articles FOR ALL USING (true);

-- ── Market Snapshots ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_snapshots (
  id          BIGSERIAL PRIMARY KEY,
  ticker      TEXT NOT NULL,
  name        TEXT,
  price       REAL,
  change_pct  REAL,
  type        TEXT,     -- index / stock / crypto
  snapshot_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_ticker ON market_snapshots (ticker, snapshot_at DESC);

ALTER TABLE market_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_market" ON market_snapshots FOR SELECT USING (true);
CREATE POLICY "service_write_market" ON market_snapshots FOR ALL USING (true);

-- ── Macro Indicators (FRED) ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS macro_indicators (
  id          BIGSERIAL PRIMARY KEY,
  series_id   TEXT NOT NULL,
  name        TEXT,
  value       REAL,
  unit        TEXT,
  period      TEXT,     -- YYYY-MM or YYYY-QN
  fetched_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_macro_series_period ON macro_indicators (series_id, period);

ALTER TABLE macro_indicators ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_macro" ON macro_indicators FOR SELECT USING (true);
CREATE POLICY "service_write_macro" ON macro_indicators FOR ALL USING (true);

-- ── Briefings ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS briefings (
  id          BIGSERIAL PRIMARY KEY,
  date        DATE DEFAULT CURRENT_DATE,
  time_of_day TEXT,     -- morning / afternoon / evening / night
  content     TEXT,
  item_count  INTEGER DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE briefings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_briefings" ON briefings FOR SELECT USING (true);
CREATE POLICY "service_write_briefings" ON briefings FOR ALL USING (true);

-- ── Alerts ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
  id         BIGSERIAL PRIMARY KEY,
  type       TEXT,     -- market_move / breaking_news / trend / macro
  title      TEXT,
  body       TEXT,
  priority   INTEGER DEFAULT 0,   -- 0=info 1=warning 2=critical
  ticker     TEXT,
  read       BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_alerts" ON alerts FOR SELECT USING (true);
CREATE POLICY "service_write_alerts" ON alerts FOR ALL USING (true);

-- ── Fear & Greed History ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fear_greed (
  id          BIGSERIAL PRIMARY KEY,
  value       INTEGER,             -- 0-100
  label       TEXT,                -- Extreme Fear / Fear / Neutral / Greed / Extreme Greed
  source      TEXT DEFAULT 'crypto',
  fetched_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE fear_greed ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_fg" ON fear_greed FOR SELECT USING (true);
CREATE POLICY "service_write_fg" ON fear_greed FOR ALL USING (true);

-- ── Signals (insider trades, options flow, congress, FINRA short) ─────────────
-- Run this migration if you applied the original schema before v2.0
CREATE TABLE IF NOT EXISTS signals (
  id              TEXT PRIMARY KEY,
  source          TEXT NOT NULL,    -- edgar / options / congress / finra
  title           TEXT NOT NULL,
  url             TEXT,
  preview         TEXT,
  sentiment_label TEXT,             -- bullish / bearish / neutral
  sentiment_score REAL DEFAULT 0,
  entities        TEXT[]  DEFAULT '{}',
  tags            TEXT[]  DEFAULT '{}',
  payload         JSONB,            -- source-specific data (option_data, short_data, etc)
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_source ON signals (source, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals (created_at DESC);

ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_signals"   ON signals FOR SELECT USING (true);
CREATE POLICY "service_write_signals" ON signals FOR ALL USING (true);

-- ── Realtime publications (enable for live updates in web terminal) ────────────
-- In Supabase Dashboard: Database → Replication → enable for:
--   alerts, articles, market_snapshots, signals
