-- Long-form Google Trends observations. Legacy per-keyword FGI columns remain
-- temporarily for rollback compatibility; application reads now use this table.
create table if not exists public.trend_snapshots (
    date date not null,
    index_name text not null,
    keyword text not null,
    score numeric not null check (score between 0 and 100),
    updated_at timestamptz not null default now(),
    primary key (date, index_name, keyword),
    check (length(trim(index_name)) between 1 and 64),
    check (length(trim(keyword)) between 1 and 100)
);

create index if not exists trend_snapshots_index_keyword_date_idx
    on public.trend_snapshots (index_name, keyword, date desc);

alter table public.trend_snapshots enable row level security;
revoke all on table public.trend_snapshots from anon, authenticated;

-- Preserve historical FGI keyword observations in the new normalized shape.
insert into public.trend_snapshots (date, index_name, keyword, score, updated_at)
select week_date, 'ihsg', 'ihsg', trend_ihsg, updated_at
from public.fgi_snapshots
where trend_ihsg is not null
on conflict (date, index_name, keyword) do update
set score = excluded.score,
    updated_at = excluded.updated_at;

insert into public.trend_snapshots (date, index_name, keyword, score, updated_at)
select week_date, 'ihsg', 'idx composite', trend_idx_composite, updated_at
from public.fgi_snapshots
where trend_idx_composite is not null
on conflict (date, index_name, keyword) do update
set score = excluded.score,
    updated_at = excluded.updated_at;

insert into public.trend_snapshots (date, index_name, keyword, score, updated_at)
select week_date, 'ihsg', 'indeks harga saham gabungan',
       trend_indeks_harga_saham_gabungan, updated_at
from public.fgi_snapshots
where trend_indeks_harga_saham_gabungan is not null
on conflict (date, index_name, keyword) do update
set score = excluded.score,
    updated_at = excluded.updated_at;
