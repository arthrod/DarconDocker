-- Supabase SQL schema for MCP Army Persistent Agent Data Table
-- This table stores detailed metadata, onboarding context, KG/Graphiti summaries, and user intent for each agent.
-- PLANNED: Expand Supabase Python client for full agent_data CRUD operations.
-- Planned methods:
--   - create_agent_data(agent_id, metadata)
--   - read_agent_data(agent_id)
--   - update_agent_data(agent_id, updates)
--   - delete_agent_data(agent_id)

create table if not exists agent_data (
    id uuid primary key default gen_random_uuid(),
    agent_id text not null unique,             -- Internal or user-facing agent identifier
    agent_name text not null,                  -- Human-readable name
    description text,                          -- Freeform description
    status text default 'inactive',            -- 'inactive', 'onboarding', 'active', 'error', etc.
    repo_url text,                             -- Associated repo (from docker_repos)
    docker_image text,                         -- Docker image/tag
    endpoints jsonb,                           -- List of endpoints (e.g., /invoke, /health, etc.)
    capabilities jsonb,                        -- Structured capabilities/skills
    config jsonb,                              -- Agent config (env, ports, etc.)
    onboarding_date timestamptz default now(), -- When onboarding started
    onboarding_context jsonb,                  -- Full onboarding context (user request, answers, etc.)
    user_intent text,                          -- User's initial "What would you like?" request
    kg_summary text,                           -- Graphiti/Neo4j KG summary (purpose, relationships)
    kg_uri text,                               -- Link to KG or Neo4j node/graph
    conversation_log jsonb,                    -- Optionally store onboarding/user-agent conversation
    last_updated timestamptz default now(),
    created_by text,                           -- User or system who initiated agent
    extra jsonb                                -- For future extensibility
);

-- Indexes for fast lookup
create index if not exists idx_agent_name on agent_data(agent_name);
create index if not exists idx_status on agent_data(status);
create index if not exists idx_onboarding_date on agent_data(onboarding_date);

-- Row-level security (RLS) and policies should be configured in Supabase dashboard for agent access control.
