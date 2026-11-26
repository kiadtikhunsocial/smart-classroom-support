#!/usr/bin/env bash
# migrate_to_supabase.sh — copy the production database from Neon to Supabase.
#
# Usage (from the repo root, Docker running):
#   bash backend/scripts/migrate_to_supabase.sh check     # versions, row counts, target is empty
#   bash backend/scripts/migrate_to_supabase.sh dump      # pg_dump Neon -> backups/neon_<stamp>.dump
#   bash backend/scripts/migrate_to_supabase.sh restore   # pg_restore latest dump -> Supabase
#   bash backend/scripts/migrate_to_supabase.sh verify    # compare row counts + sequences
#   bash backend/scripts/migrate_to_supabase.sh lock      # enable RLS, revoke anon/authenticated
#
# Reads NEON_URL and SUPABASE_URL from .env.migrate (gitignored). Use the Supabase
# "Session pooler" string (port 5432, user postgres.<ref>), not the IPv6-only direct host.
# Plain postgresql:// URLs (no +psycopg2). Passwords are never printed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env.migrate}"
PG_IMAGE="${PG_IMAGE:-postgres:18}"
BACKUP_DIR="$ROOT/backups"

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE (NEON_URL=..., SUPABASE_URL=...)"; exit 1; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

norm() {  # drop the SQLAlchemy driver suffix, force sslmode=require for remote hosts
  local u="${1/postgresql+psycopg2:/postgresql:}"
  u="${u/postgres:\/\//postgresql://}"
  case "$u" in *sslmode=*|*@localhost*|*@127.0.0.1*|*@postgres:*|*@host.docker.internal*) ;; *\?*) u="$u&sslmode=require";; *) u="$u?sslmode=require";; esac
  printf '%s' "$u"
}
mask() { printf '%s' "$1" | sed -E 's#://([^:/@]+):[^@]*@#://\1:***@#'; }

SRC="$(norm "${NEON_URL:?NEON_URL not set}")"
DST="$(norm "${SUPABASE_URL:?SUPABASE_URL not set}")"
NET_ARGS=()
[ -n "${DOCKER_NETWORK:-}" ] && NET_ARGS=(--network "$DOCKER_NETWORK")

pg() {  # run a postgres client tool in a throwaway container; backups/ mounted at /b
  MSYS_NO_PATHCONV=1 docker run --rm -i "${NET_ARGS[@]}" -v "$BACKUP_DIR:/b" "$PG_IMAGE" "$@"
}
q() { pg psql "$1" -X -v ON_ERROR_STOP=1 -Atc "$2"; }

COUNT_SQL="SELECT string_agg(format('SELECT %L AS t, count(*) AS n FROM public.%I', tablename, tablename), ' UNION ALL ') FROM pg_tables WHERE schemaname='public'"
counts() {
  local gen; gen="$(q "$1" "$COUNT_SQL")"
  [ -z "$gen" ] && { echo "(no tables)"; return; }
  q "$1" "SELECT t||' '||n FROM ($gen) x ORDER BY t"
}

mkdir -p "$BACKUP_DIR"
case "${1:-}" in
  check)
    echo "source: $(mask "$SRC")"; q "$SRC" "SELECT version()"
    echo "target: $(mask "$DST")"; q "$DST" "SELECT version()"
    echo "--- source extensions"; q "$SRC" "SELECT extname||' '||extversion FROM pg_extension ORDER BY 1"
    echo "--- source row counts"; counts "$SRC"
    echo "--- target public tables (must be 0 before restore)"
    q "$DST" "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
    ;;
  dump)
    stamp="$(date +%Y%m%d_%H%M%S)"
    pg pg_dump "$SRC" -Fc -n public --no-owner --no-privileges -f "/b/neon_$stamp.dump"
    counts "$SRC" > "$BACKUP_DIR/neon_$stamp.counts.txt"
    ls -l "$BACKUP_DIR/neon_$stamp.dump"; echo "counts -> backups/neon_$stamp.counts.txt"
    ;;
  restore)
    f="$(ls -t "$BACKUP_DIR"/neon_*.dump | head -1)"; f="/b/$(basename "$f")"
    n="$(q "$DST" "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
    if [ "$n" != "0" ] && [ "${FORCE_CLEAN:-}" != "1" ]; then
      echo "target public schema has $n tables; set FORCE_CLEAN=1 to drop and replace them"; exit 1
    fi
    echo "restoring $f -> $(mask "$DST")"
    # Render the dump as SQL and drop settings an older target server does not know
    # (pg_dump 17+ emits SET transaction_timeout). With FORCE_CLEAN the old public
    # tables, sequences and enum types are dropped inside the same transaction, so a
    # failed restore leaves the target exactly as it was.
    { if [ "$n" != "0" ]; then
        echo "DO \$\$ DECLARE r record; BEGIN
          FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
            EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename); END LOOP;
          FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname='public' LOOP
            EXECUTE format('DROP SEQUENCE IF EXISTS public.%I CASCADE', r.sequencename); END LOOP;
          FOR r IN SELECT t.typname FROM pg_type t JOIN pg_namespace s ON s.oid=t.typnamespace
                   WHERE s.nspname='public' AND t.typtype='e' LOOP
            EXECUTE format('DROP TYPE IF EXISTS public.%I CASCADE', r.typname); END LOOP;
        END \$\$;"
      fi
      pg pg_restore --no-owner --no-privileges -f - "$f" \
        | sed -E '/^SET transaction_timeout/d; /^CREATE SCHEMA public;/d; /^COMMENT ON SCHEMA public /d'
    } | pg psql "$DST" -X -q -v ON_ERROR_STOP=1 --single-transaction -f - >/dev/null
    echo "restore ok"
    ;;
  verify)
    diff <(counts "$SRC") <(counts "$DST") && echo "row counts match"
    echo "--- sequences behind max(id) (should be empty)"
    gen="$(q "$DST" "SELECT string_agg(format('SELECT %L AS s, (SELECT coalesce(max(%I),0) FROM public.%I) AS m, (SELECT last_value FROM public.%I) AS l', s.relname, a.attname, t.relname, s.relname), ' UNION ALL ')
      FROM pg_class s JOIN pg_namespace n ON n.oid=s.relnamespace AND n.nspname='public'
      JOIN pg_depend d ON d.objid=s.oid AND d.deptype IN ('a','i')
      JOIN pg_class t ON t.oid=d.refobjid JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
      WHERE s.relkind='S'")"
    [ -n "$gen" ] && q "$DST" "SELECT s||' max='||m||' last='||l FROM ($gen) x WHERE l < m"
    echo "--- enums / indexes (source vs target)"
    for u in "$SRC" "$DST"; do
      q "$u" "SELECT (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' AND t.typtype='e')||' enums, '||(SELECT count(*) FROM pg_indexes WHERE schemaname='public')||' indexes'"
    done
    ;;
  lock)
    # Supabase exposes public tables over its REST API; the backend connects as postgres and bypasses RLS.
    q "$DST" "DO \$\$ DECLARE r record; BEGIN
      FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
      END LOOP;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
      END IF; END \$\$"
    q "$DST" "SELECT 'tables without RLS: '||count(*) FROM pg_tables WHERE schemaname='public' AND NOT rowsecurity"
    q "$DST" "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')
      THEN 'anon can read users: '||has_table_privilege('anon','public.users','select') ELSE 'no anon role (not Supabase)' END"
    ;;
  *) sed -n '2,12p' "$0"; exit 1;;
esac
