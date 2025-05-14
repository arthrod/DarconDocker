from __future__ import annotations
from dotenv import load_dotenv
import streamlit as st
import logfire
import asyncio
import nest_asyncio
import os
import sys

# Initialize session state for selected tab - make sure Chat is ALWAYS the default
if "selected_tab" not in st.session_state:
    st.session_state.selected_tab = "Chat"

# Force reset to Chat tab if requested via special parameter
if st.query_params.get("reset") == "true":
    # Clear session state
    for key in list(st.session_state.keys()):
        if key != "_init_complete":
            del st.session_state[key]
    # Restore default tab
    st.session_state.selected_tab = "Chat"

# Set page config - must be the first Streamlit command
st.set_page_config(
    page_title="Darchon | Docker MCP Server",
    page_icon="🥷",
    layout="wide",
)

# Apply nest_asyncio to allow nested asyncio loops
nest_asyncio.apply()

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Utilities and styles
from utils.utils import get_clients
from streamlit_pages.styles import load_css

# Streamlit pages
from streamlit_pages.chat import chat_tab
from streamlit_pages.environment import environment_tab
from streamlit_pages.documentation import documentation_tab
from streamlit_pages.agent_service import agent_service_tab
from streamlit_pages.command_center import command_center_tab
from streamlit_pages.agent_insights import agent_insights_tab
from streamlit_pages.integrated_observability import integrated_observability_tab
from streamlit_pages.langfuse_dashboard import langfuse_dashboard_tab
from streamlit_pages.agent_builder import agent_builder_tab

# Load environment variables from .env file
load_dotenv()

# Initialize session state to ensure persistence between page changes
if "initialized" not in st.session_state:
    # Mark initialization as complete
    st.session_state.initialized = True

# Ensure environment variables match session state
if "db_type" in st.session_state:
    os.environ["DATABASE_TYPE"] = st.session_state.db_type
else:
    # If db_type not in session state, initialize it from environment or default to supabase
    default_db_type = os.environ.get("DATABASE_TYPE", "supabase")
    st.session_state.db_type = default_db_type
    os.environ["DATABASE_TYPE"] = default_db_type

if "rag_table" in st.session_state:
    os.environ["RAG_TABLE"] = st.session_state.rag_table
    # Also set VECTOR_SEARCH_TABLE for compatibility
    os.environ["VECTOR_SEARCH_TABLE"] = st.session_state.rag_table

# Get the clients (now will use the correct database type)
openai_client, db_client = get_clients()

# Store the db_client in session state for retrieval in other pages
if db_client:
    st.session_state.db_client = db_client

# Load custom CSS styles
load_css()

# Configure logfire to suppress warnings (optional)
logfire.configure(send_to_logfire='never')

async def main():
    # Check for tab query parameter
    query_params = st.query_params
    if "tab" in query_params:
        tab_name = query_params["tab"]
        valid_tabs = ["Chat", "Environment", "Documentation", "Agent Service", 
                     "Agent Builder", "Command Center", "Agent Insights", 
                     "Observability", "Langfuse"]
        if tab_name in valid_tabs:
            st.session_state.selected_tab = tab_name


    # Enhanced sidebar navigation
    with st.sidebar:
        st.image("public/Archon.png", width=200)
        
        # Stylish header for navigation
        st.markdown("""
        <style>
        .sidebar-header {
            font-size: 22px;
            font-weight: bold; 
            margin-bottom: 12px;
            border-bottom: 2px solid #444;
            padding-bottom: 6px;
        }
        .sidebar-subheader {
            font-size: 16px;
            font-weight: bold;
            margin-top: 20px;
            margin-bottom: 8px;
            color: #f0f0f0;
        }
        .sidebar-section {
            margin-bottom: 20px;
        }
        .sidebar-btn {
            margin-bottom: 8px;
        }
        </style>
        <div class='sidebar-header'>Navigation</div>
        """, unsafe_allow_html=True)
        
        # Initialize session state for selected tab if not present
        if "selected_tab" not in st.session_state:
            st.session_state.selected_tab = "Chat"
        
        # Core navigation section
        st.markdown("<div class='sidebar-subheader'>Core</div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            chat_active = st.session_state.selected_tab == "Chat"
            chat_button = st.button("💬 Chat", use_container_width=True, key="chat_button", 
                                   help="Go to Chat tab", type="primary" if chat_active else "secondary")
        with col2:    
            env_active = st.session_state.selected_tab == "Environment"
            env_button = st.button("⚙️ Config", use_container_width=True, key="env_button",
                                  help="App configuration", type="primary" if env_active else "secondary")
        docs_active = st.session_state.selected_tab == "Documentation"    
        docs_button = st.button("📚 Documentation", use_container_width=True, key="docs_button",
                               help="View documentation", type="primary" if docs_active else "secondary")
        st.markdown("---")
        # Agent Management section
        st.markdown("<div class='sidebar-subheader'>Agent Management</div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            service_active = st.session_state.selected_tab == "Agent Service"
            service_button = st.button("🔄 Service", use_container_width=True, key="service_button",
                                      help="Manage agent services", type="primary" if service_active else "secondary")
        with col2:
            builder_active = st.session_state.selected_tab == "Agent Builder"
            agent_builder_button = st.button("🛠️ Builder", use_container_width=True, key="agent_builder_button",
                                           help="Build new agents", type="primary" if builder_active else "secondary")
        command_active = st.session_state.selected_tab == "Command Center"
        command_center_button = st.button("🎮 Command", use_container_width=True, key="command_center_button",
                                         help="Command center", type="primary" if command_active else "secondary")
        st.markdown("---")
        # Observability section
        st.markdown("<div class='sidebar-subheader'>Observability</div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:    
            obs_active = st.session_state.selected_tab == "Observability"
            observability_button = st.button("📈 Metrics", use_container_width=True, key="observability_button",
                                            help="View metrics", type="primary" if obs_active else "secondary")
        with col2:
            lang_active = st.session_state.selected_tab == "Langfuse"
            langfuse_button = st.button("🔍 Traces", use_container_width=True, key="langfuse_button",
                                       help="View traces", type="primary" if lang_active else "secondary")
        st.markdown("---")
        
        # Update selected tab based on button clicks
        if chat_button:
            st.session_state.selected_tab = "Chat"
            st.rerun()
        elif env_button:
            st.session_state.selected_tab = "Environment"
            st.rerun()
        elif docs_button:
            st.session_state.selected_tab = "Documentation"
            st.rerun()
        elif service_button:
            st.session_state.selected_tab = "Agent Service"
            st.rerun()
        elif agent_builder_button:
            st.session_state.selected_tab = "Agent Builder"
            st.rerun()
        # Removed agent_insights_button tab switching logic
        # elif agent_insights_button:
        #     st.session_state.selected_tab = "Agent Insights"
        #     st.rerun()
        elif command_center_button:
            st.session_state.selected_tab = "Command Center"
            st.rerun()
        elif observability_button:
            st.session_state.selected_tab = "Observability"
            st.rerun()
        elif langfuse_button:
            st.session_state.selected_tab = "Langfuse"
            st.rerun()


    
    # Function to load a tab with error handling
    def load_tab_safely(title, tab_function, *args, **kwargs):
        st.title(title)
        try:
            if asyncio.iscoroutinefunction(tab_function):
                return asyncio.create_task(tab_function(*args, **kwargs))
            else:
                return tab_function(*args, **kwargs)
        except Exception as e:
            st.error(f"Error loading {title}: {str(e)}")
            st.write("Details:", e)
            import traceback
            st.code(traceback.format_exc(), language="python")
            return None
    
    # Display the selected tab with error handling
    if st.session_state.selected_tab == "Chat":
        chat_task = load_tab_safely("Darchon - 🤖 Gets S**t Done", chat_tab)
        if chat_task:
            await chat_task
    elif st.session_state.selected_tab == "Environment":
        load_tab_safely("Darchon - ⚙️ Environment Configuration", environment_tab)
    elif st.session_state.selected_tab == "Documentation":
        load_tab_safely("Darchon - 📚 Documentation", documentation_tab, db_client)
    elif st.session_state.selected_tab == "Agent Service":
        load_tab_safely("Darchon - 🛠️ Agent Service", agent_service_tab)
    elif st.session_state.selected_tab == "Agent Builder":
        load_tab_safely("Darchon - 🏗️ Agent Builder", agent_builder_tab)
    elif st.session_state.selected_tab == "Agent Insights":
        load_tab_safely("Darchon - 📊 Agent Insights", agent_insights_tab)
    elif st.session_state.selected_tab == "Command Center":
        load_tab_safely("Darchon - 🎮 Command Center", command_center_tab)
    elif st.session_state.selected_tab == "Observability":
        load_tab_safely("Darchon - 👁️ Integrated Observability", integrated_observability_tab)
    elif st.session_state.selected_tab == "Langfuse":
        load_tab_safely("Darchon - 🔍 Langfuse Dashboard", langfuse_dashboard_tab)

if __name__ == "__main__":
    # Create a new event loop and run the main async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
