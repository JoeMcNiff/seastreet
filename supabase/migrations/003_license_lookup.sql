-- Keep live driver-license lookups fast as the mock DMV table grows.
create index if not exists licenses_number_idx
  on public.licenses (number);
