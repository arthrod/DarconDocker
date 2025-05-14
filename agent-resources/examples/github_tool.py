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
    st.title("🚀 Github x 📦 Supabase")
    repo_url = st.text_input("🌍 Enter GitHub Repository URL:")
    if st.button("🔄 Clone and 📥 Process Repository"):
        if repo_url:
            st.info("🔄 Cloning repository...")
            repo_path = clone_repo(repo_url)
            repo_name = repo_url.split("/")[-1]
        repo_owner = repo_url.split("/")[-2]
        branch = "main"
        commit_hash = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path)
            .strip()
            .decode()
        )
        for file in repo_path.rglob("*"):
            if file.is_file():
                file_size = file.stat().st_size
                file_type = file.suffix[1:].lower()
                if file_type in {
                    "png",
                    "jpg",
                    "jpeg",
                    "gif",
                    "ico",
                    "svg",
                    "pack",
                    "idx",
                }:
                    continue
                if file_size > 5_000_000:
                    continue
                with open(file, "r", encoding="utf-8", errors="ignore") as f:
                    file_content = f.read()
                embeddings = generate_embedding(file_content)
                if embeddings:
                    upload_to_supabase(
                        repo_name,
                        repo_owner,
                        branch,
                        commit_hash,
                        str(file.relative_to(repo_path)),
                        file_type,
                        file_size,
                        file_content,
                        embeddings,
                    )
        st.success("Repository cloned and processed successfully! 🏆")
    else:
        st.error("Please enter a valid GitHub repository URL.")
st.subheader("🤖 Chat with AI about Your GitHub Repository")
if "github_chat_messages" not in st.session_state:
    st.session_state.github_chat_messages = []
for message in st.session_state.github_chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
if prompt := st.chat_input("Message...", key="github_chat_input"):
    if (
        not hasattr(st.session_state, "last_github_processed_message")
        or st.session_state.last_github_processed_message != prompt
    ):
        st.session_state.last_github_processed_message = prompt
        st.session_state.github_chat_messages.append(
            {"role": "user", "content": prompt}
        )
        with st.chat_message("user"):
            st.markdown(prompt)
    if not st.session_state.get("selected_model"):
        st.error("Please select a model first.")
    else:
        try:
            if st.session_state.use_cloud_model:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://openrouter.ai/",
                        "X-Title": "Echo-Ai/M.E.O",
                    },
                    json={
                        "model": st.session_state.selected_model,
                        "messages": st.session_state.github_chat_messages,
                    },
                )
                if response.status_code == 200:
                    assistant_response = response.json()["choices"][0]["message"][
                        "content"
                    ]
                    if (
                        st.session_state.get("last_github_assistant_response")
                        != assistant_response
                    ):
                        st.session_state.last_github_assistant_response = (
                            assistant_response
                        )
                        with st.chat_message("assistant"):
                            st.markdown(assistant_response)
                        st.session_state.github_chat_messages.append(
                            {"role": "assistant", "content": assistant_response}
                        )
                else:
                    st.error(
                        f"Failed to get a response from OpenRouter. Status code: {response.status_code}"
                    )
            else:
                ollama_base_url = st.session_state.get("ollama_base_url")
                if not ollama_base_url:
                    st.error("Please enter Ollama Base URL.")
                else:
                    response = requests.post(
                        f"{ollama_base_url}/api/chat",
                        json={
                            "model": st.session_state.selected_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "stream": False,
                            "options": {"temperature": 0.7, "top_p": 0.9},
                        },
                    )
                    if response.status_code == 200:
                        response_data = response.json()
                        assistant_response = response_data.get("message", {}).get(
                            "content", ""
                        )
                        if assistant_response:
                            with st.chat_message("assistant"):
                                st.markdown(assistant_response)
                            if not any(
                                msg["content"] == assistant_response
                                for msg in st.session_state.github_chat_messages[-3:]
                                if msg["role"] == "assistant"
                            ):
                                st.session_state.github_chat_messages.append(
                                    {"role": "assistant", "content": assistant_response}
                                )
                        else:
                            st.error("Empty response from Ollama")
                    else:
                        st.error(
                            f"Failed to get response from Ollama. Status: {response.status_code}"
                        )
        except requests.exceptions.RequestException as e:
            st.error(f"Network error: {str(e)}")
        except ValueError as e:
            st.error(f"Failed to parse response: {str(e)}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    main()
