-- Supabase SQL schema for MCP Army Agent Notice Board
create table if not exists agent_notice_board (
    id uuid primary key default gen_random_uuid(),
    agent_id text not null,
    timestamp timestamptz not null default now(),
    notice_type text not null, -- e.g., 'onboarding', 'benchmark', 'alert', 'context', etc.
    payload jsonb not null,    -- Arbitrary JSON for extra context
    visibility text default 'public', -- 'public', 'private', or custom scopes
    expires_at timestamptz     -- Optional: for ephemeral notices
);

-- Optional: Indexes
create index if not exists idx_notice_type on agent_notice_board(notice_type);
create index if not exists idx_agent_id on agent_notice_board(agent_id);
create index if not exists idx_visibility on agent_notice_board(visibility);

-- Row-level security (RLS) and policies should be configured in Supabase dashboard for agent access control.
