-- IHSG Fear & Greed Index — initial schema

CREATE TABLE IF NOT EXISTS daily_sentiment (
    date DATE PRIMARY KEY,
    close_price NUMERIC(12, 4) NOT NULL,
    ma_125 NUMERIC(12, 4),
    google_trends_raw INTEGER,
    normalized_trends NUMERIC(6, 2),
    arah_momentum SMALLINT CHECK (arah_momentum IN (-1, 1)),
    skala_emosi NUMERIC(6, 2),
    zone TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_sentiment_date_desc ON daily_sentiment (date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_sentiment_zone ON daily_sentiment (zone);

CREATE TABLE IF NOT EXISTS zone_periods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone TEXT NOT NULL,
    entry_date DATE NOT NULL,
    exit_date DATE,
    duration_days INTEGER,
    return_pct NUMERIC(8, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_zone_periods_entry ON zone_periods (entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_zone_periods_zone ON zone_periods (zone);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    rows_upserted INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

-- Row Level Security: public read-only for sentiment data
ALTER TABLE daily_sentiment ENABLE ROW LEVEL SECURITY;
ALTER TABLE zone_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read daily_sentiment"
    ON daily_sentiment FOR SELECT
    USING (true);

CREATE POLICY "Public read zone_periods"
    ON zone_periods FOR SELECT
    USING (true);

-- ingestion_runs is backend-only (no public policy)
