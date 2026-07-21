-- 20260721233330_llm_usage_attempts_status.sql
-- FinOps : rendre llm_usage réconciliable. Jusqu'ici la table ne comptait que le
-- DERNIER succès (pas les retries, pas les échecs totaux) -> écart prod 622 requêtes
-- facturées vs 11 lignes. On ajoute :
--   attempts    : nombre de requêtes OpenAI facturées pour cette génération (retries inclus)
--   status      : 'ok' (workout persisté) ou 'failed' (3 tentatives brûlées, 0 workout)
--   session_id  : rattachement à la séance (réconciliation), NULL si séance supprimée

alter table public.llm_usage
  add column if not exists attempts integer not null default 1 check (attempts >= 1),
  add column if not exists status text not null default 'ok' check (status in ('ok', 'failed')),
  add column if not exists session_id uuid;

create index if not exists llm_usage_status_created_idx
  on public.llm_usage (status, created_at desc);
