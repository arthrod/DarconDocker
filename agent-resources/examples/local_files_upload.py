from __future__ import annotations

import os
import json
import time
import asyncio
import requests
import streamlit as st
import shutil
from dotenv import load_dotenv
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from utils import (
    save_uploaded_file,
    remove_file,
    load_and_process_pdfs,
    create_vector_store,
    is_noteworthy,
    store_memory,
    get_memory_context,
    get_agent_responses_context,
    store_agent_response,
    log_memory,
)
from rag_agent import RAGAgent
from chat_handler import process_chat_message  # Centralized chat handler

# Load environment variables
load_dotenv()

# Create RAG uploads directory if it doesn't exist
RAG_UPLOADS = "RAG_uploads"
os.makedirs(RAG_UPLOADS, exist_ok=True)

# Initialize RAG agent instance
my_agent = RAGAgent()

def main():
    st.title("📂 RAG File Uploader + 🤖 AI Chatbot")

    # --- File Uploader Section ---
    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = []
    
    uploaded_files = st.file_uploader(
        "📨 Upload your documents",
        type=[
            "txt", "csv", "pdf", "sql", "py", "ts", "tsx", "js", "jsx",
            "html", "css", "json", "xml", "yaml", "yml", "md", "r", "java",
            "c", "cpp", "cs", "go", "rb", "swift", "kt", "php", "sh", "bat",
            "pl", "rs", "dart", "scala", "vb", "m", "h", "hpp", "ino"
        ],
        accept_multiple_files=True,
    )
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in st.session_state.uploaded_files:
                save_uploaded_file(uploaded_file)
                st.session_state.uploaded_files.append(uploaded_file.name)

    # --- Display Stored Files ---
    st.subheader("📂 Stored Files")
    stored_files = [
        f for f in os.listdir(RAG_UPLOADS)
        if os.path.isfile(os.path.join(RAG_UPLOADS, f))
    ]
    if stored_files:
        for file in stored_files:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(file)
            with col2:
                if st.button("Remove", key=file):
                    remove_file(file)
    else:
        st.warning("No files stored yet.")

    # --- PDF Ingestion Section ---
    pdf_files = [f for f in stored_files if f.lower().endswith(".pdf")]
    if pdf_files:
        st.subheader("🔄 Ingesting PDF Documents")
        chunks = load_and_process_pdfs(RAG_UPLOADS)
        st.write(f"Created {len(chunks)} chunks from PDFs.")
        vector_store = create_vector_store(chunks, persist_directory="chroma_db")
        st.write("Vector store updated.")

    # --- Chat Section ---
    st.subheader("🤖 Chat with AI about Your Documents")
    
    # Initialize chat history in session state (if not already set)
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("last_processed_message", "")

    # Display chat history
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input box using the centralized chat handler
    if prompt := st.chat_input("Message...", key="crawl4ai_chat_input"):
        final_response = process_chat_message(prompt, user_id="default_user", config={})
        st.write("Final Response:", final_response)

if __name__ == "__main__":
    main()
