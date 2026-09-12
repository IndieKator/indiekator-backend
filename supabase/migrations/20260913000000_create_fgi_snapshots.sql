create table if not exists public.fgi_snapshots (
    week_date date primary key,
    close_price numeric not null,
    ma_125 numeric not null,
    distance_pct numeric not null,
    price_score numeric not null check (price_score between 0 and 100),
    search_score numeric not null check (search_score between 0 and 100),
    fgi numeric not null check (fgi between 0 and 100),
    sentiment text not null check (
        sentiment in ('Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed')
    ),
    trends_mean numeric not null check (trends_mean between 0 and 100),
    trend_ihsg numeric not null check (trend_ihsg between 0 and 100),
    trend_idx_composite numeric not null check (trend_idx_composite between 0 and 100),
    trend_indeks_harga_saham_gabungan numeric not null check (
        trend_indeks_harga_saham_gabungan between 0 and 100
    ),
    updated_at timestamptz not null default now()
);

create index if not exists fgi_snapshots_updated_at_idx
    on public.fgi_snapshots (updated_at desc);

alter table public.fgi_snapshots enable row level security;
revoke all on table public.fgi_snapshots from anon, authenticated;
