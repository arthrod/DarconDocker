from __future__ import annotations as _annotations

import os
import json
import time
import threading
import logging
import subprocess
import tempfile
import asyncio
import psutil
import requests
import streamlit as st
import pandas as pd
import pdfplumber
import tiktoken
import openai
import logfire
import nest_asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv, dotenv_values, set_key
from pathlib import Path
from supabase import create_client, Client
from xml.etree import ElementTree
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal, TypedDict
from dataclasses import dataclass, field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from contextlib import asynccontextmanager
import httpx
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel
from functools import wraps
import shutil
import atexit
import streamlit.components.v1 as components
from utils import fetch_openrouter_models, fetch_ollama_models  # or other functions from utils

# NEW: Import psycopg2 for Postgres support
import psycopg2

# ------------------ Landing Page ------------------
import streamlit as st

# Ensure session state variable exists
if "entered_app" not in st.session_state:
    st.session_state["entered_app"] = False

# Show landing page if user hasn't entered the app
if not st.session_state["entered_app"]:
    st.set_page_config(page_title="Echo AI", layout="centered")

    # Custom styling
    st.markdown(
        """
        <style>
        .main {
            text-align: center;
        }
        .title {
            font-size: 36px;
            font-weight: bold;
            color: #4CAF50;
        }
        .subtitle {
            font-size: 18px;
            color: #777;
        }
        .button {
            background-color: #4CAF50;
            color: white;
            font-size: 18px;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
        }
        .button:hover {
            background-color: #45a049;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Centered layout
    st.markdown('<div class="main">', unsafe_allow_html=True)
    st.image("Designer.jpeg", use_container_width=True)  # Updated parameter
    st.markdown('<p class="title">Welcome to Echo AI</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitle">Your all-in-one AI tool platform for building and configuring your favourite Ai related services.</p>',
        unsafe_allow_html=True,
    )

    # Custom-styled button
    if st.button("Enter", key="enter_button"):
        st.session_state["entered_app"] = True
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# ------------------ End Landing Page ------------------

# ----- Dashboard Config Functions -----
CONFIG_FILE = "dashboard_config.json"

def load_dashboard_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Failed to load config: {e}")
    return {
        "ai_model": "RAG",
        "database": "Supabase",
        "configured": False
    }

def save_dashboard_config(config: Dict[str, Any]):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        st.error(f"Failed to save config: {e}")

def update_config():
    config = load_dashboard_config()
    config["ai_model"] = st.session_state.get("ai_model_choice", "RAG")
    config["database"] = st.session_state.get("database_choice", "Supabase")
    save_dashboard_config(config)
    st.session_state["has_interacted"] = True

# Load the saved configuration on startup
saved_config = load_dashboard_config()

# List of tools that support chat history and settings
allowed_tools_for_history = [
    "🤖 Chat",
    "🕷️ Crawl4AI",
    "🗃️ Local file Uploader",
    "📥 Clone GitHub Repo",
    "🔄 n8n → Pydantic-AI",
    "🛠️ Ai Agent Builder 🤖"
]

# Initialize chat history in session state if not already there
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []  # Changed from dict to list

#############################################
# (No changes made to the chat tool UI below)
#############################################

# ------------------ Sidebar Layout ------------------
st.sidebar.info("Streamlit App enhanced with all your favourite  A.I Tools.")
st.sidebar.markdown("---")
st.sidebar.title("🧭 Navigation")

# New Chat Button at the top of the navigation
if st.session_state.get("selected_tool", "🤖 Chat") in [
    "🤖 Chat",
    "🕷️ Crawl4AI",
    "🗃️ Local file Uploader",
    "📥 Clone GitHub Repo",
    "🔄 n8n → Pydantic-AI",
    "🛠️ Ai Agent Builder 🤖"
]:
    if st.sidebar.button("✨ New Chat", key="sidebar_new_chat_button_top"):
        if "messages" in st.session_state and st.session_state["messages"]:
            st.session_state["messages"] = []
        st.rerun()

tool_options = [
    "🤖 Chat",
    "🕷️ Crawl4AI",
    "🎓 GPT Researcher",
    "🗃️ Local file Uploader",
    "⚡ Bolt.diy",
    "📥 Clone GitHub Repo",
    "🔄 n8n → Pydantic-AI",
    "👁️ Onlook",
    "🖥️ Theia IDE",
    "🖼️ Image Generation",
    "🌐 Browser UI",
    "📊 Dashboard & Config"
]
if "selected_tool" not in st.session_state:
    st.session_state["selected_tool"] = tool_options[0]

selected_tool = st.sidebar.radio(
    "🛠️ Choose a Tool:", 
    tool_options, 
    index=tool_options.index(st.session_state["selected_tool"]),
    key="selected_tool"
)

# -----------------------------------------------------------------
# Tool-Specific Configuration Setup
if "tool_configs" not in st.session_state:
    st.session_state["tool_configs"] = {}

if selected_tool not in st.session_state["tool_configs"]:
    if selected_tool in allowed_tools_for_history:
        st.session_state["tool_configs"][selected_tool] = {
            "ai_model": saved_config.get("ai_model", "RAG"),
            "database": saved_config.get("database", "Supabase")
        }
    else:
        st.session_state["tool_configs"][selected_tool] = {}

# -----------------------------------------------------------------
# View Toggle for Navigation/History
if selected_tool in allowed_tools_for_history:
    view_mode = st.sidebar.radio("View", ["Navigation", "History"], index=0, key="view_mode")
else:
    view_mode = "Navigation"

if view_mode == "Navigation":
    if selected_tool in allowed_tools_for_history:
        config = st.session_state["tool_configs"][selected_tool]
        
        st.sidebar.markdown("## AI Model")
        ai_model_options = [
            "RAG",
            "API Providers",
            "Openrouter",
            "Ollama (Local)",
            "Chain of Thought MOE"
        ]
        default_ai_model = config.get("ai_model", saved_config.get("ai_model", "RAG"))
        default_ai_index = ai_model_options.index(default_ai_model) if default_ai_model in ai_model_options else 0
        
        ai_model_choice = st.sidebar.radio(
            "Choose AI Model:",
            ai_model_options,
            index=default_ai_index,
            key=f"ai_model_choice_{selected_tool}"
        )
        st.session_state["tool_configs"][selected_tool]["ai_model"] = ai_model_choice
        
        if ai_model_choice == "RAG":
            rag_options = [
                "Pydantic AI", 
                "Smolagent", 
                "n8n", 
                "Flowise"
            ]
            selected_rag_variant = st.sidebar.radio(
                "Choose RAG Agent:",
                rag_options,
                key=f"rag_variant_{selected_tool}"
            )
            st.session_state["tool_configs"][selected_tool]["rag_variant"] = selected_rag_variant
        
        st.sidebar.markdown("## Database")
        database_options = [
            "Supabase",
            "Postgres (Local)",
            "Do not save"
        ]
        default_database = config.get("database", saved_config.get("database", "Supabase"))
        if default_database not in database_options:
            default_database = "Supabase"
        default_db_index = database_options.index(default_database)
        
        database_choice = st.sidebar.radio(
            "Choose Database:",
            database_options,
            index=default_db_index,
            key=f"database_choice_{selected_tool}"
        )
        st.session_state["tool_configs"][selected_tool]["database"] = database_choice
        
        # Configure db_config based on the user's selection.
        if database_choice == "Supabase":
            supabase_api_key = os.getenv("SUPABASE_API_KEY", "")
            supabase_url = os.getenv("SUPABASE_URL", "")
            st.session_state["tool_configs"][selected_tool]["db_config"] = {
                "type": "supabase",
                "api_key": supabase_api_key,
                "url": supabase_url
            }
        elif database_choice == "Postgres (Local)":
            st.session_state["tool_configs"][selected_tool]["db_config"] = {
                "type": "postgres",
                "host": os.getenv("POSTGRES_HOST", "10.147.20.2"),
                "port": os.getenv("POSTGRES_PORT", "5432"),
                "dbname": os.getenv("POSTGRES_DB", "postgres"),
                "user": os.getenv("POSTGRES_USER", ""),
                "password": os.getenv("POSTGRES_PASSWORD", "")
            }
        else:
            st.session_state["tool_configs"][selected_tool]["db_config"] = {
                "type": "none"
            }
else:
    st.sidebar.markdown("### Chat History")
    if "chat_history" in st.session_state and st.session_state["chat_history"]:
        for i, chat in enumerate(st.session_state["chat_history"]):
            with st.sidebar.expander(f"📝 {chat['topic']} - {chat['timestamp']}"):
                for msg in chat['messages']:
                    st.markdown(f"**{msg['role']}**: {msg['content']}")
                if st.button("Continue this chat", key=f"load_chat_{i}"):
                    st.session_state["selected_chat"] = i
                    st.rerun()
    else:
        st.sidebar.write("No chat history available.")

# ------------------ Main Area: Tool Modules Selection ------------------
if selected_tool == "🤖 Chat":
    import chat_tool
    chat_tool.main()
elif selected_tool == "🕷️ Crawl4AI":
    import crawl4ai_tool
    crawl4ai_tool.main()
elif selected_tool == "🗃️ Local file Uploader":
    import local_files_upload
    local_files_upload.main()
elif selected_tool == "📥 Clone GitHub Repo":
    import github_tool
    github_tool.main()
elif selected_tool == "⚡ Bolt.diy":
    import bolt_diy_tool
    bolt_diy_tool.main()
elif selected_tool == "🖼️ Image Generation":
    import image_generation_tool
    image_generation_tool.main()
elif selected_tool == "🌐 Browser UI":
    import browser_use_tool
    browser_use_tool.main()
elif selected_tool == "🔄 n8n → Pydantic-AI":
    import n8n_tool
    asyncio.run(n8n_tool.main())
elif selected_tool == "📊 Dashboard & Config":
    import dashboard_tool
    dashboard_tool.main()
elif selected_tool == "🖥️ Theia IDE":
    import theia_tool
    theia_tool.main()
elif selected_tool == "👁️ Onlook":
    import onlook_tool
    onlook_tool.main()
elif selected_tool == "🎓 GPT Researcher":
    import researcher_tool
    researcher_tool.main()
