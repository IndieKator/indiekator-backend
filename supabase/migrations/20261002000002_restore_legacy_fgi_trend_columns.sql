-- Restore per-keyword columns as backward-compatibility mirrors.
-- public.trend_snapshots remains the normalized source of truth.
alter table public.fgi_snapshots
    add column if not exists trend_ihsg numeric,
    add column if not exists trend_idx_composite numeric,
    add column if not exists trend_indeks_harga_saham_gabungan numeric;

update public.fgi_snapshots as f
set trend_ihsg = ihsg.score,
    trend_idx_composite = idx.score,
    trend_indeks_harga_saham_gabungan = full_name.score
from public.trend_snapshots as ihsg,
     public.trend_snapshots as idx,
     public.trend_snapshots as full_name
where ihsg.date = f.week_date
  and ihsg.index_name = 'ihsg'
  and ihsg.keyword = 'ihsg'
  and idx.date = f.week_date
  and idx.index_name = 'ihsg'
  and idx.keyword = 'idx composite'
  and full_name.date = f.week_date
  and full_name.index_name = 'ihsg'
  and full_name.keyword = 'indeks harga saham gabungan';

alter table public.fgi_snapshots
    alter column trend_ihsg set not null,
    alter column trend_idx_composite set not null,
    alter column trend_indeks_harga_saham_gabungan set not null,
    add constraint fgi_snapshots_trend_ihsg_range
        check (trend_ihsg between 0 and 100),
    add constraint fgi_snapshots_trend_idx_composite_range
        check (trend_idx_composite between 0 and 100),
    add constraint fgi_snapshots_trend_full_name_range
        check (trend_indeks_harga_saham_gabungan between 0 and 100);

create or replace function public.sync_fgi_legacy_trend_columns()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.index_name <> 'ihsg' then
        return new;
    end if;

    case new.keyword
        when 'ihsg' then
            update public.fgi_snapshots
            set trend_ihsg = new.score
            where week_date = new.date;
        when 'idx composite' then
            update public.fgi_snapshots
            set trend_idx_composite = new.score
            where week_date = new.date;
        when 'indeks harga saham gabungan' then
            update public.fgi_snapshots
            set trend_indeks_harga_saham_gabungan = new.score
            where week_date = new.date;
        else
            null;
    end case;

    return new;
end;
$$;

revoke all on function public.sync_fgi_legacy_trend_columns() from public, anon, authenticated;

drop trigger if exists sync_fgi_legacy_trends on public.trend_snapshots;
create trigger sync_fgi_legacy_trends
after insert or update of score on public.trend_snapshots
for each row execute function public.sync_fgi_legacy_trend_columns();
