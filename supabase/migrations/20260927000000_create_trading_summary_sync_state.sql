-- Fetch attempts must survive restarts, including attempts that returned no IDX data.
CREATE TABLE IF NOT EXISTS public.trading_summary_sync_state (
    date DATE PRIMARY KEY,
    last_attempt_at TIMESTAMPTZ NOT NULL,
    finalized_at TIMESTAMPTZ
);

ALTER TABLE public.trading_summary_sync_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.trading_summary_sync_state FROM anon, authenticated;
