#!/usr/bin/env python3
"""Migrate data from local Postgres to Railway Postgres, keeping only columns that
exist in BOTH schemas (Railway is a newer schema without id_uuid). Uses psql COPY
(csv) which handles escaping/quoting correctly.
Usage:  python scripts/migrate_to_railway.py   (tunnel to :15432 must be open)
"""
import subprocess
import sys

LOCAL = ["docker", "exec", "smart_classroom_db", "psql", "-U", "postgres", "-d", "smart_classroom", "-t", "-A", "-P", "format=unaligned", "-P", "fieldsep=,"]
REMOTE = ["docker", "exec", "smart_classroom_db", "psql", "-h", "host.docker.internal", "-p", "15432", "-U", "postgres", "-d", "railway", "-t", "-A"]

TABLES = ["organizations", "rooms", "devices", "users", "kb_articles",
          "settings", "pm_plans"]


def cols(dsn, tbl):
    out = subprocess.run(dsn + ["-c", f"SELECT string_agg(column_name, ',' ORDER BY ordinal_position) AS c FROM information_schema.columns WHERE table_name='{tbl}'"], capture_output=True, text=True)
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    return lines[0].strip().split(",") if lines else []


def main():
    for tbl in TABLES:
        lc = cols(LOCAL, tbl)
        rc = cols(REMOTE, tbl)
        common = [c for c in lc if c in rc]
        if not common:
            print(f"SKIP {tbl}: no common cols (local={lc}, rail={rc})")
            continue
        colstr = ",".join(common)
        # dump from local as CSV
        dump = subprocess.run(LOCAL + ["-c", f"COPY (SELECT {colstr} FROM {tbl}) TO STDOUT WITH (FORMAT csv)"], capture_output=True, text=True)
        if dump.returncode != 0 or not dump.stdout.strip():
            print(f"EMPTY/ERR {tbl}: {dump.stderr[:100]}")
            continue
        data = dump.stdout.encode()
        # load into railway, wrap in transaction with truncate? No — just insert ignore dup
        sql = f"TRUNCATE {tbl} RESTART IDENTITY CASCADE;\\nCOPY {tbl} ({colstr}) FROM STDIN WITH (FORMAT csv);"
        # psql needs the SQL via stdin; send COPY line then data then \.
        stdin = f"COPY {tbl} ({colstr}) FROM STDIN WITH (FORMAT csv);\n".encode() + data + b"\\.\n"
        load = subprocess.run(REMOTE + ["-q"], input=stdin, capture_output=True)
        if load.returncode != 0:
            print(f"LOAD_ERR {tbl}: {load.stderr.decode()[:200]}")
        else:
            print(f"OK {tbl}: {len(data.splitlines())} rows, cols={common}")


if __name__ == "__main__":
    main()
