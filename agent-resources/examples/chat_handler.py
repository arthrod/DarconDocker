import json
import os
import requests
import streamlit as st
from utils import store_memory, store_agent_response

def process_chat_message(prompt, user_id):
    # Ensure configuration exists
    if "tool_configs" not in st.session_state or \
       st.session_state["selected_tool"] not in st.session_state["tool_configs"]:
        st.error("Please configure your AI model settings in the sidebar first.")
        return ""
    
    # Get the tool configuration (including AI model and database settings)
    config = st.session_state["tool_configs"][st.session_state["selected_tool"]]
    provider = config.get("ai_model")
    selected_model = config.get("selected_model")  # may be used by some providers
    db_config = config.get("db_config", {"type": "none"})
    
    # Append the user's prompt to the chat history (simple list)
    st.session_state.setdefault("chat_messages", [])
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    
    final_response = ""
    
    # Process the call based on the chosen AI model
    if provider == "RAG":
        # When using RAG, check the variant from the sidebar
        rag_variant = config.get("rag_variant", "Pydantic AI")
        final_response = f"{rag_variant} response for: {prompt}"
    
    elif provider == "API Providers":
        # For API Providers, simulate a response (or plug in your API logic)
        final_response = f"API Providers response for: {prompt}"
    
    elif provider == "Openrouter":
        openrouter_api_key = config.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY", "")
        if not openrouter_api_key:
            st.error("Please configure your OpenRouter API key in the sidebar.")
            return ""
        headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": selected_model,
                "messages": st.session_state.chat_messages,
                "stream": False,
            },
        )
        if response.status_code != 200:
            st.error(f"Openrouter API error: {response.status_code}")
            return ""
        data = response.json()
        final_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    elif provider == "Ollama (Local)":
        ollama_base_url = st.session_state.get("ollama_base_url")
        selected_model = st.session_state.get("selected_tool_model")
        if not ollama_base_url or not selected_model:
            st.error("Please configure your Ollama settings in the sidebar.")
            return ""
        response = requests.post(
            f"{ollama_base_url}/api/generate",
            json={"model": selected_model, "prompt": prompt, "stream": False},
        )
        if response.status_code != 200:
            st.error(f"Ollama API error: {response.status_code}")
            return ""
        final_response = response.json().get("response", "")
    
    elif provider == "Chain of Thought MOE":
        final_response = f"Chain of Thought MOE response for: {prompt}"
    
    else:
        final_response = f"{provider} response for: {prompt}"
    
    # Append the assistant response to the chat history
    st.session_state.chat_messages.append({"role": "assistant", "content": final_response})
    st.markdown(final_response)
    
    # Save the conversation in the chosen database if saving is enabled
    if db_config.get("type") != "none":
        store_memory(user_id, prompt)
        store_agent_response(user_id, final_response)
    
    return final_response
