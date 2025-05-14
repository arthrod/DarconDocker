from dotenv import load_dotenv
import os
import streamlit as st
import psycopg2
import pandas as pd
import requests

# Path to your .env file
load_dotenv()

# ---------------------------
# Local Postgres Credentials from .env
# ---------------------------
default_postgres_host = os.getenv("POSTGRES_HOST", "10.147.20.2")
default_postgres_port = os.getenv("POSTGRES_PORT", "5432")
default_postgres_db = os.getenv("POSTGRES_DB", "postgres")
default_postgres_user = os.getenv("POSTGRES_USER", "")
default_postgres_password = os.getenv("POSTGRES_PASSWORD", "")

def get_postgres_databases(host, port, user, password):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname="postgres",  # Connect to default db to list others
            user=user,
            password=password
        )
        cur = conn.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        databases = [db[0] for db in cur.fetchall()]
        cur.close()
        conn.close()
        return databases, None
    except Exception as e:
        return None, str(e)

def get_postgres_tables(host, port, dbname, user, password):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE';
        """)
        tables = [table[0] for table in cur.fetchall()]
        cur.close()
        conn.close()
        return tables, None
    except Exception as e:
        return None, str(e)

def main():
    st.title("Database Configuration Dashboard")
    tabs = st.tabs(["Local Postgres", "Supabase Dashboard"])

    # ============================
    # Local Postgres Tab
    # ============================
    with tabs[0]:
        st.header("Execute SQL on Local Postgres")
        st.write("Using credentials loaded from your .env file:")
        st.write(
            f"**Host:** {default_postgres_host}  |  **Port:** {default_postgres_port}  |  "
            f"**User:** {default_postgres_user}"
        )
        
        # Create two columns for databases and tables
        col1, col2 = st.columns(2)
        
        # Database dropdown in first column
        with col1:
            st.subheader("Select Database")
            databases, db_error = get_postgres_databases(
                default_postgres_host,
                default_postgres_port,
                default_postgres_user,
                default_postgres_password
            )
            
            if db_error:
                st.error(f"Error fetching databases: {db_error}")
                selected_db = None
            elif databases:
                selected_db = st.selectbox(
                    "Available Databases",
                    options=databases,
                    help="Select a database to work with"
                )
            else:
                st.info("No databases found")
                selected_db = None

        # Tables dropdown in second column
        with col2:
            st.subheader("Select Table")
            if selected_db:
                tables, table_error = get_postgres_tables(
                    default_postgres_host,
                    default_postgres_port,
                    selected_db,
                    default_postgres_user,
                    default_postgres_password
                )
                
                if table_error:
                    st.error(f"Error fetching tables: {table_error}")
                elif tables:
                    selected_table = st.selectbox(
                        "Available Tables",
                        options=tables,
                        help="Select a table to work with"
                    )
                    if selected_table:
                        st.write(f"Selected: **{selected_table}**")
                else:
                    st.info("No tables found in selected database")
            else:
                st.info("Please select a database first")

        st.markdown("---")
        
        # SQL Editor section
        st.subheader("SQL Editor")
        # Initialize a dynamic key for the SQL editor form if not already set.
        if "sql_form_key" not in st.session_state:
            st.session_state["sql_form_key"] = 0
        
        # Provide a reset button that increments the key,
        # thereby forcing the SQL editor and its output to reinitialize.
        if st.button("Reset SQL Editor", key="reset_sql"):
            st.session_state["sql_form_key"] += 1

        # Container for the SQL editor and any output (such as a table)
        with st.container():
            with st.form(key=f"sql_form_{st.session_state['sql_form_key']}"):
                sql_query = st.text_area("Enter SQL Query", height=200)
                execute_sql = st.form_submit_button("Execute SQL on Local Postgres")
            
            if execute_sql:
                if sql_query.strip() == "":
                    st.error("Please enter a SQL query.")
                else:
                    # Convert meta command (\dt) to equivalent SQL if needed.
                    sql_command = sql_query.strip()
                    if sql_command.startswith("\\dt"):
                        sql_command = (
                            "SELECT schemaname, tablename "
                            "FROM pg_catalog.pg_tables "
                            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema');"
                        )
                    try:
                        conn = psycopg2.connect(
                            host=default_postgres_host,
                            port=default_postgres_port,
                            dbname=selected_db,
                            user=default_postgres_user,
                            password=default_postgres_password
                        )
                        cur = conn.cursor()
                        cur.execute(sql_command)
                        
                        # If it's a SELECT query, fetch and display the results.
                        if sql_command.lower().startswith("select"):
                            results = cur.fetchall()
                            col_names = [desc[0] for desc in cur.description]
                            df = pd.DataFrame(results, columns=col_names)
                            st.dataframe(df)
                        else:
                            conn.commit()
                            st.success("SQL executed successfully on Local Postgres!")
                        
                        cur.close()
                        conn.close()
                    except Exception as e:
                        st.error(f"Error executing SQL on Local Postgres: {e}")

    # ============================
    # Supabase Dashboard Tab
    # ============================
    with tabs[1]:
        st.header("Supabase Dashboard")
        st.write("Click the link below to open your Supabase configuration dashboard:")
        
        proxy_url = "http://localhost:8880"
        st.markdown(f"[Open Supabase Dashboard in a new tab]({proxy_url})", unsafe_allow_html=True)
        
        # Add table selection dropdown right after dashboard link
        st.markdown("---")
        st.subheader("Tables in Public Schema")
        
        SUPABASE_URL = os.getenv("SUPABASE_URL", "")
        SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY", "")
        
        if SUPABASE_URL and SUPABASE_API_KEY:
            endpoint = f"{SUPABASE_URL}/rest/v1/rpc/get_public_tables"
            headers = {
                "apikey": SUPABASE_API_KEY,
                "Authorization": f"Bearer {SUPABASE_API_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
            
            response = requests.post(endpoint, headers=headers, json={})
            if response.status_code == 200:
                tables = response.json()
                if tables:
                    # Convert to dropdown with emoji
                    table_names = [f"📋 {table['table_name']}" for table in tables]
                    selected_table = st.selectbox(
                        "Available Tables",
                        options=table_names,
                        help="Select a table to view"
                    )
                    if selected_table:
                        # Strip emoji for actual table name
                        actual_table = selected_table.split(' ', 1)[1]
                        st.write(f"Selected table: **{actual_table}**")
                else:
                    st.info("No tables found in the public schema.")
            else:
                st.error(f"Error fetching tables: {response.status_code} - {response.text}")
        else:
            st.error("Supabase URL or Service Key is not set.")
        
        st.markdown("---")
        st.header("Supabase Setup Tutorial")
        st.write(
            "Below is a YouTube video tutorial that explains how to set up your Supabase account "
            "and configure your dashboard for embedding."
        )
        st.video("https://www.youtube.com/watch?v=-jISW-jVG-s&list=PL8HkCX2C5h0W-Fr3NEfOprzTRHICMGyOX")
    
    st.divider()
    st.header("Chat with Database AI Bot & SQL Expert")
    
    # Initialize chat history in session state if it doesn't exist
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    
    # Display chat history
    if st.session_state["chat_history"]:
        for sender, message in st.session_state["chat_history"]:
            if sender == "User":
                st.markdown(f"**You:** {message}")
            else:
                st.markdown(f"**Bot:** {message}")
    
    # Chat form for new message
    with st.form(key="chat_form"):
        user_message = st.text_input("Enter your message here:")
        send_message = st.form_submit_button("Send")
    
    if send_message and user_message.strip():
        # Append the user message to the chat history
        st.session_state["chat_history"].append(("User", user_message.strip()))
        
        # Here you would integrate your AI bot logic.
        # For now, we simply use a placeholder response.
        bot_reply = "This is a placeholder reply from the Database AI Bot & SQL Expert."
        st.session_state["chat_history"].append(("Bot", bot_reply))
        
        # Rerun the app to display the updated chat history.
        st.rerun()

if __name__ == "__main__":
    main()
