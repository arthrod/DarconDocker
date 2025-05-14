-- 1) Recreate the table
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE n8npyaigit (
  id            UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
  source        TEXT       NOT NULL,
  url           TEXT       NOT NULL,
  repo_name     TEXT       NOT NULL,
  repo_owner    TEXT       NOT NULL,
  branch        TEXT       NOT NULL,
  commit_hash   TEXT       NOT NULL,
  chunk_number  INT        NOT NULL,
  file_path     TEXT       NOT NULL,
  file_type     TEXT       NOT NULL,
  file_size     BIGINT     NOT NULL,
  title         TEXT       NOT NULL,
  summary       TEXT       NOT NULL,
  file_content  TEXT       NOT NULL,
  metadata      JSONB      NOT NULL,
  embedding     VECTOR(1536),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2) Recreate your match function
CREATE OR REPLACE FUNCTION match_n8npyaigit(
  query_embedding vector,
  match_count    int
)
RETURNS TABLE(
  id           UUID,
  source       TEXT,
  url          TEXT,
  repo_name    TEXT,
  repo_owner   TEXT,
  branch       TEXT,
  commit_hash  TEXT,
  chunk_number INT,
  file_path    TEXT,
  file_type    TEXT,
  file_size    BIGINT,
  title        TEXT,
  summary      TEXT,
  file_content TEXT,
  metadata     JSONB,
  embedding    vector,
  created_at   TIMESTAMPTZ
)
LANGUAGE sql STABLE AS $$
  SELECT * 
    FROM n8npyaigit
   ORDER BY embedding <=> query_embedding
   LIMIT match_count;
$$;

-- 3) (Optional) recreate your index
CREATE INDEX ON n8npyaigit USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);