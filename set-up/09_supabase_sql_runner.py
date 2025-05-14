"""
09_supabase_sql_runner.py

A script to execute (run) SQL files against your Supabase Postgres instance.
- Use for bootstrapping tables, migrations, or agent-driven schema creation.
- Can be called by agents or RAG flows to update schema before retrieval.

Usage:
  python set-up/09_supabase_sql_runner.py --file features/agent_notice_board_supabase_schema.sql
  python set-up/09_supabase_sql_runner.py --file features/agent_data_supabase_schema.sql

Required env vars:
  SUPABASE_DB_URL (e.g., postgresql://user:pass@host:5432/db)
"""

import argparse
import os
import sys
import psycopg2

parser = argparse.ArgumentParser(description='Run a SQL file against Supabase Postgres.')
parser.add_argument('--file', required=True, help='Path to the .sql file to execute')
args = parser.parse_args()

SUPABASE_DB_URL = os.getenv('SUPABASE_DB_URL')
if not SUPABASE_DB_URL:
    print('Error: SUPABASE_DB_URL environment variable not set.')
    sys.exit(1)

if not os.path.isfile(args.file):
    print(f'Error: SQL file {args.file} not found.')
    sys.exit(1)

with open(args.file, 'r') as f:
    sql = f.read()

print(f'Connecting to Supabase Postgres...')
conn = psycopg2.connect(SUPABASE_DB_URL)
try:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f'Successfully ran {args.file}')
finally:
    conn.close()
