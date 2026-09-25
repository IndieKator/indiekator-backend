-- Daily Trading Summary (Volume, Turnover Value, and Frequency)

CREATE TABLE IF NOT EXISTS public.daily_trading_summary (
    date DATE PRIMARY KEY,
    volume BIGINT NOT NULL,
    value_idr NUMERIC(20, 2) NOT NULL,
    frequency INTEGER NOT NULL,
    volume_ma_20 NUMERIC(20, 2),
    frequency_ma_20 NUMERIC(14, 2),
    value_ma_20 NUMERIC(20, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trading_summary_date_desc
    ON public.daily_trading_summary (date DESC);

ALTER TABLE public.daily_trading_summary ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read daily_trading_summary"
    ON public.daily_trading_summary FOR SELECT
    USING (true);
