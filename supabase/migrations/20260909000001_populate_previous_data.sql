-- Migration: 002_populate_previous_data.sql
-- Seeds zone_periods with the historical Fear & Greed zone episodes.
--
-- The daily_sentiment seed block that used to live here was removed when the
-- V1 table was decommissioned (see 20260915000000_remove_daily_sentiment_table.sql).
-- Keeping it would break `supabase db reset`, because this file is applied
-- before the drop migration and would insert rows into a table that the later
-- migration removes.
--
-- These rows are a starting point only. The consolidated ingestion path
-- rebuilds zone_periods from fgi_snapshots on every run, so after the first
-- successful ingestion these values are replaced by the weekly derivation.

-- Clear existing zone_periods before inserting newly computed periods
DELETE FROM zone_periods;

INSERT INTO zone_periods (zone, entry_date, exit_date, duration_days, return_pct)
VALUES
    ('fear', '2026-03-05', '2026-03-06', 2, -1.6192),
    ('extreme_fear', '2026-03-09', '2026-03-09', 1, 0.0),
    ('fear', '2026-03-10', '2026-05-13', 65, -9.6439),
    ('extreme_fear', '2026-05-18', '2026-05-25', 8, -5.9536),
    ('fear', '2026-05-26', '2026-05-29', 4, -0.0458),
    ('neutral', '2026-06-02', NULL, 92, 6.5293);
