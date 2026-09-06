-- Additive fields used by the live synthetic criminal-record panel.
alter table public.criminal_records
  add column if not exists record_status text not null default 'unspecified',
  add column if not exists wanted_level smallint not null default 0,
  add column if not exists arrest_count smallint not null default 0,
  add column if not exists active_warrant boolean,
  add column if not exists conviction_count smallint not null default 0,
  add column if not exists primary_offense text,
  add column if not exists warrant_number text,
  add column if not exists last_arrest_date date,
  add column if not exists warrant_issue_date date;

create index if not exists criminal_records_identity_id_idx
  on public.criminal_records (identity_id);

do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conrelid = 'public.criminal_records'::regclass
       and conname = 'criminal_records_check'
  ) then
    alter table public.criminal_records
      add constraint criminal_records_check
      check (active_warrant = true or warrant_number is null);
  end if;
end;
$$;
