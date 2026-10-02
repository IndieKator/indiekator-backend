-- Per-keyword Google Trends observations now live in public.trend_snapshots.
-- fgi_snapshots retains only the configured aggregate (trends_mean).
alter table public.fgi_snapshots
    drop column if exists trend_ihsg,
    drop column if exists trend_idx_composite,
    drop column if exists trend_indeks_harga_saham_gabungan;
