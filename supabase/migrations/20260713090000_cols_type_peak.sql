-- Distingue les cols routiers (mountain_pass OSM) des sommets/crêts (natural=peak OSM)
-- dans le référentiel partagé `cols`. Les lignes existantes (toutes issues de
-- mountain_pass=yes) prennent la valeur par défaut 'col'.
alter table public.cols
  add column type text not null default 'col'
    check (type in ('col', 'peak'));

comment on column public.cols.type is
  'Catégorie du point OSM : col (mountain_pass=yes) ou sommet (natural=peak).';
