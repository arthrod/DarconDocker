# 05_notice_board_and_agent_data.md

## Agent Notice Board & Persistent Agent Data (Supabase)

### 1. Deploy Agent Notice Board Table
- In Supabase, open **SQL Editor**
- Paste the contents of `features/agent_notice_board_supabase_schema.sql` and run
- Confirm table and columns are created

### 2. Deploy Agent Data Table
- In Supabase, open **SQL Editor**
- Paste the contents of `features/agent_data_supabase_schema.sql` and run
- Confirm table and columns are created

### 3. Enable Row-Level Security (RLS)
- In Table Editor, select each table
- Click "Enable RLS"
- Add policies (for now, allow authenticated users full access)

### 4. Configure Supabase Credentials for Local Dev
- Create a `.env` file in your project root or in `darchon/`:
```
SUPABASE_URL=your_supabase_url
SUPABASE_API_KEY=your_service_key
```

### 5. Test Notice Board Client
- Run example post/read with the Python client:
```bash
python darchon/agent_notice_board_client.py --post --agent_id=my_agent --notice_type=onboarding_start --payload='{"step":"init"}'
python darchon/agent_notice_board_client.py --read --agent_id=my_agent
```

### 6. (Optional) Integrate Graphiti/Neo4j for KG
- If using a knowledge graph, set up Graphiti or Neo4j and connect it to your agent data pipeline.
- **PLANNED:** Build out integration for agent-driven KG summaries.
- Planning method signature:
  ```python
  def update_agent_kg_summary(agent_id: str, kg_summary: dict) -> None:
      """Update agent's knowledge graph summary in Neo4j/Graphiti."""
      pass
  ```
- Store KG summary and URI in the `agent_data` table for each agent

---

**Your notice board and agent data tables are now ready for onboarding, context sharing, and persistent agent metadata. Continue to the next setup step.**
