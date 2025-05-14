-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the documentation chunks table
CREATE TABLE n8nxpyai (
    id bigserial PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    repo_owner TEXT NOT NULL,
    branch TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    chunk_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,
    file_size BIGINT,
    title TEXT,
    summary TEXT,
    file_content TEXT,
    metadata JSONB,
    embedding VECTOR(1536) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient vector similarity search
CREATE INDEX IF NOT EXISTS idx_n8nxpyai_embedding
    ON n8nxpyai USING ivfflat (embedding VECTOR_COSINE_OPS)
    WITH (lists = 100);

-- Function for similarity matching
CREATE OR REPLACE FUNCTION match_n8nxpyai(
    query_embedding VECTOR(1536),
    match_count INTEGER
)
RETURNS TABLE (
    id BIGINT,
    source TEXT,
    similarity REAL
) AS $$
    SELECT id,
           source,
           1 - (embedding <=> query_embedding) AS similarity
    FROM n8nxpyai
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$ LANGUAGE SQL STABLE;

-- Supabase Security Settings

-- Enable Row-Level Security (RLS) on the table
ALTER TABLE n8nxpyai ENABLE ROW LEVEL SECURITY;

-- Create a policy that allows anyone to read
CREATE POLICY "Allow public read access"
  ON n8nxpyai
  FOR SELECT
  TO public
  USING (true);
