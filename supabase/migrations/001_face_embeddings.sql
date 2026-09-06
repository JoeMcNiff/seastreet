-- Additive migration for Clearview embeddings and local cosine matching.
create schema if not exists extensions;
create extension if not exists vector with schema extensions;

-- This cast succeeds for an empty table or when every existing vector has
-- exactly 512 dimensions. It fails safely if incompatible data is present.
alter table public.image_embeddings
  alter column embedding type extensions.vector(512)
  using embedding::extensions.vector(512);

alter table public.identities
  add column if not exists external_ref text;

create unique index if not exists identities_external_ref_idx
  on public.identities (external_ref);

alter table public.identity_images
  add column if not exists sha256 text,
  add column if not exists face_rect real[] check (array_length(face_rect, 1) = 4);

create unique index if not exists identity_images_sha256_idx
  on public.identity_images (sha256)
  where sha256 is not null;

create unique index if not exists identity_images_storage_object_idx
  on public.identity_images (storage_bucket, storage_path);

alter table public.image_embeddings
  add column if not exists provider text not null default 'clearview',
  add column if not exists model_version text not null default 'demo-v1';

create unique index if not exists image_embeddings_model_idx
  on public.image_embeddings (image_id, provider, model_version);

create index if not exists image_embeddings_cosine_idx
  on public.image_embeddings using hnsw (embedding extensions.vector_cosine_ops);

alter table public.criminal_records
  add column if not exists record_type text not null default 'unspecified',
  add column if not exists record_data jsonb not null default '{}'::jsonb,
  add column if not exists external_ref text;

create unique index if not exists criminal_records_external_ref_idx
  on public.criminal_records (external_ref);

drop function if exists public.match_identity_embeddings(
  extensions.vector,
  double precision,
  integer
);

create function public.match_identity_embeddings(
  query_embedding extensions.vector(512),
  match_threshold double precision default 0.47,
  match_count integer default 10
)
returns table (
  identity_id uuid,
  display_name text,
  image_id uuid,
  similarity double precision
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
  select links.identity_id,
         identities.display_name,
         embeddings.image_id,
         1 - (embeddings.embedding <=> query_embedding) as similarity
    from public.image_embeddings as embeddings
    join public.identity_image_links as links
      on links.image_id = embeddings.image_id
     and links.status = 'active'
    join public.identities as identities
      on identities.id = links.identity_id
     and identities.status = 'active'
   where 1 - (embeddings.embedding <=> query_embedding) >= match_threshold
   order by embeddings.embedding <=> query_embedding
   limit greatest(1, least(match_count, 100));
$$;

revoke all on function public.match_identity_embeddings(extensions.vector, double precision, integer) from public, anon;
grant execute on function public.match_identity_embeddings(extensions.vector, double precision, integer) to authenticated, service_role;
