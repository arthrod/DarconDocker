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
from utils import *

def main():
    st.markdown(
    "<h1 style='text-align: center; margin: 1.5rem 0;'>⚡ Bolt Chat</h1>",
        unsafe_allow_html=True,
    )
    st.write("")

    # Create two columns with equal width
    col1, col2 = st.columns([4, 4])

    # (External process for Bolt.diy is launched on app startup.)

    st.markdown(
        """
        <style>
        /* Container layout */
        .block-container {
            padding: 1rem 2rem !important;
            max-width: 100% !important;
        }
        /* Chat box container */
        .stColumn > div {
            background: rgba(17, 23, 33, 0.7) !important;
            border: 1px solid rgba(250, 250, 250, 0.1) !important;
            border-radius: 8px !important;
            padding: 1rem !important;
            height: calc(100vh - 200px) !important;
            max-width: 100% !important;
            overflow-y: auto !important;
        }
        /* Messages container */
        [data-testid="stChatMessageContainer"] {
            max-width: 100% !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
            word-wrap: break-word !important;
        }
        /* Chat messages */
        .stChatMessage {
            max-width: 100% !important;
            word-wrap: break-word !important;
        }
        /* Chat input */
        .stChatInputContainer {
            position: relative !important;
            margin-top: auto !important;
            background: rgba(30, 37, 48, 0.7) !important;
            border: 1px solid rgba(250, 250, 250, 0.1) !important;
            border-radius: 4px !important;
            padding: 0.5rem !important;
        }
        /* Scrollbar */
        .stColumn > div::-webkit-scrollbar {
            width: 6px;
            background: transparent;
        }
        .stColumn > div::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }
        </style>
        <script>
            function scrollToBottom() {
                const containers = document.querySelectorAll('.stColumn > div');
                containers.forEach(container => {
                    const chatInput = container.querySelector('.stChatInputContainer');
                    if (chatInput) {
                        chatInput.scrollIntoView({ block: 'end', inline: 'nearest' });
                    }
                });
            }
            const observer = new MutationObserver(scrollToBottom);
            observer.observe(document.body, { childList: true, subtree: true });
            scrollToBottom();
        </script>
    """,
        unsafe_allow_html=True,
    )

    # Bolt Chat Column
    with col1:
        st.markdown(
            "<h3 style='text-align: center; margin-bottom: 1.5rem;'>⚡ Bolt Chat</h3>",
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown(
            "<h5 style='text-align: center; margin-bottom: 1.0rem;'>Chat directly with ⚡ bolt.diy to create files, modify code, or dev assistance.</h5>",
            unsafe_allow_html=True,
        )

        if "bolt_messages" not in st.session_state:
            st.session_state.bolt_messages = []
        if "expert_messages" not in st.session_state:
            st.session_state.expert_messages = []

        with st.sidebar.expander("⚡ Bolt Providers", expanded=True):
            try:
                models_response = requests.get("http://localhost:5174/api/models")
                models_data = models_response.json()
                selected_provider = st.selectbox(
                    "Provider", [p["name"] for p in models_data["providers"]], index=0
                )
                available_models = [
                    m["name"]
                    for m in models_data["modelList"]
                    if m["provider"] == selected_provider
                ]
                selected_model = st.selectbox("Model", available_models, index=0)
            except Exception as e:
                st.error("Could not connect to Bolt API. Make sure Bolt is running.")
                selected_model = None

        with st.container():
            chat_container = st.container()
            prompt = st.chat_input("Message ⚡ Bolt...", key="bolt_input")
            with chat_container:
                for message in st.session_state.bolt_messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                if prompt:
                    if not selected_model:
                        st.error("Please select a model first.")
                    else:
                        st.session_state.bolt_messages.append(
                            {"role": "user", "content": prompt}
                        )
                        with st.chat_message("user"):
                            st.markdown(prompt)
                        try:
                            response = requests.post(
                                "http://localhost:5174/api/llmcall",
                                headers={
                                    "Content-Type": "application/json",
                                    "Authorization": (
                                        f"Bearer {openrouter_api_key}"
                                        if openrouter_api_key
                                        else ""
                                    ),
                                },
                                json={
                                    "message": prompt,
                                    "model": selected_model,
                                    "provider": {"name": selected_provider},
                                    "streamOutput": True,
                                },
                                stream=True,
                            )
                            with st.chat_message("assistant"):
                                message_placeholder = st.empty()
                                full_response = ""
                                for chunk in response.iter_content(chunk_size=1024):
                                    if chunk:
                                        text = chunk.decode()
                                        full_response += text
                                        message_placeholder.markdown(full_response + "▌")
                                message_placeholder.markdown(full_response)
                                st.session_state.bolt_messages.append(
                                    {"role": "assistant", "content": full_response}
                                )
                                try:
                                    vscode_response = requests.post(
                                        "http://localhost:5000/chat",
                                        json={"message": full_response},
                                    )
                                    if vscode_response.ok:
                                        st.success("Response saved to VSCode workspace 🏆")
                                    else:
                                        st.warning(
                                            "Could not save response to VSCode workspace 🚧"
                                        )
                                except Exception as e:
                                    st.warning(f"VSCode integration error: {str(e)}")
                        except Exception as e:
                            st.error(f"Error communicating with Bolt: {str(e)}")

    # Bolt Preview Column
    with col2:
        st.markdown(
            "<h3 style='text-align: center; margin-bottom: 1.5rem;'>⚡ Bolt Preview</h3>",
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown(
            "<h5 style='text-align: center; margin-bottom: 1.0rem;'>Preview your ⚡ bolt.diy app development.</h5>",
            unsafe_allow_html=True,
        )

if __name__ == "__main__":
    main()


