import streamlit as st
import requests  # For MCP HTTP calls
import time
import sys
import os
import subprocess
import threading
import json
import asyncio
from pathlib import Path
import logging
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "agent-resources", "tools"))
from gitn8n import process_github_repo

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# No longer needed as we're using direct MCP HTTP calls instead
# from archon.crawl_pydantic_ai_docs import start_crawl_with_requests

# Add MCP crawl4ai path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp-crawl4ai-rag", "src"))
# Direct import not needed for HTTP approach, but useful if we want direct function calls
# from crawl4ai_mcp import smart_crawl_url, crawl_single_page
from utils.utils import get_env_var, create_new_tab_button
from supabase import create_client
from openai import OpenAI




# Add caching for expensive operations
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_database_stats(_supabase_client, source_name):
    """Cache database statistics to avoid repeated queries"""
    try:
        result = _supabase_client.table("crawled_pages").select("count", count="exact").eq("metadata->>source", source_name).execute()
        count = result.count if hasattr(result, "count") else 0
        return count
    except Exception as e:
        return {"error": str(e)}

# Function to run subprocess in background
def run_subprocess_async(cmd, callback_fn, timeout=300):
    """Run subprocess asynchronously and call callback function when done"""
    def target():
        try:
            # Add stderr logging to capture error output
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Track progress with incremental output
            stdout = []
            stderr = []
            
            # Set a timeout
            end_time = time.time() + timeout
            
            while process.poll() is None:
                # Check for timeout
                if time.time() > end_time:
                    process.terminate()
                    try:
                        process.wait(timeout=5)  # Give it 5 seconds to terminate
                    except subprocess.TimeoutExpired:
                        process.kill()  # Force kill if not terminated
                    callback_fn({"timeout": True, "stdout": "".join(stdout), "stderr": "".join(stderr)})
                    return
                
                # Read output without blocking
                stdout_line = process.stdout.readline()
                if stdout_line:
                    stdout.append(stdout_line)
                    # Update status in real-time for URL processing
                    if "Fetching" in stdout_line or "Successfully fetched" in stdout_line:
                        st.session_state.lightrag_status = stdout_line.strip()
                
                stderr_line = process.stderr.readline()
                if stderr_line:
                    stderr.append(stderr_line)
                    # Update error status in real-time
                    if "Error" in stderr_line:
                        st.session_state.lightrag_status = f"❌ {stderr_line.strip()}"
                
                # Avoid tight loop
                if not stdout_line and not stderr_line:
                    time.sleep(0.1)
            
            # Get remaining output
            remaining_stdout, remaining_stderr = process.communicate()
            stdout.append(remaining_stdout)
            stderr.append(remaining_stderr)
            
            result = subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout="".join(stdout),
                stderr="".join(stderr)
            )
            
            callback_fn(result)
            
        except Exception as e:
            callback_fn({"error": str(e)})
    
    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    return thread

def documentation_tab(supabase_client):
    """Display the documentation interface"""
    # Initialize session state variables only once at the start
    if "crawl_tracker" not in st.session_state:
        st.session_state.crawl_tracker = None
    if "crawl_status" not in st.session_state:
        st.session_state.crawl_status = None
    if "last_update_time" not in st.session_state:
        st.session_state.last_update_time = time.time()
    if "lightrag_processing" not in st.session_state:
        st.session_state.lightrag_processing = False
    if "lightrag_status" not in st.session_state:
        st.session_state.lightrag_status = ""
    if "lightrag_thread" not in st.session_state:
        st.session_state.lightrag_thread = None
    
    st.header("Documentation")
    
    # Create tabs for documentation sources
    doc_tabs = st.tabs(["Custom Documentation Crawler", "LightRAG Text Dump", "GitHub → Supabase Uploader", "YouTube Uploader", "n8n → Pydantic-AI Chat"])

    with doc_tabs[0]:
        st.subheader("Custom Documentation Crawler")
        st.markdown("""
        This section allows you to crawl and index custom documentation from a URL or sitemap.
        The crawler will:
        
        1. Either fetch a single URL or retrieve URLs from a sitemap
        2. Crawl each page and extract content
        3. Split content into chunks
        4. Generate embeddings for each chunk
        5. Store the chunks in the Supabase database
        
        This process may take several minutes depending on the number of pages.
        """)
        
        # Check if the database is configured
        if not get_env_var("SUPABASE_URL") or not get_env_var("SUPABASE_API_KEY"):
            st.warning("⚠️ Supabase is not configured. Please set up your environment variables first.")
            create_new_tab_button("Go to Environment Section", "Environment", key="goto_env_from_custom_docs")
        else:
            # Source name input
            source_name = st.text_input("Source Name (used to identify these docs in the database)", 
                                       value="custom_documentation",
                                       key="custom_source_name")
            
            # URL input - No URL type selection needed as MCP auto-detects URL type
            url = st.text_input("Enter URL (webpage, sitemap.xml, or text file)", 
                               placeholder="https://example.com/documentation/ or https://example.com/sitemap.xml",
                               key="custom_url")
            
            # Create columns for the buttons
            col1, col2 = st.columns(2)
            
            with col1:
                # Button to start crawling
                if st.button("Start Crawl", key="crawl_custom") and not (st.session_state.crawl_tracker and st.session_state.crawl_tracker.is_running):
                    if not url:
                        st.error("❌ Please enter a URL.")
                    elif not source_name:
                        st.error("❌ Please enter a source name.")
                    else:
                        try:
                            # MCP server endpoint
                            mcp_url = "http://localhost:8051/smart_crawl_url"  # Change if different
                            max_depth = 3  # Or make this a UI input if you want
                            chunk_size = 5000  # Or make this a UI input if you want
                            with st.spinner("Contacting MCP server and crawling..."):
                                payload = {
                                    "url": url,
                                    "max_depth": max_depth,
                                    "chunk_size": chunk_size,
                                    "source_name": source_name  # Add source name to payload for proper labeling
                                }
                                response = requests.post(mcp_url, json=payload, timeout=360)
                                if response.status_code == 200:
                                    st.success("Crawl complete!")
                                    st.json(response.json() if response.headers.get('content-type','').startswith('application/json') else response.text)
                                else:
                                    st.error(f"MCP server error: {response.status_code}\n{response.text}")
                        except Exception as e:
                            st.error(f"❌ Error starting crawl: {str(e)}")
            

            # Display crawling progress if a crawl is in progress or has completed
            display_crawl_progress()
            
            # Display database statistics for custom source
            if source_name:
                display_database_stats(supabase_client, source_name, "Documentation")

    with doc_tabs[1]:
        display_lightrag_text_dump()

    # --- GitHub → Supabase Uploader Tab ---
    with doc_tabs[2]:
        st.title("🚀 GitHub → Supabase Uploader")
        source_name = st.text_input("Source Name (optional)", "", key="github_source_name")
        repo_url = st.text_input("🌍 Enter GitHub Repository URL:", key="github_repo_url")
        if st.button("🔄 Clone and Upload", key="github_clone_upload"):
            if not repo_url:
                st.error("Please enter a valid GitHub repository URL.")
            else:
                if source_name:
                    os.environ["SOURCE_NAME"] = source_name
                st.info("🔄 Cloning repository and uploading to Supabase...")
                try:
                    process_github_repo(repo_url)
                    st.success("✅ Repository cloned and processed successfully!")
                except subprocess.CalledProcessError as e:
                    st.error(f"Git clone failed: {e}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")

    # --- YouTube Uploader Tab ---
    with doc_tabs[3]:
        st.title("📺 YouTube → Supabase Uploader")
        st.markdown("""
        Enter a YouTube video or playlist URL to process and upload transcript/chunks to Supabase.
        """)
        youtube_url = st.text_input("YouTube Video or Playlist URL", key="youtube_url_input")
        if st.button("Process YouTube URL", key="youtube_process_btn"):
            if not youtube_url:
                st.error("Please enter a YouTube video or playlist URL.")
            else:
                with st.spinner("Processing via Python call..."):
                    try:
                        sys.path.append(os.path.join(os.path.dirname(__file__), "..", "agent-resources", "tools"))
                        import youtube_tool
                        if hasattr(youtube_tool, "process_youtube_url"):
                            youtube_tool.process_youtube_url(youtube_url)
                            st.success("YouTube processing complete.")
                        else:
                            st.warning("Direct UI processing is not available. Please add process_youtube_url(url) to youtube_tool.py.")
                    except Exception as e:
                        st.error(f"Python call error: {str(e)}")

    # --- n8n → Pydantic-AI Chat Tab ---
    with doc_tabs[4]:
        st.title("🔄 n8n → 🐍 Pydantic-AI Chat")
        if "n8n_messages" not in st.session_state:
            st.session_state.n8n_messages = []
        for msg in st.session_state.n8n_messages:
            if isinstance(msg, ModelRequest) or isinstance(msg, ModelResponse):
                for part in msg.parts:
                    display_message_part(part)
        user_input = st.chat_input("What questions do you have about Pydantic-AI?", key="n8n_chat_input")
        if user_input:
            st.session_state.n8n_messages.append(
                ModelRequest(parts=[UserPromptPart(content=user_input)])
            )
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    task = asyncio.create_task(run_agent_with_streaming(user_input))

                else:
                    asyncio.run(run_agent_with_streaming(user_input))
        uploaded = st.file_uploader("Upload n8n workflow JSON", type=["json"], key="n8n_workflow_upload")
        if uploaded:
            try:
                workflow = json.loads(uploaded.getvalue())
                st.success("✅ Workflow loaded successfully!")
                wf_str = json.dumps(workflow, indent=2)
                st.session_state.n8n_messages.append(
                    ModelRequest(parts=[UserPromptPart(content=wf_str)])
                )
                with st.chat_message("user"):
                    st.markdown(f"Uploaded Workflow:\n```json\n{wf_str}\n```")
                with st.chat_message("assistant"):
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop and loop.is_running():
                        task = asyncio.create_task(run_agent_with_streaming(wf_str))

                    else:
                        asyncio.run(run_agent_with_streaming(wf_str))
            except json.JSONDecodeError:
                st.error("Invalid JSON file. Please upload valid n8n workflow JSON.")


def display_crawl_progress():
    """Display the progress of a running crawl"""
    if "crawl_tracker" in st.session_state and st.session_state.crawl_tracker:
        # Create a container for the progress information
        progress_container = st.container()
        
        with progress_container:
            # Get the latest status
            current_time = time.time()
            # Update status every second
            if current_time - st.session_state.last_update_time >= 1:
                st.session_state.crawl_status = st.session_state.crawl_tracker.get_status()
                st.session_state.last_update_time = current_time
            
            status = st.session_state.crawl_status
            
            # Display a progress bar
            if status and status["urls_found"] > 0:
                progress = status["urls_processed"] / status["urls_found"]
                st.progress(progress)
            
            # Display status metrics
            col1, col2, col3, col4 = st.columns(4)
            if status:
                col1.metric("URLs Found", status["urls_found"])
                col2.metric("URLs Processed", status["urls_processed"])
                col3.metric("Successful", status["urls_succeeded"])
                col4.metric("Failed", status["urls_failed"])
            else:
                col1.metric("URLs Found", 0)
                col2.metric("URLs Processed", 0)
                col3.metric("Successful", 0)
                col4.metric("Failed", 0)
            
            # Display logs in an expander
            with st.expander("Crawling Logs", expanded=True):
                if status and "logs" in status:
                    logs_text = "\n".join(status["logs"][-20:])  # Show last 20 logs
                    st.code(logs_text)
                else:
                    st.code("No logs available yet...")
            
            # Show completion message
            if status and not status["is_running"] and status["end_time"]:
                if status["urls_failed"] == 0:
                    st.success("✅ Crawling process completed successfully!")
                else:
                    st.warning(f"⚠️ Crawling process completed with {status['urls_failed']} failed URLs.")
        
        # Auto-refresh while crawling is in progress
        if not status or status["is_running"]:
            st.rerun()

def display_database_stats(supabase_client, source_name, display_name):
    """Display database statistics for a specific source"""
    st.subheader(f"{display_name} Statistics")
    
    # Use cached function to get stats
    stats = get_database_stats(supabase_client, source_name)
    
    if isinstance(stats, dict) and "error" in stats:
        st.error(f"Error querying database: {stats['error']}")
        return
    
    # Display the count
    st.metric(f"{display_name} Chunks", stats)
    
    # Add a button to view the data
    if stats > 0 and st.button(f"View {display_name} Data", key=f"view_{source_name}_data"):
        # Query a sample of the data
        sample_data = supabase_client.table("crawled_pages").select("url,title,summary,chunk_number").eq("metadata->>source", source_name).limit(10).execute()
        
        # Display the sample data
        st.dataframe(sample_data.data)
        st.info("Showing up to 10 sample records. The database contains more records.")

def lightrag_process_callback(result):
    """Callback function to handle subprocess results"""
    if isinstance(result, dict):
        if "timeout" in result:
            st.session_state.lightrag_status = "❌ Processing timed out after 5 minutes."
            if "stdout" in result and result["stdout"]:
                st.session_state.lightrag_stdout = result["stdout"]
            if "stderr" in result and result["stderr"]:
                st.session_state.lightrag_stderr = result["stderr"]
        else:
            st.session_state.lightrag_status = f"❌ Error: {result.get('error', 'Unknown error')}"
    else:
        if result.returncode == 0:
            st.session_state.lightrag_status = "✅ Text successfully processed and stored in LightRAG."
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            st.session_state.lightrag_status = f"❌ Error: {error_msg}"
            st.session_state.lightrag_stdout = result.stdout
            st.session_state.lightrag_stderr = result.stderr
    
    st.session_state.lightrag_processing = False
    st.session_state.lightrag_thread = None

def display_lightrag_text_dump():
    """Display the LightRAG Text Dump interface"""
    st.subheader("LightRAG Text Dump")
    st.markdown("""
    This section allows you to insert text directly into LightRAG for processing and retrieval.
    
    1. Either paste your text in the textarea below
    2. Or enter a URL to fetch content from
    3. Click the "Process Text" or "Fetch & Process URL" button to add the content to LightRAG
    
    The text will be automatically processed and made available for retrieval.
    """)
    
    # Text input section
    st.subheader("Text Input")
    text_input = st.text_area(
        "Enter Text to Process", 
        height=200,
        placeholder="Paste your text here...",
        key="lightrag_text_input"
    )
    
    if st.button("Process Text", key="process_lightrag_text") and not st.session_state.lightrag_processing:
        if not text_input.strip():
            st.error("❌ Please enter some text to process.")
        else:
            st.session_state.lightrag_processing = True
            st.session_state.lightrag_status = "Processing text..."
            try:
                # Save text to a temporary file
                temp_file = "/tmp/lightrag_text_input.txt"
                with open(temp_file, "w") as f:
                    f.write(text_input)
                
                # Run the process asynchronously
                script_path = "/var/www/mcpg/light-rag-agent/LightRAG/insert_pydantic_docs.py"
                cmd = ["python", script_path, "-m", "file", "-i", temp_file]
                st.session_state.lightrag_thread = run_subprocess_async(cmd, lightrag_process_callback, 300)
            except Exception as e:
                st.session_state.lightrag_status = f"❌ Error processing text: {str(e)}"
                st.session_state.lightrag_processing = False
            
            # Use a less resource-intensive approach than full page rerun
            st.empty().info("Processing started. Wait for the status update...")
    
    # URL input section
    st.subheader("URL Input")
    url_input = st.text_input(
        "Enter URL to Fetch and Process",
        placeholder="https://example.com/documentation.txt",
        key="lightrag_url_input"
    )
    
    # Add special handling for problematic URLs
    is_problematic_url = "ai.pydantic.dev" in url_input if url_input else False
    
    # Show fallback option and more options for problematic URLs
    col1, col2 = st.columns(2)
    
    with col1:
        # Show fallback option for problematic URLs
        if is_problematic_url:
            st.warning("⚠️ The Pydantic docs URL may require special handling.")
            use_fallback = st.checkbox("Use fallback methods", value=True,
                                     help="Try multiple download methods including curl")
        else:
            use_fallback = False
    
    with col2:
        # Add option for direct text input as alternative
        if is_problematic_url:
            st.info("💡 Tip: If fetching fails, try downloading the file manually and using the text input above.")
    
    if st.button("Fetch & Process URL", key="process_lightrag_url") and not st.session_state.lightrag_processing:
        if not url_input.strip():
            st.error("❌ Please enter a URL to fetch.")
        else:
            st.session_state.lightrag_processing = True
            st.session_state.lightrag_status = f"Fetching content from {url_input}..."
            try:
                # Run the process asynchronously
                script_path = "/var/www/mcpg/light-rag-agent/LightRAG/insert_pydantic_docs.py"
                cmd = ["python", script_path, "-m", "url", "-i", url_input]
                
                # Add fallback flag if needed
                if use_fallback:
                    cmd.append("-f")
                    
                st.session_state.lightrag_thread = run_subprocess_async(cmd, lightrag_process_callback, 300)
            except Exception as e:
                st.session_state.lightrag_status = f"❌ Error: {str(e)}"
                st.session_state.lightrag_processing = False
            
            # Use a less resource-intensive approach than full page rerun
            st.empty().info("Processing started. Wait for the status update...")
    
    # Initialize additional state variables
    if "lightrag_stdout" not in st.session_state:
        st.session_state.lightrag_stdout = ""
    if "lightrag_stderr" not in st.session_state:
        st.session_state.lightrag_stderr = ""
    
    # Display processing status with detailed logs
    if st.session_state.lightrag_processing:
        st.info(st.session_state.lightrag_status)
        with st.spinner("Processing..."):
            # Check thread status at reasonable intervals rather than continuous rerun
            time.sleep(0.1)
            # Force a rerun every 2 seconds to update status
            if time.time() % 2 < 0.1:
                st.rerun()
    elif st.session_state.lightrag_status:
        if "✅" in st.session_state.lightrag_status:
            st.success(st.session_state.lightrag_status)
        elif "❌" in st.session_state.lightrag_status:
            st.error(st.session_state.lightrag_status)
            # Show detailed error logs in expanders if available
            if st.session_state.lightrag_stderr:
                with st.expander("Error Details"):
                    st.code(st.session_state.lightrag_stderr)
            if st.session_state.lightrag_stdout:
                with st.expander("Process Output"):
                    st.code(st.session_state.lightrag_stdout)
        else:
            st.info(st.session_state.lightrag_status)