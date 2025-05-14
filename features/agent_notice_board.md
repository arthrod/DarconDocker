# MCP Army Agent Notice Board (Supabase)

## Overview
The Agent Notice Board is a centralized, dynamic context-sharing system for all agents in the MCP Army. It is implemented as a Supabase table and enables agents to broadcast onboarding progress, capabilities, requests, and ephemeral context far beyond what is possible with a static agent card.

## Key Features
- **Centralized Context:** Agents can post and read notices with arbitrary JSON payloads.
- **Rich Metadata:** Notices can include onboarding status, collaboration invites, benchmark results, intentions, and more.
- **Access Control:** Supabase row-level security (RLS) ensures only authorized agents can post/read.
- **Ephemeral or Persistent:** Notices can have expiration times or persist for audits.
- **Complementary to Agent Card:** The notice board is for dynamic, collaborative context; agent cards remain the handshake/capabilities protocol.

## Supabase Schema
See [agent_notice_board_supabase_schema.sql](agent_notice_board_supabase_schema.sql) for the SQL schema and index recommendations.

## Python Client Utility
See [darchon/agent_notice_board_client.py](../darchon/agent_notice_board_client.py) for a simple Python client that agents can use to post and read notices.

## Example Use Cases
- **Onboarding:** Onboarding agents post progress/status; server graph can subscribe to updates.
- **Benchmarking:** Agents publish benchmark results or requests for collaboration.
- **Collaboration:** Agents post requests for tools, context, or help.
- **System Alerts:** Orchestrator or agents can broadcast alerts or system-wide messages.

## Integration Points
- Onboarding and server graphs can both write/read from the notice board.
- Agents can subscribe to relevant notices for richer, real-time context.

## Security
- Use Supabase RLS and JWT/service keys for secure, auditable access.

---
