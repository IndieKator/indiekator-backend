-- Migration: remove the legacy daily_sentiment table (V1 index storage).
--
-- DECISION RECORD
--   The rows held in daily_sentiment are DISCARDED by explicit project
--   decision. No archive export was taken.
--
--   A numeric backfill into fgi_snapshots is not possible: skala_emosi is a
--   min-max normalization of a single Google Trends keyword multiplied by a
--   momentum sign, whereas fgi is 0.60 * price_score + 0.40 * search_score
--   over three keywords. No arithmetic mapping exists between the two, and
--   the granularities differ (daily vs weekly).
--
--   No calendar coverage is lost. fgi_snapshots spans 2025-10-05 through
--   2026-09-13, which fully encloses the daily_sentiment range 2026-03-05
--   through 2026-09-01.
--
--   This migration is forward-only; there is no down migration by decision.
--   Once applied, the discarded rows are recoverable only from a platform
--   backup.
--
-- SCOPE
--   daily_sentiment and its own dependent objects only. No statement here
--   touches fgi_snapshots, zone_periods, ingestion_runs, or any auth or
--   storage schema. Every statement is guarded so re-application is a no-op.
--
-- PRECONDITION
--   The consolidated ingestion path must already be deployed before this runs,
--   so that no scheduled job attempts to write the dropped table.

-- Drop the read policy first. Guarded on table existence because
-- DROP POLICY IF EXISTS still fails when the parent relation is absent.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = 'daily_sentiment'
    ) THEN
        DROP POLICY IF EXISTS "Public read daily_sentiment" ON public.daily_sentiment;
    END IF;
END
$$;

DROP INDEX IF EXISTS public.idx_daily_sentiment_date_desc;
DROP INDEX IF EXISTS public.idx_daily_sentiment_zone;

-- Dropping the table also removes daily_sentiment_pkey and
-- daily_sentiment_arah_momentum_check.
--
-- Deliberately no CASCADE: daily_sentiment has no dependent views,
-- materialized views, triggers, or foreign keys in either direction. A plain
-- DROP is therefore sufficient, and it will fail loudly if that ever stops
-- being true rather than silently removing an unrelated object.
DROP TABLE IF EXISTS public.daily_sentiment;
