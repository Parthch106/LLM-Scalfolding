-- ============================================================
-- Vector Search Upgrade for Supabase
-- Run this in your Supabase project: SQL Editor → New Query → Paste → Run
-- ============================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Add embedding column to celestial_objects table
-- (OpenAI text-embedding-3-small uses 1536 dimensions)
ALTER TABLE celestial_objects ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- 3. Create the Semantic Search RPC function
CREATE OR REPLACE FUNCTION match_celestial_objects (
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id uuid,
  catalog_id text,
  name text,
  object_type text,
  observation_status text,
  priority text,
  tags text[],
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    id, catalog_id, name, object_type, observation_status, priority, tags,
    1 - (embedding <=> query_embedding) AS similarity
  FROM celestial_objects
  WHERE 1 - (embedding <=> query_embedding) > match_threshold
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
