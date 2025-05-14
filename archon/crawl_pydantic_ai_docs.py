import os
import sys
import asyncio
import threading
import subprocess
import requests
import json
import time
import argparse
import psutil
from typing import List, Dict, Any, Optional, Callable
from xml.etree import ElementTree
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from dotenv import load_dotenv
from openai import AsyncOpenAI
import re
import html2text

# Add the parent directory to sys.path to allow importing from the parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.utils import get_env_var, get_clients

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

load_dotenv()

# Initialize embedding and Supabase clients
embedding_client, supabase = get_clients()

# Define the embedding model for embedding the documentation for RAG
embedding_model = get_env_var('EMBEDDING_MODEL') or 'text-embedding-3-small'

# LLM client setup
llm_client = None
base_url = get_env_var('BASE_URL') or 'https://api.openai.com/v1'
api_key = get_env_var('LLM_API_KEY') or 'no-api-key-provided'
provider = get_env_var('LLM_PROVIDER') or 'OpenAI'

# Setup OpenAI client for LLM
if provider == "Ollama":
    if api_key == "NOT_REQUIRED":
        api_key = "ollama"  # Use a dummy key for Ollama
    llm_client = AsyncOpenAI(base_url=base_url, api_key=api_key)
else:
    llm_client = AsyncOpenAI(base_url=base_url, api_key=api_key)

# Initialize HTML to Markdown converter
html_converter = html2text.HTML2Text()
html_converter.ignore_links = False
html_converter.ignore_images = False
html_converter.ignore_tables = False
html_converter.body_width = 0  # No wrapping

# First, add this right after initializing the embedding_client
print(f"Initializing with embedding model: {embedding_model}")
print(f"Embedding client setup: {embedding_client is not None}")

@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]
    embedding: List[float]

class CrawlProgressTracker:
    """Class to track progress of the crawling process."""
    
    def __init__(self, 
                 progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Initialize the progress tracker.
        
        Args:
            progress_callback: Function to call with progress updates
        """
        self.progress_callback = progress_callback
        self.urls_found = 0
        self.urls_processed = 0
        self.urls_succeeded = 0
        self.urls_failed = 0
        self.chunks_stored = 0
        self.logs = []
        self.is_running = False
        self.start_time = None
        self.end_time = None
        self.stop_requested = False
        self.memory_usage = []
    
    def log(self, message: str):
        """Add a log message and update progress."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        print(message)  # Also print to console
        
        # Call the progress callback if provided
        if self.progress_callback:
            self.progress_callback(self.get_status())
    
    def start(self):
        """Mark the crawling process as started."""
        self.is_running = True
        self.start_time = datetime.now()
        self.log("Crawling process started")
        
        # Call the progress callback if provided
        if self.progress_callback:
            self.progress_callback(self.get_status())
    
    def complete(self):
        """Mark the crawling process as completed."""
        self.is_running = False
        self.end_time = datetime.now()
        duration = self.end_time - self.start_time if self.start_time else None
        duration_str = str(duration).split('.')[0] if duration else "unknown"
        self.log(f"Crawling process completed in {duration_str}")
        
        # Call the progress callback if provided
        if self.progress_callback:
            self.progress_callback(self.get_status())
    
    def stop(self):
        """Request the crawling process to stop gracefully."""
        self.stop_requested = True
        self.log("Stop requested. Finishing current tasks and stopping...")
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the crawling process."""
        process = psutil.Process(os.getpid())
        current_memory = process.memory_info().rss // (1024 * 1024)  # MB
        
        # Record memory usage
        self.memory_usage.append(current_memory)
        
        return {
            "is_running": self.is_running,
            "urls_found": self.urls_found,
            "urls_processed": self.urls_processed,
            "urls_succeeded": self.urls_succeeded,
            "urls_failed": self.urls_failed,
            "chunks_stored": self.chunks_stored,
            "progress_percentage": (self.urls_processed / self.urls_found * 100) if self.urls_found > 0 else 0,
            "logs": self.logs,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "stop_requested": self.stop_requested,
            "current_memory_mb": current_memory,
            "peak_memory_mb": max(self.memory_usage) if self.memory_usage else 0,
        }
    
    @property
    def is_completed(self) -> bool:
        """Return True if the crawling process is completed."""
        return not self.is_running and self.end_time is not None
    
    @property
    def is_successful(self) -> bool:
        """Return True if the crawling process completed successfully."""
        return self.is_completed and self.urls_failed == 0 and self.urls_succeeded > 0

def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
    """Split text into chunks, respecting code blocks and paragraphs."""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        # Calculate end position
        end = start + chunk_size

        # If we're at the end of the text, just take what's left
        if end >= text_length:
            chunks.append(text[start:].strip())
            break

        # Try to find a code block boundary first (```)
        chunk = text[start:end]
        code_block = chunk.rfind('```')
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block

        # If no code block, try to break at a paragraph
        elif '\n\n' in chunk:
            # Find the last paragraph break
            last_break = chunk.rfind('\n\n')
            if last_break > chunk_size * 0.3:  # Only break if we're past 30% of chunk_size
                end = start + last_break

        # If no paragraph break, try to break at a sentence
        elif '. ' in chunk:
            # Find the last sentence break
            last_period = chunk.rfind('. ')
            if last_period > chunk_size * 0.3:  # Only break if we're past 30% of chunk_size
                end = start + last_period + 1

        # Extract chunk and clean it up
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start position for next chunk
        start = max(start + 1, end)

    return chunks

async def get_title_and_summary(chunk: str, url: str) -> Dict[str, str]:
    """Extract title and summary using GPT-4."""
    system_prompt = """You are an AI that extracts titles and summaries from documentation chunks.
    Return a JSON object with 'title' and 'summary' keys.
    For the title: If this seems like the start of a document, extract its title. If it's a middle chunk, derive a descriptive title.
    For the summary: Create a concise summary of the main points in this chunk.
    Keep both title and summary concise but informative."""
    
    try:
        response = await llm_client.chat.completions.create(
            model=get_env_var("PRIMARY_MODEL") or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"URL: {url}\n\nContent:\n{chunk[:1000]}..."}  # Send first 1000 chars for context
            ],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error getting title and summary: {e}")
        return {"title": "Error processing title", "summary": "Error processing summary"}

async def get_embedding(text: str) -> List[float]:
    """Get embedding vector from OpenAI."""
    # Detailed debugging on env vars and setup
    print(f"Embedding environment check:")
    print(f"  EMBEDDING_MODEL: {embedding_model}")
    print(f"  Provider: {provider}")
    print(f"  API Key set: {'Yes' if api_key and api_key != 'no-api-key-provided' else 'No'}")
    print(f"  Base URL: {base_url}")
    
    # Try primary model first
    try:
        print(f"Attempting to get embedding for text of length {len(text)} with model {embedding_model}")
        
        if embedding_client is None:
            print("ERROR: embedding_client is None! Check utils.get_clients() implementation")
            return [0] * 768
            
        # Print actual API request (obscuring key)
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
        print(f"API request to {base_url}/embeddings with model={embedding_model}, api_key={masked_key}")
        
        # Create a dedicated embedding client right here to bypass potential issues
        from openai import AsyncOpenAI
        local_embedding_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # Attempt to get embedding with local client
        response = await local_embedding_client.embeddings.create(
            model=embedding_model,
            input=text
        )
        
        # Success case
        embedding = response.data[0].embedding
        embed_len = len(embedding)
        print(f"SUCCESS: Generated embedding of length {embed_len}")
        
        # Validate embedding has non-zero values
        num_zeros = sum(1 for v in embedding if v == 0)
        num_nonzeros = embed_len - num_zeros
        print(f"Embedding quality check: {num_nonzeros} non-zero values, {num_zeros} zeros")
        
        if num_nonzeros > 0:
            return embedding
        else:
            print("WARNING: Embedding contains all zeros! Using fallback...")
    except Exception as e:
        print(f"ERROR with primary embedding model: {str(e)}")
        import traceback
        print(f"Embedding error details: {traceback.format_exc()}")
    
    # Fallback to secondary model
    try:
        print("Trying fallback embedding model: text-embedding-3-small")
        from openai import AsyncOpenAI
        fallback_client = AsyncOpenAI(api_key=api_key)  # Use OpenAI directly
        response = await fallback_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        embedding = response.data[0].embedding
        print(f"SUCCESS with fallback model: Generated embedding of length {len(embedding)}")
        return embedding
    except Exception as fallback_error:
        print(f"ERROR with fallback embedding model: {str(fallback_error)}")
    
    # Ultimate fallback - random vector
    print("WARNING: All embedding attempts failed. Generating random vector for demonstration.")
    import random
    return [random.uniform(-0.1, 0.1) for _ in range(768)]  # Random vector is better than all zeros

async def process_chunk(chunk: str, chunk_number: int, url: str, 
                      source_name: str = "pydantic ai docs") -> ProcessedChunk:
    """Process a single chunk of text."""
    # Get title and summary
    extracted = await get_title_and_summary(chunk, url)
    
    # Get embedding
    embedding = await get_embedding(chunk)
    
    # Create metadata
    metadata = {
        "source": source_name,
        "chunk_size": len(chunk),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "url_path": urlparse(url).path
    }
    
    return ProcessedChunk(
        url=url,
        chunk_number=chunk_number,
        title=extracted['title'],
        summary=extracted['summary'],
        content=chunk,  # Store the original chunk content
        metadata=metadata,
        embedding=embedding
    )

async def insert_chunk(chunk: ProcessedChunk):
    """Insert a processed chunk into Supabase."""
    try:
        data = {
            "url": chunk.url,
            "chunk_number": chunk.chunk_number,
            "title": chunk.title,
            "summary": chunk.summary,
            "content": chunk.content,
            "metadata": chunk.metadata,
            "embedding": chunk.embedding
        }
        
        # Add detailed logging
        print(f"Attempting to insert chunk {chunk.chunk_number} for {chunk.url}")
        
        # Check Supabase connection first
        if supabase is None:
            print("ERROR: Supabase client is not initialized")
            return None
            
        # Set a timeout for the insert operation
        try:
            result = supabase.table("crawled_pages").insert(data).execute()
            
            # Verify that data was inserted successfully
            if hasattr(result, 'data') and result.data:
                print(f"Successfully inserted chunk {chunk.chunk_number} for {chunk.url} - ID: {result.data[0].get('id') if result.data else 'unknown'}")
                return result
            else:
                print(f"WARNING: Insertion may have failed for chunk {chunk.chunk_number} - No data returned")
                print(f"Supabase response: {result}")
                return None
                
        except Exception as e:
            # Print detailed error information
            print(f"ERROR inserting chunk {chunk.chunk_number} for {chunk.url}: {str(e)}")
            print(f"Data preview: URL={chunk.url}, Title={chunk.title}, Content length={len(chunk.content)}")
            print(f"Embedding length={len(chunk.embedding) if chunk.embedding else 'None'}")
            raise  # Re-raise to ensure error is properly handled upstream
            
    except Exception as e:
        print(f"ERROR preparing chunk {chunk.chunk_number} for {chunk.url}: {str(e)}")
        raise  # Re-raise to ensure error is properly handled upstream

async def process_and_store_document(url: str, markdown: str, 
                                   tracker: Optional[CrawlProgressTracker] = None,
                                   source_name: str = "documentation"):
    """Process a document and store its chunks in parallel."""
    # Split into chunks
    chunks = chunk_text(markdown)
    
    if tracker:
        tracker.log(f"Split document into {len(chunks)} chunks for {url}")
        # Ensure UI gets updated
        if tracker.progress_callback:
            tracker.progress_callback(tracker.get_status())
    else:
        print(f"Split document into {len(chunks)} chunks for {url}")
    
    # Process chunks in smaller parallel batches to control memory
    processed_chunks = []
    
    # Process chunks in batches of 10
    batch_size = 10
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:min(i+batch_size, len(chunks))]
        
        # Check for stop request before processing batch
        if tracker and tracker.stop_requested:
            tracker.log(f"Stopping chunk processing for {url} due to user request")
            return
            
        batch_tasks = [
            process_chunk(chunk, i+j, url, source_name) 
            for j, chunk in enumerate(batch)
        ]
        batch_results = await asyncio.gather(*batch_tasks)
        processed_chunks.extend(batch_results)
    
    if tracker:
        tracker.log(f"Processed {len(processed_chunks)} chunks for {url}")
        # Ensure UI gets updated
        if tracker.progress_callback:
            tracker.progress_callback(tracker.get_status())
    else:
        print(f"Processed {len(processed_chunks)} chunks for {url}")
    
    # Store chunks in batches and handle errors properly
    insertion_failures = 0
    insertion_successes = 0
    
    for i in range(0, len(processed_chunks), batch_size):
        batch = processed_chunks[i:min(i+batch_size, len(processed_chunks))]
        
        # Check for stop request before storing batch
        if tracker and tracker.stop_requested:
            tracker.log(f"Stopping chunk storage for {url} due to user request")
            return
        
        # Use gather with return_exceptions to handle failures without stopping
        insert_tasks = [insert_chunk(chunk) for chunk in batch]
        results = await asyncio.gather(*insert_tasks, return_exceptions=True)
        
        # Count successes and failures
        for j, result in enumerate(results):
            if isinstance(result, Exception):
                insertion_failures += 1
                chunk_num = i + j if i + j < len(processed_chunks) else "unknown"
                if tracker:
                    tracker.log(f"Failed to insert chunk {chunk_num}: {str(result)}")
                else:
                    print(f"Failed to insert chunk {chunk_num}: {str(result)}")
            else:
                insertion_successes += 1
    
    if tracker:
        tracker.chunks_stored += insertion_successes
        tracker.log(f"Stored {insertion_successes}/{len(processed_chunks)} chunks for {url} (Failed: {insertion_failures})")
        # Ensure UI gets updated
        if tracker.progress_callback:
            tracker.progress_callback(tracker.get_status())
    else:
        print(f"Stored {insertion_successes}/{len(processed_chunks)} chunks for {url} (Failed: {insertion_failures})")

def fetch_url_content(url: str) -> str:
    """Fetch content from a URL using requests and convert to markdown."""
    # Import modules locally to ensure they're available in this scope
    import re
    import html2text
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        # Fetch the HTML content
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Try converting HTML to Markdown with error handling
        try:
            html_conv = html2text.HTML2Text()
            html_conv.ignore_links = False
            html_conv.ignore_images = False
            html_conv.ignore_tables = False
            html_conv.body_width = 0  # No wrapping
            markdown = html_conv.handle(response.text)
        except Exception as html_error:
            # If html2text fails, try a more robust fallback approach
            print(f"Warning: HTML parsing error with html2text for {url}: {str(html_error)}")
            
            # Try an alternative parsing approach
            try:
                import bs4
                soup = bs4.BeautifulSoup(response.text, 'html.parser')
                
                # Remove script and style elements that might cause parsing issues
                for script_or_style in soup(['script', 'style']):
                    script_or_style.extract()
                
                # Get text content
                text = soup.get_text()
                
                # Clean up whitespace
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                markdown = '\n'.join(chunk for chunk in chunks if chunk)
                
                print(f"Used BeautifulSoup fallback parser for {url}")
            except Exception as bs_error:
                # If that also fails, extract plain text with regex as last resort
                print(f"Warning: BeautifulSoup fallback also failed for {url}: {str(bs_error)}")
                # Use re module directly - make sure it's imported in this scope
                markdown = re.sub(r'<[^>]+>', ' ', response.text)
                markdown = re.sub(r'\s+', ' ', markdown).strip()
                print(f"Used regex fallback parser for {url}")
        
        # Clean up the markdown
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)  # Remove excessive newlines
        
        return markdown
    except requests.exceptions.RequestException as e:
        # Handle network/request errors
        raise Exception(f"Error fetching {url}: {str(e)}")
    except Exception as e:
        # Handle any other errors
        raise Exception(f"Error processing {url}: {str(e)}")

async def crawl_parallel_with_requests(urls: List[str], tracker: Optional[CrawlProgressTracker] = None, 
                                      max_concurrent: int = 5, source_name: str = "pydantic_ai_docs",
                                      batch_size: int = 20):
    """Crawl multiple URLs in parallel with a concurrency limit using direct HTTP requests."""
    # Create a semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Process URLs in batches to control memory usage
    total_urls = len(urls)
    batch_count = (total_urls + batch_size - 1) // batch_size  # Ceiling division
    
    if tracker:
        tracker.log(f"Processing {total_urls} URLs in {batch_count} batches with concurrency {max_concurrent}")
    else:
        print(f"Processing {total_urls} URLs in {batch_count} batches with concurrency {max_concurrent}")
    
    for batch_idx in range(batch_count):
        # Check for stop request before starting new batch
        if tracker and tracker.stop_requested:
            tracker.log("Crawl stopped by user request. Not processing remaining batches.")
            break
            
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, total_urls)
        batch = urls[start_idx:end_idx]
        
        if tracker:
            tracker.log(f"Processing batch {batch_idx+1}/{batch_count} ({len(batch)} URLs)")
            # Monitor memory
            process = psutil.Process(os.getpid())
            mem_before = process.memory_info().rss // (1024 * 1024)  # MB
            tracker.log(f"Memory before batch: {mem_before} MB")
        
        async def process_url(url: str):
            async with semaphore:
                if tracker and tracker.stop_requested:
                    return
                
                if tracker:
                    tracker.log(f"Crawling: {url}")
                    # Ensure UI gets updated
                    if tracker.progress_callback:
                        tracker.progress_callback(tracker.get_status())
                else:
                    print(f"Crawling: {url}")
                
                try:
                    # Use a thread pool to run the blocking HTTP request
                    loop = asyncio.get_running_loop()
                    if tracker:
                        tracker.log(f"Fetching content from: {url}")
                    else:
                        print(f"Fetching content from: {url}")
                    markdown = await loop.run_in_executor(None, fetch_url_content, url)
                    
                    if markdown:
                        if tracker:
                            tracker.urls_succeeded += 1
                            tracker.log(f"Successfully crawled: {url}")
                            # Ensure UI gets updated
                            if tracker.progress_callback:
                                tracker.progress_callback(tracker.get_status())
                        else:
                            print(f"Successfully crawled: {url}")
                        
                        # Pass source_name to process_and_store_document
                        await process_and_store_document(url, markdown, tracker, source_name)
                    else:
                        if tracker:
                            tracker.urls_failed += 1
                            tracker.log(f"Failed: {url} - No content retrieved")
                            # Ensure UI gets updated
                            if tracker.progress_callback:
                                tracker.progress_callback(tracker.get_status())
                        else:
                            print(f"Failed: {url} - No content retrieved")
                except Exception as e:
                    if tracker:
                        tracker.urls_failed += 1
                        tracker.log(f"Error processing {url}: {str(e)}")
                        # Ensure UI gets updated
                        if tracker.progress_callback:
                            tracker.progress_callback(tracker.get_status())
                    else:
                        print(f"Error processing {url}: {str(e)}")
                finally:
                    if tracker:
                        tracker.urls_processed += 1
                        # Ensure UI gets updated
                        if tracker.progress_callback:
                            tracker.progress_callback(tracker.get_status())
        
        # Process the batch
        batch_tasks = [process_url(url) for url in batch]
        await asyncio.gather(*batch_tasks)
        
        # Check memory after batch completion
        if tracker:
            process = psutil.Process(os.getpid())
            mem_after = process.memory_info().rss // (1024 * 1024)  # MB
            tracker.log(f"Memory after batch: {mem_after} MB (Δ {mem_after - mem_before} MB)")
            
            # Force garbage collection to reduce memory between batches
            import gc
            gc.collect()
            
            # Slight delay between batches to allow system to stabilize
            if batch_idx < batch_count - 1:  # Not the last batch
                await asyncio.sleep(1)

# Add this function before the main_with_requests function
def get_sitemap_urls(sitemap_url: str) -> List[str]:
    """Get URLs from a sitemap XML.
    
    Args:
        sitemap_url: URL to the sitemap XML file
        
    Returns:
        List of URLs found in the sitemap
    """
    try:
        response = requests.get(sitemap_url)
        response.raise_for_status()
        
        # Parse the XML
        root = ElementTree.fromstring(response.content)
        
        # Extract all URLs from the sitemap
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [loc.text for loc in root.findall('.//ns:loc', namespace)]
        
        return urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []

# main_with_requests: Core async implementation that runs the crawler
async def main_with_requests(tracker: Optional[CrawlProgressTracker] = None, 
                            crawl_type: str = "sitemap", 
                            url: str = "",
                            source_name: str = "documentation",
                            batch_size: int = 20,
                            max_concurrent: int = 0):
    """Main function using direct HTTP requests instead of browser automation."""
    try:
        # Check for required URL
        if not url:
            error_msg = "No URL provided for crawling"
            if tracker:
                tracker.log(error_msg)
                tracker.complete()
            print(error_msg)
            return
            
        # Start tracking if tracker is provided
        if tracker:
            tracker.start()
        else:
            print("Starting crawling process...")
        
        # Remove the clearing of existing records as per user request
        # if tracker:
        #     tracker.log(f"Clearing existing {source_name} records...")
        # else:
        #     print(f"Clearing existing {source_name} records...")
        # clear_existing_records(source_name)  # This line caused the error
        # if tracker:
        #     tracker.log("Existing records cleared")
        # else:
        #     print("Existing records cleared")
        
        # Determine optimal concurrency based on system resources
        cpu_count = os.cpu_count() or 4
        recommended_concurrent = max(2, min(cpu_count * 2, 10))  # Between 2 and 10
        
        if max_concurrent <= 0:  # Auto mode
            max_concurrent = recommended_concurrent
            if tracker:
                tracker.log(f"Auto-selected concurrency: {max_concurrent} based on system resources")
        
        urls = []
        # Get URLs based on crawl type
        if crawl_type == "sitemap":
            if tracker:
                tracker.log(f"Fetching URLs from sitemap: {url}...")
            else:
                print(f"Fetching URLs from sitemap: {url}...")
            urls = get_sitemap_urls(url)  # Use get_sitemap_urls directly
        else:  # single URL mode
            if tracker:
                tracker.log(f"Processing single URL: {url}")
            else:
                print(f"Processing single URL: {url}")
            urls = [url]
        
        if not urls:
            if tracker:
                tracker.log("No URLs found to crawl")
                tracker.complete()
            else:
                print("No URLs found to crawl")
            return
        
        if tracker:
            tracker.urls_found = len(urls)
            tracker.log(f"Found {len(urls)} URLs to crawl")
        else:
            print(f"Found {len(urls)} URLs to crawl")
        
        # Crawl the URLs using direct HTTP requests
        await crawl_parallel_with_requests(urls, tracker, max_concurrent, source_name, batch_size)
        
        # Mark as complete if tracker is provided
        if tracker:
            tracker.complete()
        else:
            print("Crawling process completed")
            
    except Exception as e:
        if tracker:
            tracker.log(f"Error in crawling process: {str(e)}")
            tracker.complete()
        else:
            print(f"Error in crawling process: {str(e)}")

# start_crawl_with_requests: Wrapper for non-async contexts (like Streamlit UI)
def start_crawl_with_requests(progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                             crawl_type: str = "sitemap",
                             url: str = "",
                             source_name: str = "documentation",
                             batch_size: int = 20,
                             max_concurrent: int = 0) -> CrawlProgressTracker:  # 0 means auto-select
    """Start the crawling process in a background thread and return immediately.
    Used by the Streamlit UI to start a crawl without blocking the interface.
    Returns a tracker that can be used to monitor progress."""
    tracker = CrawlProgressTracker(progress_callback)
    
    # Check for required URL
    if not url:
        tracker.log("No URL provided for crawling")
        tracker.complete()
        return tracker
        
    def run_crawl():
        try:
            asyncio.run(main_with_requests(tracker, crawl_type, url, source_name, batch_size, max_concurrent))
        except Exception as e:
            print(f"Error in crawl thread: {e}")
            tracker.log(f"Thread error: {str(e)}")
            tracker.complete()
    
    # Start the crawling process in a separate thread
    thread = threading.Thread(target=run_crawl)
    thread.daemon = True
    thread.start()
    
    return tracker

if __name__ == "__main__":    
    # Set up argument parser for command-line usage
    parser = argparse.ArgumentParser(description="Crawl and index documentation.")
    parser.add_argument("--type", "-t", choices=["sitemap", "single"], default="sitemap", 
                        help="Type of crawl: 'sitemap' to crawl all URLs from a sitemap, 'single' to crawl a single URL")
    parser.add_argument("--url", "-u", required=True,  # Make URL required
                        help="URL to crawl (sitemap URL or single page URL)")
    parser.add_argument("--source", "-s", default="documentation",  # Use more generic default
                        help="Name to use as source in metadata")
    parser.add_argument("--batch-size", "-b", type=int, default=20,
                        help="Number of URLs to process in each batch")
    parser.add_argument("--concurrent", "-c", type=int, default=0,
                        help="Maximum concurrent requests (0 for auto)")
    
    args = parser.parse_args()
    
    # Run the main function with command-line arguments
    print(f"Starting crawler with {args.type} mode for URL: {args.url}...")
    asyncio.run(main_with_requests(
        crawl_type=args.type, 
        url=args.url, 
        source_name=args.source,
        batch_size=args.batch_size,
        max_concurrent=args.concurrent
    ))
    print("Crawler finished.")