from __future__ import annotations as _annotations

import os
import json
import time
import threading
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
    chunk_text,
    get_embedding,
    display_memory_usage,
    log_memory,
    store_chunk,
    is_noteworthy,
    store_memory,
    get_memory_context,
    get_agent_responses_context,
    store_agent_response,
)

from chat_handler import process_chat_message  # Centralized chat handler

# Load environment variables
load_dotenv()



def main():
    st.title("🕷️ Crawl4AI Tool")
    
    # --- Unique User ID for Chat Section ---
    # This ensures that each session gets its own user identifier,
    # preventing chat messages from different sessions from mixing.
    import uuid
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())

    # --- Crawl Configuration Section ---
    url_input = st.text_area(
        "🔍 🌍 Enter URLs (one per line) or a sitemap URL:",
        help="You can enter multiple URLs on separate lines, or a sitemap URL ending with .xml",
    )
    crawl_label = st.text_input(
        "🕷️ Crawl Label (optional):",
        placeholder="e.g., documentation-v1, blog-posts, api-docs",
        help="A label to identify and group this crawl in the database",
    )
    col1, col2 = st.columns([2, 1])
    with col1:
        max_concurrent = st.radio(
            "Choose Max Concurrent Crawls:",
            options=[1, 2, 3, 5, 10, 20],
            index=2,
            help="Select the maximum number of URLs to process simultaneously",
            horizontal=True,
        )
    with col2:
        st.metric(
            "Current Memory Usage",
            f"{log_memory()} MB",
            help="Current RAM usage by the application",
        )

    @dataclass
    class CrawlState:
        total: int = 0
        progress_bar: any = None
        status_text: any = None
        memory_stats: any = None
        details: any = None
        _completed: int = field(default=0)
        _lock: threading.Lock = field(default_factory=threading.Lock)

        @property
        def completed(self) -> int:
            with self._lock:
                return self._completed

        def increment_completed(self) -> None:
            with self._lock:
                self._completed += 1
                progress = self._completed / self.total
                if self.progress_bar:
                    self.progress_bar.progress(progress)
                if self.status_text:
                    self.status_text.text(f"✓ {self._completed}/{self.total} URLs")

    async def process_url(
        url: str,
        state: CrawlState,
        crawler: AsyncWebCrawler,
        semaphore: asyncio.Semaphore,
        crawl_config: CrawlerRunConfig,
    ):
        async with semaphore:
            memory_display = st.empty()
            error_display = st.empty()
            try:
                with state.details:
                    st.write(f"📥 Processing: {url}")
                result = await crawler.arun(url=url, config=crawl_config)
                if result.success:
                    chunks = chunk_text(result.markdown_v2.raw_markdown)
                    display_memory_usage(
                        memory_display, f"Memory Usage after processing {url}"
                    )
                    state.memory_stats.metric(
                        "Memory Usage", f"{log_memory()} MB", delta=f"{len(chunks)} chunks"
                    )
                    for i, chunk in enumerate(chunks):
                        try:
                            embedding = await get_embedding(chunk)
                            completion = await openai_client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=create_json_messages(
                                    content=chunk[:1000],
                                    instruction="Extract a title and summary from this content",
                                ),
                                response_format={"type": "json_object"},
                            )
                            await store_chunk(url, i, chunk, embedding, completion)
                            display_memory_usage(
                                memory_display,
                                f"Memory Usage after storing chunk {i+1} from {url}",
                            )
                        except Exception as chunk_error:
                            st.error(
                                f"Error processing chunk {i+1} from {url}: {str(chunk_error)}"
                            )
                            continue
                    state.increment_completed()
                else:
                    st.error(f"Failed to crawl {url}")
            except Exception as e:
                error_display.error(f"❌ Error: {str(e)}")
            finally:
                memory_display.empty()
                error_display.empty()

    @asynccontextmanager
    async def create_crawler(browser_config: BrowserConfig):
        crawler = AsyncWebCrawler(config=browser_config)
        try:
            await crawler.start()
            yield crawler
        finally:
            await crawler.close()

    # --- Start Crawling ---
    if st.button("🕷️ Start Crawling", type="primary"):
        if url_input:
            progress_bar, status_text, memory_stats, details = create_progress_ui()
            urls = parse_urls(url_input)
            if urls:
                state = CrawlState(
                    total=len(urls),
                    progress_bar=progress_bar,
                    status_text=status_text,
                    memory_stats=memory_stats,
                    details=details,
                )
                browser_config = BrowserConfig(
                    headless=True,
                    verbose=False,
                    extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
                )
                crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
                try:
                    async def run_crawler():
                        async with create_crawler(browser_config) as crawler:
                            semaphore = asyncio.Semaphore(max_concurrent)
                            tasks = [
                                process_url(url, state, crawler, semaphore, crawl_config)
                                for url in urls
                            ]
                            await asyncio.gather(*tasks)
                            st.success("✅ Crawling completed successfully!")
                    asyncio.run(run_crawler())
                except Exception as e:
                    st.error(f"❌ Error during crawl: {str(e)}")
    
    # --- Chat Section (Centralized Chat Logic) ---
    st.subheader("🤖 Chat with AI about Your Crawl")
    # Ensure chat history is preserved across reruns
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("last_processed_message", "")
    
    # Display chat history
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Use st.chat_input to capture a chat message and delegate processing to chat_handler
    if prompt := st.chat_input("Message...", key="crawl4ai_chat_input"):
        # Append the user's message to the session state
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        
        # Process the chat message using the centralized chat handler.
        # The unique user_id from session state is now used instead of "default_user".
        final_response = process_chat_message(prompt, user_id=st.session_state.user_id, config={})
        
        # Append the assistant's response to the session state
        st.session_state.chat_messages.append({"role": "assistant", "content": final_response})
        
        st.write("Final Response:", final_response)

if __name__ == "__main__":
    main()
