-- 20260801120000_llm_usage_error_reason.sql
-- Audit 2026-08 (issue #124) : 34 % des générations LLM échouent sans que le
-- motif de rejet de validation soit persisté nulle part. On ajoute error_reason
-- sur llm_usage pour cibler les enveloppes insatisfiables (ex : longues sorties
-- vélo 167-174 min dont le bloc principal continu est quasi impossible à caser).

alter table public.llm_usage
  add column if not exists error_reason text;

comment on column public.llm_usage.error_reason is
  'Motif du dernier rejet (validation enveloppe ou erreur API) quand status=failed. NULL sinon.';
