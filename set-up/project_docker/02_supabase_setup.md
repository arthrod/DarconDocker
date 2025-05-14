# 02_supabase_setup.md

## Supabase Setup for MCP Army

### 1. Create a Supabase Project
- Go to https://app.supabase.com/ and sign in.
- Click "New project" and fill in:
  - Project name
  - Database password (store securely)
  - Choose a region
- Click "Create new project" and wait for provisioning.

### 2. Get Your API Credentials
- In your project dashboard, go to **Project Settings > API**
- Copy your `SUPABASE_URL` and `SUPABASE_API_KEY` for later use.

### 3. Create Tables
#### a) Agent Notice Board Table
- In the Supabase dashboard, go to **Table Editor > New Table**
- Use the schema from `features/agent_notice_board_supabase_schema.sql`:
  - You can copy the SQL and run it in the **SQL Editor**
- Confirm table and columns are created as expected

#### b) Agent Data Table
- Repeat above, using the schema in `features/agent_data_supabase_schema.sql`

### 4. Enable Row-Level Security (RLS)
- In the Table Editor, select each table
- Click "Enable RLS"
- Add policies as needed (for now, you can allow authenticated users full access)

### 5. (Optional) Create Service Role Key
- In **Project Settings > API**, copy the `service_role` key for backend/server-side access

### 6. (Optional) Set Up Neo4j/Graphiti
- Download and install Neo4j Desktop: https://neo4j.com/download/
- Create a new local database
- For Graphiti, follow: https://github.com/graphiti-api/graphiti

---

**Supabase is now ready. Continue to the next setup step.**
