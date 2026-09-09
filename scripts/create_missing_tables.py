import subprocess, os

REMOTE = ["docker", "exec", "smart_classroom_db", "psql", "-h", "host.docker.internal", "-p", "15432", "-U", "postgres", "-d", "railway"]

DDL = """
CREATE TABLE IF NOT EXISTS chatbot_logs (
  id SERIAL PRIMARY KEY,
  user_id TEXT,
  message TEXT,
  ai_response TEXT,
  intent TEXT,
  resolved BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sales_leads (
  id SERIAL PRIMARY KEY,
  user_id TEXT,
  name TEXT,
  phone TEXT,
  interest TEXT,
  products TEXT,
  source TEXT DEFAULT 'LINE',
  note TEXT,
  status TEXT DEFAULT 'new',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chatbot_profiles (
  user_id TEXT PRIMARY KEY,
  profile JSONB DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS line_sessions (
  user_id TEXT PRIMARY KEY,
  session JSONB DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT now()
);
"""
for stmt in DDL.split(";"):
    s = stmt.strip()
    if not s:
        continue
    r = subprocess.run(REMOTE + ["-c", s], capture_output=True, text=True)
    if r.returncode != 0:
        print("ERR:", s[:60], r.stderr[:120])
    else:
        print("OK:", s.split()[0], s.split()[2] if len(s.split())>2 else "")
