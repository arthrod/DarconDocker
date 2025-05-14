import streamlit as st
import requests
import threading
import os
from dotenv import load_dotenv
from utils import fetch_openrouter_models
from huggingface_hub import snapshot_download  # For downloading Huggingface models
import zipfile
import io
import psycopg2
import graphviz  # For the visual builder

# Load environment variables (if not already loaded)
load_dotenv("./.env")

# ------------------------------------------------------------
# New helper functions for the RAG Builder section
# ------------------------------------------------------------

def render_chat_interface(agent_type: str):
    st.subheader(f"{agent_type} Chat Assistant")

    # Initialize session state for chat history if it doesn't exist.
    chat_key = f"chat_history_{agent_type}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    # Display the existing chat history.
    for msg in st.session_state[chat_key]:
        st.markdown(msg)

    # Input box for user message.
    message = st.text_input("Enter your message:", key=f"input_{agent_type}")
    if st.button("Send", key=f"send_{agent_type}") and message:
        # Append user message.
        st.session_state[chat_key].append(f"**You:** {message}")
        # Simulate an expert response.
        expert_response = f"**Expert:** I received '{message}'. (This is a simulated response.)"
        st.session_state[chat_key].append(expert_response)
        # Rerun to update the interface.
        st.rerun()

def render_visual_builder(agent_type: str):
    st.subheader("Visual Builder")
    st.write("Below is a placeholder for the agent configuration visual flow:")

    # Create a simple Graphviz flowchart.
    dot = graphviz.Digraph(comment=f"{agent_type} Configuration")
    dot.node("A", "Start")
    dot.node("B", "Configure")
    dot.node("C", "Validate")
    dot.node("D", "Deploy")
    dot.edges(["AB", "BC", "CD"])
    
    # Render the graph.
    st.graphviz_chart(dot)

# ------------------------------------------------------------
# Main application code (existing branches preserved)
# ------------------------------------------------------------
def main():
    st.title("⚙️ AI Model Settings")
    
    # Add Save Configuration button at the top
    save_col1, save_col2 = st.columns([3,1])
    with save_col2:
        if st.button("💾 Save Config"):
            # Store all current selections in session state
            if "tool_configs" not in st.session_state:
                st.session_state["tool_configs"] = {}
            
            # Save default configurations for all tools
            for tool in ["🤖 Chat", "🕷️ Crawl4AI"]:
                if tool not in st.session_state["tool_configs"]:
                    st.session_state["tool_configs"][tool] = {}
                current_config = {
                    "ai_model": st.session_state.get("chat_model_provider"),
                    "selected_model": None  # Will be updated below
                }
                # Set the selected model based on provider
                if current_config["ai_model"] == "Openrouter":
                    current_config["selected_model"] = st.session_state.get("chat_selected_reasoning_model")
                    current_config["openrouter_api_key"] = st.session_state.get("openrouter_api_key", "")
                elif current_config["ai_model"] == "Ollama (Local)":
                    current_config["selected_model"] = st.session_state.get("selected_model")
                # ...other providers as needed...
                st.session_state["tool_configs"][tool].update(current_config)
            # Save defaults to dashboard_config.json so chat_handler always has a fallback
            default_config = st.session_state["tool_configs"]
            try:
                with open("dashboard_config.json", "w") as f:
                    import json
                    json.dump(default_config, f, indent=4)
            except Exception as e:
                st.error(f"Error saving config file: {e}")
            st.success("Configuration saved!")
    
    # Ensure the openrouter API key is set; load from .env if not provided by user.
    if not st.session_state.get("openrouter_api_key"):
        st.session_state["openrouter_api_key"] = os.getenv("OPENROUTER_API_KEY", "")
    
    # Sorted list for radio options (model providers)
    provider_options = sorted([
        "Cloud Providers", 
        "Openrouter", 
        "Ollama (Local)", 
        "Huggingface", 
        "Chain of Thought MOE",
        "RAG Builder"
    ])
    model_provider = st.radio("Select Model Provider:", provider_options, key="chat_model_provider")
    st.markdown("---")
    
    # ---------------------
    # API Providers Branch
    if model_provider == "Cloud Providers":
        st.markdown("### API Providers Settings")
        try:
            models_response = requests.get("http://localhost:5174/api/models")
            models_data = models_response.json()
            # Get and sort the provider names
            provider_list = sorted([p["name"] for p in models_data["providers"]])
            selected_provider = st.selectbox("Provider", provider_list, index=0)
            # Filter and sort the models for the selected provider
            available_models = sorted(
                [m["name"] for m in models_data["modelList"] if m["provider"] == selected_provider]
            )
            selected_model = st.selectbox("Model", available_models, index=0)
            st.write(f"Selected Model: **{selected_model}**")
        except Exception as e:
            st.error("Could not connect to Bolt API. Make sure Bolt is running.")
    
    # ---------------------
    # Openrouter Branch
    elif model_provider == "Openrouter":
        st.markdown("### OpenRouter AI Models")
        default_api_key = os.getenv("OPENROUTER_API_KEY", "")
        openrouter_api_key = st.text_input(
            "OpenRouter API Key", 
            value=default_api_key,
            type="password"
        )
        st.session_state["openrouter_api_key"] = openrouter_api_key
        
        models_data = fetch_openrouter_models()
        reasoning_options = sorted(
            [model["id"] for model in models_data.get("data", [])]
        ) if models_data else ["No models available"]
        
        # Get previously selected model or default to first option
        default_model_index = 0
        if "chat_selected_reasoning_model" in st.session_state:
            try:
                default_model_index = reasoning_options.index(st.session_state["chat_selected_reasoning_model"])
            except ValueError:
                pass
        
        selected_model = st.selectbox(
            "Choose Model:", 
            reasoning_options, 
            index=default_model_index,
            key="chat_selected_reasoning_model"
        )
        
        # Store selections immediately along with provider name
        if "tool_configs" not in st.session_state:
            st.session_state["tool_configs"] = {}
        for tool in ["🤖 Chat", "🕷️ Crawl4AI"]:
            if tool not in st.session_state["tool_configs"]:
                st.session_state["tool_configs"][tool] = {}
            st.session_state["tool_configs"][tool].update({
                "ai_model": model_provider,
                "openrouter_api_key": openrouter_api_key,
                "selected_model": selected_model
            })
    
    # ---------------------
    # Ollama (Local) Branch
    elif model_provider == "Ollama (Local)":
        st.markdown("### Local Models (Ollama)")
        ollama_base_url_global = st.text_input("🐑 Ollama Base URL", "http://10.147.20.20:11434")
        st.session_state.ollama_base_url = ollama_base_url_global
        pull_input_cols = st.columns([3, 1])
        with pull_input_cols[0]:
            new_model_global = st.text_input("🔄 Pull New Model", placeholder="e.g., llama2, codellama, mistral")
        with pull_input_cols[1]:
            pull_button_global = st.button("Pull", key="pull_model")
        if pull_button_global and new_model_global:
            st.session_state.pull_done = False
            st.session_state.pull_status = f"Starting model pull for '{new_model_global}'. Please wait..."
            pull_status = st.empty()
            pull_status.info(st.session_state.pull_status)
            def pull_model_global(new_model, base_url):
                try:
                    response = requests.post(
                        f"{base_url}/api/pull",
                        json={"name": new_model},
                        timeout=60,
                        stream=False
                    )
                    if response.status_code == 200:
                        st.session_state.pull_status = f"Model '{new_model}' pulled successfully!"
                    else:
                        st.session_state.pull_status = f"Model pull failed with status code: {response.status_code}"
                except Exception as e:
                    st.session_state.pull_status = f"An error occurred while pulling the model: {str(e)}"
                st.session_state.pull_done = True
            threading.Thread(
                target=pull_model_global, 
                args=(new_model_global, ollama_base_url_global), 
                daemon=True
            ).start()
        if "pull_status" in st.session_state:
            st.info(st.session_state.pull_status)
        try:
            model_options = []  # Initialize model_options
            if ollama_base_url_global:
                response = requests.get(f"{ollama_base_url_global}/api/tags", timeout=30)
                if response.status_code == 200:
                    ollama_models = response.json().get("models", [])
                    # Sort the available model names alphabetically
                    model_options = sorted([model["name"] for model in ollama_models])
                    with st.container():
                        st.markdown("### 📊 Model Details")
                        if ollama_models:
                            for model in ollama_models:
                                st.markdown(f"""
                                    **{model['name']}**
                                    - Size: {model.get('size', 'N/A')}
                                    - Modified: {model.get('modified', 'N/A')}
                                    - Digest: `{model.get('digest', 'N/A')[:10]}`
                                """)
                        else:
                            st.warning("No models found. Try pulling a model first.")
                else:
                    st.error(f"Failed to fetch model details. Status: {response.status_code}")
        except Exception as e:
            st.error(f"Failed to connect to Ollama: {e}")
        if not model_options:
            model_options = ["No models available"]
        selected_model = st.selectbox("Choose a model:", model_options, key="selected_model", on_change=lambda: st.session_state.update({"config_reloaded": True}))
        # Store the selected model for the chat handler as the tool model.
        st.session_state["selected_tool_model"] = selected_model
    
    # ---------------------
    # Huggingface Branch
    elif model_provider == "Huggingface":
        st.markdown("### Huggingface Models")
        # Use the API key from .env by default, unless the user provides a new one.
        default_hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        user_input_api_key = st.text_input(
            "Huggingface API Key", 
            default_hf_api_key,
            help="Enter your Huggingface API key (this will be used temporarily)."
        )
        hf_api_key = user_input_api_key if user_input_api_key else default_hf_api_key

        with st.spinner("Fetching Huggingface models..."):
            try:
                headers = {}
                if hf_api_key:
                    headers["Authorization"] = f"Bearer {hf_api_key}"
                response = requests.get("https://huggingface.co/api/models?limit=200", headers=headers, timeout=30)
                if response.status_code == 200:
                    hf_models = response.json()
                    model_ids = sorted([model.get("id", "Unknown Model") for model in hf_models])
                else:
                    st.error(f"Failed to fetch models. Status code: {response.status_code}")
                    model_ids = []
            except Exception as e:
                st.error(f"Error fetching models: {e}")
                model_ids = []
        if not model_ids:
            model_ids = ["No models available"]
        selected_hf_model = st.selectbox("Choose Huggingface Model:", model_ids, key="selected_hf_model")
        
        storage_option = st.radio(
            "Select storage option for downloaded model:",
            options=["Local Storage", "PostgreSQL Storage"],
            index=0,
            key="storage_option"
        )
        
        if storage_option == "PostgreSQL Storage":
            st.markdown("### PostgreSQL Database Configuration")
            pg_database = st.text_input("PostgreSQL Database", os.getenv("PG_DATABASE", "models"), key="pg_database")
        
        if st.button("Download", key="download_hf_model"):
            if selected_hf_model == "No models available":
                st.warning("No model selected.")
            else:
                with st.spinner(f"Downloading model '{selected_hf_model}'..."):
                    try:
                        download_path = snapshot_download(repo_id=selected_hf_model, token=hf_api_key)
                        st.success(f"Model '{selected_hf_model}' downloaded to {download_path}.")
                        
                        if storage_option == "Local Storage":
                            st.info("Model saved locally (in Downloads folder).")
                        else:
                            st.info("Zipping model files for PostgreSQL storage...")
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                                for root, dirs, files in os.walk(download_path):
                                    for file in files:
                                        file_path = os.path.join(root, file)
                                        arcname = os.path.relpath(file_path, download_path)
                                        zip_file.write(file_path, arcname)
                            zip_buffer.seek(0)
                            
                            st.info("Connecting to PostgreSQL...")
                            try:
                                conn = psycopg2.connect(
                                    database=pg_database
                                )
                                cursor = conn.cursor()
                                cursor.execute("""
                                    CREATE TABLE IF NOT EXISTS huggingface_models (
                                        id SERIAL PRIMARY KEY,
                                        model_name TEXT,
                                        model_zip BYTEA,
                                        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                    )
                                """)
                                conn.commit()
                                cursor.execute(
                                    "INSERT INTO huggingface_models (model_name, model_zip) VALUES (%s, %s)",
                                    (selected_hf_model, psycopg2.Binary(zip_buffer.getvalue()))
                                )
                                conn.commit()
                                cursor.close()
                                conn.close()
                                st.success("Model inserted into PostgreSQL.")
                            except Exception as db_err:
                                st.error(f"Failed to insert model into PostgreSQL: {db_err}")
                    except Exception as e:
                        st.error(f"Failed to download model: {e}")
    
    # ---------------------
    # Chain of Thought MOE Branch
    elif model_provider == "Chain of Thought MOE":
        st.markdown("### Chain of Thought MOE Configuration")
        chain_length = st.number_input("Select chain length (number of steps):", min_value=1, max_value=20, value=3, step=1)
        st.markdown("Configure the chain sequence:")
        
        chain_options = ["Cloud Providers", "Huggingface", "Ollama", "Openrouter", "RAG"]
        chain_elements = []
        for i in range(int(chain_length)):
            chain_choice = st.selectbox(f"Chain step {i+1}", chain_options, key=f"chain_step_{i}")
            chain_elements.append(chain_choice)
        
        chain_display = " 🔗 ".join(chain_elements)
        st.markdown(f"**Your chain:** {chain_display}")
        
        query = st.text_input("Enter your query:", "Explain the chain-of-thought pipeline and its benefits.")
        
        if st.button("Submit"):
            st.markdown("### Processing your chain-of-thought...")
            final_result = process_chain(query, chain_elements)
            st.markdown("### Final Aggregated Response:")
            st.write(final_result)
    
    # ---------------------
    # RAG Builder Branch
    elif model_provider == "RAG Builder":
        st.markdown("### RAG Builder")
        st.write("This tool allows you to build a RAG configuration with multiple parts.")
        
        # Create tabs for multiple agent creators
        tabs = st.tabs([
            "Pydantic AI Agent Creator", 
            "Smolagent Creator (Hugging Face)", 
            "n8n", 
            "Flowise"
        ])
        
        # Tab 1: Pydantic AI Agent Creator
        # Tab 1: Pydantic AI Agent Creator
        with tabs[0]:
            st.subheader("Pydantic AI Agent Creator")
            import ai_agent_builder_tool
            import asyncio
            asyncio.run(ai_agent_builder_tool.main())

        
        # Tab 2: Smolagent Creator (Hugging Face)
        with tabs[1]:
            st.title("⚡️ Huggingface - The Ultimate Smolagent Builder 🤖")
            st.write("🛠️ **Tell me your dream AI agent, and I'll make it real with Huggingface Smolagents!**")
            st.write("💡 **Example**: *Build me an AI agent that can search the web using the Brave API.*")
            st.markdown("---")
            st.write("✨ **Unleash the power of AI. Start building now!**")
            smolagent_config = st.text_area("Smolagent Code", height=150, key="smolagent_config_rag")
            if smolagent_config:
                st.write("**Configuration Preview:**")
                st.code(smolagent_config, language="yaml")
            render_chat_interface("Smolagent_RAG")
            render_visual_builder("Smolagent_RAG")
        
        # Tab 3: n8n
        with tabs[2]:
            st.title("⚡️ N8N - The Ultimate n8n workflow Builder 🤖")
            st.write("Paste your n8n configuration details below and interact with the expert.")
            st.write("💡 **Example**: *Build me an AI agent that can search the web using the Brave API.*")
            st.markdown("---")
            st.write("✨ **Unleash the power of AI. Start building now!**")
            n8n_config = st.text_area("n8n json workflow", height=150, key="n8n_config_rag")
            if n8n_config:
                st.write("**Configuration Preview:**")
                st.code(n8n_config, language="json")
            render_chat_interface("n8n_RAG")
            render_visual_builder("n8n_RAG")
        
        # Tab 4: Flowise
        with tabs[3]:
            st.title("⚡️ Flowise - The Ultimate Flowise Agent Builder 🤖")
            st.write("Paste your Flowise json configuration details below and interact with the expert.")
            st.write("💡 **Example**: *Build me an AI agent that can search the web using the Brave API.*")
            st.markdown("---")
            st.write("✨ **Unleash the power of AI. Start building now!**")
            flowise_config = st.text_area("Flowise json code", height=150, key="flowise_config_rag")
            if flowise_config:
                st.write("**Configuration Preview:**")
                st.code(flowise_config, language="json")
            render_chat_interface("Flowise_RAG")
            render_visual_builder("Flowise_RAG")
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


