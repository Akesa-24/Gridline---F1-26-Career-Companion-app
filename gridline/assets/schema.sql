-- Gridline — shared career database
-- Paste this whole file into Supabase > SQL Editor > New query, then press Run.
-- It is safe to run more than once.

create table if not exists public.gridline_careers (
    id          uuid primary key,
    name        text not null,
    created_at  timestamptz not null default now()
);

create table if not exists public.gridline_events (
    seq         bigserial primary key,
    uid         uuid not null unique,
    career_id   uuid not null references public.gridline_careers(id) on delete cascade,
    author      text not null,
    kind        text not null,
    payload     jsonb not null,
    created_at  double precision not null,
    inserted_at timestamptz not null default now()
);

create index if not exists gridline_events_career_seq on public.gridline_events (career_id, seq);

-- The log is append-only for the app: it can read and insert, never edit or delete.
-- The project owner can still clean up from the Supabase dashboard.
alter table public.gridline_careers enable row level security;
alter table public.gridline_events  enable row level security;

drop policy if exists gridline_careers_read   on public.gridline_careers;
drop policy if exists gridline_careers_insert on public.gridline_careers;
drop policy if exists gridline_events_read    on public.gridline_events;
drop policy if exists gridline_events_insert  on public.gridline_events;

create policy gridline_careers_read   on public.gridline_careers for select to anon, authenticated using (true);
create policy gridline_careers_insert on public.gridline_careers for insert to anon, authenticated with check (true);
create policy gridline_events_read    on public.gridline_events  for select to anon, authenticated using (true);
create policy gridline_events_insert  on public.gridline_events  for insert to anon, authenticated
    with check (octet_length(payload::text) < 200000);

grant usage on schema public to anon, authenticated;
grant select, insert on public.gridline_careers to anon, authenticated;
grant select, insert on public.gridline_events  to anon, authenticated;
grant usage, select on sequence public.gridline_events_seq_seq to anon, authenticated;
