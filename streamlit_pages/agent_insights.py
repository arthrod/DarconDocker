"""
Agent Insights Dashboard

A Streamlit dashboard for visualizing agent performance and interactions using Langfuse.
"""
import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
import sys
import logging
import math  # Moved import to the top
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field, asdict

# Suppress InsecureRequestWarning when using verify=False
urllib3 = __import__("urllib3")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add the parent directory to the path to fix import issues
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import agent discovery
from archon.discovery import discover_agents

# Try to import Langfuse
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Data models using dataclasses for type safety and consistency
@dataclass
class TraceMetadata:
    """Metadata associated with a trace."""
    agent_id: str = "unknown"
    agent_name: str = "unknown"
    parent_span_id: Optional[str] = None
    parent_trace_id: Optional[str] = None
    # Add any other metadata fields that might be present

@dataclass
class Trace:
    """Dataclass representing a Langfuse trace with consistent field structure."""
    id: str = ""
    name: str = ""
    timestamp: str = ""
    latency_ms: int = 0
    status: str = ""
    metadata: TraceMetadata = field(default_factory=TraceMetadata)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Trace':
        """Create a Trace instance from a dictionary."""
        # Handle nested metadata
        metadata_dict = data.get("metadata", {})
        if not isinstance(metadata_dict, dict):
            metadata_dict = {}
            
        metadata = TraceMetadata(
            agent_id=metadata_dict.get("agent_id", "unknown"),
            agent_name=metadata_dict.get("agent_name", "unknown"),
            parent_span_id=metadata_dict.get("parent_span_id"),  # Add parent span ID
            parent_trace_id=metadata_dict.get("parent_trace_id")  # Add parent trace ID
        )
        
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            timestamp=data.get("timestamp", ""),
            latency_ms=int(data.get("latency_ms", 0) or 0),
            status=data.get("status", ""),
            metadata=metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the Trace instance to a dictionary."""
        return asdict(self)

@dataclass
class GenerationMetadata:
    """Metadata associated with a generation."""
    agent_id: str = "unknown"
    agent_name: str = "unknown"
    # Add any other metadata fields that might be present

@dataclass
class Generation:
    """Dataclass representing a Langfuse generation with consistent field structure."""
    id: str = ""
    model: str = ""
    timestamp: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    metadata: GenerationMetadata = field(default_factory=GenerationMetadata)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Generation':
        """Create a Generation instance from a dictionary."""
        # Handle nested metadata
        metadata_dict = data.get("metadata", {})
        if not isinstance(metadata_dict, dict):
            metadata_dict = {}
            
        metadata = GenerationMetadata(
            agent_id=metadata_dict.get("agent_id", "unknown"),
            agent_name=metadata_dict.get("agent_name", "unknown")
        )
        
        # Extract and convert token counts
        prompt_tokens = int(data.get("prompt_tokens", 0) or 0)
        completion_tokens = int(data.get("completion_tokens", 0) or 0)
        
        return cls(
            id=data.get("id", ""),
            model=data.get("model", ""),
            timestamp=data.get("timestamp", ""),
            latency_ms=int(data.get("latency_ms", 0) or 0),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=float(data.get("cost", 0) or 0),
            metadata=metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the Generation instance to a dictionary."""
        return asdict(self)

# Styling
COLORS = {
    "primary": "#4CAF50",
    "secondary": "#2196F3",
    "success": "#4CAF50",
    "warning": "#FF9800",
    "danger": "#F44336",
    "info": "#2196F3",
    "light": "#F8F9FA",
    "dark": "#343A40",
    "background": "#FFFFFF",
    "success_light": "#E8F5E9",
    "warning_light": "#FFF3E0",
    "danger_light": "#FFEBEE",
    "info_light": "#E3F2FD"
}

# Note: Page configuration is handled in the main streamlit_ui.py file

# Function to check Langfuse availability
def check_langfuse_availability(url, timeout=2):
    """Check if Langfuse is available at the given URL."""
    try:
        # Use verify=False to bypass SSL verification if using self-signed certificates
        response = requests.get(url, timeout=timeout, verify=False)
        return response.status_code < 500
    except Exception:
        return False

# Custom hash function for Langfuse client to avoid unhashable input errors
def _hash_langfuse_client(client):
    """Create a stable hash for Langfuse client objects based on host and key fingerprint.
    
    This ensures caching is predictable and based only on the connection parameters,
    not the entire client object which may contain unhashable components.
    """
    if client is None:
        return None
        
    # Extract just the host and a fingerprint of the public key for stable hashing
    host = os.environ.get("LANGFUSE_HOST", "")
    
    # Create a fingerprint of the public key (first 8 chars) rather than using the full key
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    key_fingerprint = public_key[:8] if len(public_key) >= 8 else public_key
    
    # Return a predictable string hash
    return f"langfuse:{host}:{key_fingerprint}"

# Function to fetch traces from Langfuse
@st.cache_data(
    ttl=300,  # Cache for 5 minutes
    max_entries=20,  # Store up to 20 different query results
    show_spinner=False,  # We'll handle our own spinner
    hash_funcs={Langfuse: _hash_langfuse_client}  # Custom hash function for unhashable Langfuse client
)
def fetch_traces(start_date: datetime, end_date: datetime, agent_ids: List[str] = None, _langfuse_client=None) -> List[Trace]:
    """Fetch traces from Langfuse within the given date range for the specified agents.
    
    Args:
        start_date: The start date for filtering traces
        end_date: The end date for filtering traces
        agent_ids: Optional list of agent IDs to filter by
        _langfuse_client: Langfuse client instance
        
    Returns:
        List of Trace objects with consistent schema
    """
    if not _langfuse_client:
        logger.warning("No Langfuse client provided to fetch_traces")
        return []
    
    try:
        # Convert dates to ISO format with Z suffix (UTC) for proper filtering
        start_time = start_date.isoformat() + "Z"
        end_time = end_date.isoformat() + "Z"
        
        all_traces = []
        page = 1
        has_more = True
        total_count = 0
        
        # Progress tracking
        progress = st.progress(0, text="Fetching traces...")
        
        # Paginate through all results
        while has_more:
            try:
                # Use the SDK's built-in fetch_traces method
                traces_response = _langfuse_client.fetch_traces(
                    page=page,
                    limit=100,  # Smaller batch size for more reliable pagination
                    from_timestamp=start_time,
                    to_timestamp=end_time,
                )
                
                # Add this page's traces to our collection
                all_traces.extend(traces_response.data)
                
                # Log pagination info
                if hasattr(traces_response, 'total'):
                    total_count = traces_response.total
                    logger.info(f"Fetched page {page} of traces. Total available: {total_count}")
                    
                    # Update progress bar
                    total_pages = math.ceil(total_count / 100)
                    progress.progress(min(page / max(total_pages, 1), 1.0), 
                                     text=f"Fetching traces: page {page}/{total_pages}")
                
                # Check if there are more pages
                has_more = hasattr(traces_response, 'has_more') and traces_response.has_more
                if not has_more and page == 1 and len(traces_response.data) == 100:
                    # If we got exactly our limit on page 1, there might be more
                    has_more = True
                
                page += 1
                
                # Calculate max pages based on total count instead of hard-coding
                max_pages = math.ceil(total_count / 100) if total_count > 0 else 10
                if page > max_pages + 1:  # +1 to account for potential has_more edge case
                    st.warning(f"Reached maximum page limit ({max_pages}). Some data may be missing.")
                    logger.warning(f"Reached maximum page limit ({max_pages}). Retrieved {len(all_traces)} of {total_count} total traces.")
                    break
            except Exception as page_error:
                st.error(f"Error fetching traces page {page}: {str(page_error)}")
                logger.error(f"Error fetching traces page {page}: {str(page_error)}")
                break
        
        # Clear progress
        progress.empty()
        
        # Rest of the function remains unchanged
        
        # If we need to filter by agent_ids
        if agent_ids and len(agent_ids) > 0:
            filtered_traces = []
            for trace in all_traces:
                metadata = getattr(trace, 'metadata', {})
                if metadata and hasattr(metadata, 'get'):
                    agent_id = metadata.get("agent_id", None)
                    if agent_id in agent_ids:
                        filtered_traces.append(trace)
                elif isinstance(metadata, dict) and "agent_id" in metadata:
                    if metadata["agent_id"] in agent_ids:
                        filtered_traces.append(trace)
            all_traces = filtered_traces
            logger.info(f"Filtered traces by agent_ids ({len(agent_ids)} agents): {len(all_traces)} traces remaining")
        
        # Convert to Trace objects for type safety and consistent schema
        trace_objects = []
        for trace in all_traces:
            try:
                # Handle different object types (SDK models vs dictionaries)
                if hasattr(trace, 'dict'):
                    trace_dict = trace.dict()
                elif hasattr(trace, '__dict__'):
                    trace_dict = vars(trace)
                else:
                    # Already a dict or similar
                    trace_dict = trace
                
                # Create a Trace object with consistent schema
                trace_object = Trace.from_dict(trace_dict)
                trace_objects.append(trace_object)
            except Exception as convert_error:
                # Only log to console, don't clutter UI with individual record errors
                logger.warning(f"Skipping malformed trace: {str(convert_error)}")
        
        if trace_objects:
            logger.info(f"Successfully processed {len(trace_objects)} traces")
        else:
            logger.info("No traces found or processed")
            
        return trace_objects
    except Exception as e:
        st.error(f"Trace fetch failed: {str(e)}")
        logger.error(f"Trace fetch failed: {str(e)}")
        return []

# This function is now replaced by the Trace.from_dict method in the dataclass

# Function to fetch generations from Langfuse
@st.cache_data(
    ttl=300,  # Cache for 5 minutes
    max_entries=20,  # Store up to 20 different query results
    show_spinner=False,  # We'll handle our own spinner
    hash_funcs={Langfuse: _hash_langfuse_client}  # Custom hash function for unhashable Langfuse client
)
def fetch_generations(start_date: datetime, end_date: datetime, agent_ids: List[str] = None, _langfuse_client=None) -> List[Generation]:
    """Fetch LLM generations from Langfuse within the given date range for the specified agents.
    
    Args:
        start_date: The start date for filtering generations
        end_date: The end date for filtering generations
        agent_ids: Optional list of agent IDs to filter by
        _langfuse_client: Langfuse client instance
        
    Returns:
        List of Generation objects with consistent schema
    """
    if not _langfuse_client:
        logger.warning("No Langfuse client provided to fetch_generations")
        return []
    
    try:
        # Convert dates to ISO format with Z suffix (UTC) for proper filtering
        start_time = start_date.isoformat() + "Z"
        end_time = end_date.isoformat() + "Z"
        
        all_generations = []
        page = 1
        has_more = True
        total_count = 0
        
        # Paginate through all results
        while has_more:
            try:
                # Use the SDK's built-in fetch_observations method
                observations_response = _langfuse_client.fetch_observations(
                    page=page,
                    limit=100,  # Smaller batch size for more reliable pagination
                    from_timestamp=start_time,
                    to_timestamp=end_time,
                    as_type="generation"  # Filter for generations directly in the API call
                )
                
                # Add this page's observations to our collection
                if observations_response.data:
                    all_generations.extend(observations_response.data)
                
                # Log pagination info
                if hasattr(observations_response, 'total'):
                    total_count = observations_response.total
                    logger.info(f"Fetched page {page} of generations. Total available: {total_count}")
                
                # Check if there are more pages
                has_more = hasattr(observations_response, 'has_more') and observations_response.has_more
                if not has_more and page == 1 and len(observations_response.data) == 100:
                    # If we got exactly our limit on page 1, there might be more
                    has_more = True
                
                page += 1
                
                # Safety limit to prevent infinite loops
                if page > 10:  # Limit to 1000 generations (10 pages × 100 per page)
                    st.warning("Reached maximum page limit for generations. Some data may be missing.")
                    logger.warning(f"Reached maximum page limit (10) for generations. Retrieved {len(all_generations)} of {total_count} total generations.")
                    break
                    
            except requests.Timeout as timeout_error:
                st.error(f"Timeout fetching generations page {page}: {str(timeout_error)}")
                logger.error(f"Timeout fetching generations page {page}: {str(timeout_error)}")
                break
            except ValueError as value_error:
                st.error(f"Value error fetching generations page {page}: {str(value_error)}")
                logger.error(f"Value error fetching generations page {page}: {str(value_error)}")
                break
            except Exception as page_error:
                st.error(f"Error fetching generations page {page}: {str(page_error)}")
                logger.error(f"Error fetching generations page {page}: {str(page_error)}")
                break
        
        # If we need to filter by agent_ids
        if agent_ids and len(agent_ids) > 0:
            filtered_generations = []
            for gen in all_generations:
                metadata = getattr(gen, 'metadata', {})
                if metadata and hasattr(metadata, 'get'):
                    agent_id = metadata.get("agent_id", None)
                    if agent_id in agent_ids:
                        filtered_generations.append(gen)
                elif isinstance(metadata, dict) and "agent_id" in metadata:
                    if metadata["agent_id"] in agent_ids:
                        filtered_generations.append(gen)
            all_generations = filtered_generations
            logger.info(f"Filtered generations by agent_ids ({len(agent_ids)} agents): {len(all_generations)} generations remaining")
        
        # Convert to Generation objects for type safety and consistent schema
        generation_objects = []
        for gen in all_generations:
            try:
                # Handle different object types (SDK models vs dictionaries)
                if hasattr(gen, 'dict'):
                    gen_dict = gen.dict()
                elif hasattr(gen, '__dict__'):
                    gen_dict = vars(gen)
                else:
                    # Already a dict or similar
                    gen_dict = gen
                
                # Create a Generation object with consistent schema
                generation_object = Generation.from_dict(gen_dict)
                generation_objects.append(generation_object)
            except Exception as convert_error:
                # Only log to console, don't clutter UI with individual record errors
                logger.warning(f"Skipping malformed generation: {str(convert_error)}")
        
        if generation_objects:
            logger.info(f"Successfully processed {len(generation_objects)} generations")
        else:
            logger.info("No generations found or processed")
            
        return generation_objects
    except Exception as e:
        st.error(f"Generation fetch failed: {str(e)}")
        logger.error(f"Generation fetch failed: {str(e)}")
        return []

# This function is now replaced by the Generation.from_dict method in the dataclass

# We've removed the test_langfuse_connection function since we know the connection works

# Cache the Langfuse client to prevent redundant initialization
@st.cache_resource(
    ttl=3600,  # Cache for 1 hour
    show_spinner=False,  # We'll handle our own spinner
    hash_funcs={Langfuse: _hash_langfuse_client}  # Restore the hash function for Langfuse client
)
def get_langfuse_client(public_key: str, secret_key: str, host: str) -> Optional[Langfuse]:
    """Create and cache a Langfuse client instance."""
    if not LANGFUSE_AVAILABLE:
        logger.warning("Langfuse package is not available")
        return None
        
    if not public_key or not secret_key:
        logger.warning("Missing Langfuse API keys")
        return None
        
    try:
        # Set environment variables for the Langfuse SDK to use
        os.environ["LANGFUSE_HOST"] = host
        os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
        os.environ["LANGFUSE_SECRET_KEY"] = secret_key
        
        # Create the client - the SDK will read from environment variables
        client = Langfuse(
            public_key=public_key,  # Explicitly pass keys instead of relying on env vars
            secret_key=secret_key,
            host=host
        )
        
        # Log detailed connection info
        logger.info(f"Attempting to connect to Langfuse at {host}")
        
        # Verify connection by making a simple API call
        test_response = client.fetch_traces(page=1, limit=1)
        if hasattr(test_response, 'data'):
            logger.info(f"Successfully connected to Langfuse at {host}")
            return client
        else:
            logger.error("Langfuse API response format unexpected")
            return None
    except Exception as e:
        # Log the full error details for debugging
        import traceback
        logger.error(f"Failed to initialize Langfuse client: {str(e)}")
        logger.error(traceback.format_exc())
        return None

# Function to load and process data
def load_data(langfuse_client, start_date: datetime, end_date: datetime, selected_agents: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load and process data from Langfuse.
    
    Args:
        langfuse_client: Langfuse client instance
        start_date: Start date for filtering data
        end_date: End date for filtering data
        selected_agents: List of agent IDs to filter by
        
    Returns:
        Tuple of (trace_df, generation_df) pandas DataFrames
    """
    if not langfuse_client:
        logger.warning("No Langfuse client provided to load_data")
        return pd.DataFrame(), pd.DataFrame()
    
    trace_df = pd.DataFrame()
    generation_df = pd.DataFrame()
    
    # Create a progress container to show overall progress
    progress_container = st.empty()
    progress_container.info("Starting data fetch from Langfuse...")
    
    with st.spinner("Fetching traces from Langfuse..."):
        try:
            traces = fetch_traces(start_date, end_date, selected_agents, _langfuse_client=langfuse_client)
            if traces:
                progress_container.success(f"Successfully fetched {len(traces)} traces and processing...")
            else:
                progress_container.info("No traces found for the selected time range and agents")
        except Exception as e:
            st.error(f"Error fetching traces from Langfuse: {str(e)}")
            logger.error(f"Error in load_data fetching traces: {str(e)}")
            traces = []
    
    with st.spinner("Fetching generations from Langfuse..."):
        try:
            generations = fetch_generations(start_date, end_date, selected_agents, _langfuse_client=langfuse_client)
            if generations:
                progress_container.success(f"Successfully fetched {len(generations)} generations and processing...")
            else:
                progress_container.info("No generations found for the selected time range and agents")
        except Exception as e:
            st.error(f"Error fetching generations from Langfuse: {str(e)}")
            logger.error(f"Error in load_data fetching generations: {str(e)}")
            generations = []
    
    # If no data is available
    if not traces and not generations:
        progress_container.warning("No data available for the selected filters")
        return pd.DataFrame(), pd.DataFrame()
    
    # Process trace data using the dataclass objects
    if traces:
        with st.spinner("Processing trace data..."):
            # Convert Trace objects to dictionaries for DataFrame
            trace_data = [trace.to_dict() for trace in traces]
            
            # Create DataFrame with consistent column structure
            trace_df = pd.DataFrame(trace_data)
            
            # Extract metadata fields to top level for easier analysis
            if not trace_df.empty and "metadata" in trace_df.columns:
                try:
                    # Expand metadata into separate columns
                    for trace in traces:
                        trace_df.loc[trace_df["id"] == trace.id, "agent_id"] = trace.metadata.agent_id
                        trace_df.loc[trace_df["id"] == trace.id, "agent_name"] = trace.metadata.agent_name
                        # Also extract parent relationship fields
                        trace_df.loc[trace_df["id"] == trace.id, "parent_span_id"] = trace.metadata.parent_span_id
                        trace_df.loc[trace_df["id"] == trace.id, "parent_trace_id"] = trace.metadata.parent_trace_id
                except Exception as e:
                    logger.warning(f"Could not expand trace metadata: {e}")
            
            # Convert timestamp to datetime for better sorting and filtering
            if not trace_df.empty and "timestamp" in trace_df.columns:
                try:
                    # Convert to datetime in UTC, properly handling timezone
                    trace_df["timestamp"] = pd.to_datetime(trace_df["timestamp"], utc=True)
                    
                    # Add a local_timestamp column with user's timezone
                    local_tz = datetime.now().astimezone().tzinfo
                    trace_df["local_timestamp"] = trace_df["timestamp"].dt.tz_convert(local_tz)
                    
                    # Format for display
                    trace_df["timestamp_display"] = trace_df["local_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.warning(f"Could not convert trace timestamps to datetime: {e}")
                    # Only log to console, don't clutter UI
                    if "timestamp_display" not in trace_df.columns:
                        trace_df["timestamp_display"] = trace_df["timestamp"]
            
            # Apply sampling for very large dataframes to improve performance
            if len(trace_df) > 50000:
                trace_df.sample_original = trace_df.copy()
                trace_df = trace_df.sample(n=50000, random_state=42)
                st.warning(f"Large dataset detected! Showing a sample of 50,000 traces from {len(trace_df.sample_original)} total.")
    
    # Process generation data using the dataclass objects
    if generations:
        with st.spinner("Processing generation data..."):
            # Convert Generation objects to dictionaries for DataFrame
            generation_data = [gen.to_dict() for gen in generations]
            
            # Create DataFrame with consistent column structure
            generation_df = pd.DataFrame(generation_data)
            
            # Extract metadata fields to top level for easier analysis
            if not generation_df.empty and "metadata" in generation_df.columns:
                try:
                    # Expand metadata into separate columns
                    for gen in generations:
                        generation_df.loc[generation_df["id"] == gen.id, "agent_id"] = gen.metadata.agent_id
                        generation_df.loc[generation_df["id"] == gen.id, "agent_name"] = gen.metadata.agent_name
                except Exception as e:
                    logger.warning(f"Could not expand generation metadata: {e}")
            
            # Convert timestamp to datetime for better sorting and filtering
            if not generation_df.empty and "timestamp" in generation_df.columns:
                try:
                    # Convert to datetime in UTC
                    generation_df["timestamp"] = pd.to_datetime(generation_df["timestamp"])
                    
                    # Add a local_timestamp column with user's timezone
                    local_tz = datetime.now().astimezone().tzinfo
                    generation_df["local_timestamp"] = generation_df["timestamp"].dt.tz_localize("UTC").dt.tz_convert(local_tz)
                    
                    # Format for display
                    generation_df["timestamp_display"] = generation_df["local_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    logger.warning(f"Could not convert generation timestamps to datetime: {e}")
                    # Only log to console, don't clutter UI
                    if "timestamp_display" not in generation_df.columns:
                        generation_df["timestamp_display"] = generation_df["timestamp"]
    
    # Clear the progress container when done
    progress_container.empty()
    
    # Log summary of processed data
    logger.info(f"Processed data: {len(trace_df)} traces, {len(generation_df)} generations")
    
    return trace_df, generation_df

def agent_insights_tab():
    """Main entry point for the Agent Insights tab in the Streamlit UI."""
    # Add a minimal sidebar for status information
    with st.sidebar:
        # Add a spacer at the bottom of the sidebar
        st.markdown("<br>" * 5, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("### Connection Status")
        sidebar_status = st.empty()
    
    # Configuration section in the main area
    with st.expander("Dashboard Filters", expanded=False):
        # Create a 3-column layout for configuration options
        config_col1, config_col2, config_col3 = st.columns([1, 1, 1])
        
        # Use system-wide Langfuse configuration
        langfuse_host = os.environ.get("LANGFUSE_HOST", "http://10.147.20.5:8002")
        langfuse_public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        langfuse_secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
        
        # Column 1: Time Range
        with config_col1:
            st.subheader("Time Range")
            time_range = st.selectbox(
                label="Select Time Range",
                options=["Last Hour", "Last 24 Hours", "Last 7 Days", "Last 30 Days", "Custom"],
                index=1,  # Default to Last 24 Hours
                key="time_range_selector",
                help="Choose the time period for data analysis"
            )
            
            if time_range == "Custom":
                default_start = (datetime.now() - timedelta(days=7)).date()
                default_end = datetime.now().date()
                
                start_date_val = st.date_input(
                    label="Start Date", 
                    value=default_start,
                    key="custom_start_date",
                    help="Select the starting date for data analysis"
                )
                end_date_val = st.date_input(
                    label="End Date", 
                    value=default_end,
                    key="custom_end_date",
                    help="Select the ending date for data analysis"
                )
                # Convert date objects to datetime objects
                start_date = datetime.combine(start_date_val, datetime.min.time())
                end_date = datetime.combine(end_date_val, datetime.max.time())
                
                # Validate date range
                if end_date < start_date:
                    st.error("End date must be on or after the start date.")
            else:
                # Calculate start and end dates based on selection
                end_date = datetime.now()
                if time_range == "Last Hour":
                    start_date = end_date - timedelta(hours=1)
                elif time_range == "Last 24 Hours":
                    start_date = end_date - timedelta(days=1)
                elif time_range == "Last 7 Days":
                    start_date = end_date - timedelta(days=7)
                else:  # Last 30 Days
                    start_date = end_date - timedelta(days=30)
        
        # Column 2: Agent Filter
        with config_col2:
            st.subheader("Agent Filter")
            agents = discover_agents(test_health=False)
            agent_ids = list(agents.keys())
            
            if not agents:
                st.warning("No agents found. Make sure your discovery service is running.")
                selected_agents = []
            else:
                selected_agents = st.multiselect(
                    label="Select Agents to Monitor",
                    options=agent_ids,
                    default=agent_ids[:5] if len(agent_ids) > 5 else agent_ids,
                    key="agent_selector",
                    help="Choose which agents to include in the analysis"
                )
        
        # Column 3: Refresh Settings
        with config_col3:
            st.subheader("Refresh Settings")
            auto_refresh = st.checkbox(
                label="Auto Refresh", 
                value=False,
                key="auto_refresh_toggle",
                help="Enable automatic refresh of the dashboard"
            )
            if auto_refresh:
                refresh_interval = st.slider(
                    label="Refresh Interval (seconds)",
                    min_value=5,
                    max_value=300,
                    value=30,
                    step=5,
                    key="refresh_interval_slider",
                    help="Set how frequently the dashboard should refresh"
                )
            
            # Langfuse API Keys (if not set in environment)
            if not langfuse_public_key or not langfuse_secret_key:
                st.subheader("Langfuse API Keys")
                st.info("API keys not set in environment variables")
                langfuse_public_key = st.text_input(
                    "Public Key", 
                    value=langfuse_public_key,
                    type="password",
                    help="Enter your Langfuse public API key"
                )
                langfuse_secret_key = st.text_input(
                    "Secret Key", 
                    value=langfuse_secret_key,
                    type="password",
                    help="Enter your Langfuse secret API key"
                )
                st.markdown(f"[Open Langfuse Dashboard]({langfuse_host})")
    
    # Create tabs for different views
    tab_overview, tab_agents, tab_interactions, tab_performance, tab_traces = st.tabs([
        "Overview", "Agent Activity", "Agent Interactions", "Performance Metrics", "Raw Traces"
    ])
    
    # Initialize Langfuse client using the cached client function
    langfuse_client = None
    status_container = st.empty()
    if LANGFUSE_AVAILABLE:
        try:
            # Show that we're connecting
            with st.spinner("Connecting to Langfuse..."):
                # Use the cached client function to get or create a client
                langfuse_client = get_langfuse_client(
                    public_key=langfuse_public_key,
                    secret_key=langfuse_secret_key,
                    host=langfuse_host
                )
                
                if langfuse_client:
                    # Show success message in the main content area
                    status_container.success("✅ Connected to Langfuse")
                    # Also show success in the sidebar
                    sidebar_status.success(f"✅ Connected to Langfuse\n{langfuse_host}")
                    logger.info(f"Successfully connected to Langfuse at {langfuse_host}")
                else:
                    raise Exception("Failed to initialize Langfuse client - client is None")
        except Exception as e:
            # Show error message in the main content area with detailed information
            full_error = f"Could not connect to Langfuse: {str(e)}"
            status_container.error(full_error)
            # Also show error in the sidebar
            sidebar_status.error("❌ Langfuse connection failed")
            logger.error(f"Langfuse connection failed: {str(e)}")
            
            # Add a debug button to show detailed error info
            if st.button("Show Debug Info"):
                import traceback
                st.code(traceback.format_exc())
                st.json({
                    "host": langfuse_host,
                    "public_key_length": len(langfuse_public_key) if langfuse_public_key else 0,
                    "secret_key_length": len(langfuse_secret_key) if langfuse_secret_key else 0,
                    "langfuse_available": LANGFUSE_AVAILABLE
                })
            
            langfuse_client = None
    
    # Auto-refresh logic
    if auto_refresh:
        refresh_placeholder = st.empty()
        with refresh_placeholder.container():
            st.info(f"Auto-refreshing every {refresh_interval} seconds")
        
        if "last_refresh" not in st.session_state:
            st.session_state.last_refresh = datetime.now()
        
        if (datetime.now() - st.session_state.last_refresh).total_seconds() >= refresh_interval:
            st.session_state.last_refresh = datetime.now()
            st.rerun()
    
    # Load and process data
    trace_df, generation_df = load_data(langfuse_client, start_date, end_date, selected_agents)
    
    # Display date range below the status message
    status_container.markdown(f"Data from {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")
    
    # Add a small divider
    st.divider()
    
    # Only show warnings if there's no data
    if trace_df.empty and generation_df.empty:
        # If no data is available, show a helpful message
        for tab in [tab_overview, tab_agents, tab_interactions, tab_performance, tab_traces]:
            with tab:
                st.info("No data available for the selected time range and agents. Try adjusting the filters in the sidebar.")
                st.markdown("If you're expecting data, make sure your agents are properly configured to send telemetry to Langfuse.")
    else:
        # Render each tab using the helper functions
        render_overview_tab(tab_overview, trace_df, generation_df, selected_agents)
        render_agent_activity_tab(tab_agents, trace_df, generation_df, selected_agents)
        render_agent_interactions_tab(tab_interactions, trace_df, generation_df, selected_agents)
        render_performance_tab(tab_performance, trace_df, generation_df, selected_agents)
        render_raw_traces_tab(tab_traces, trace_df, generation_df)
    
    # Last updated time
    st.text(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# Helper functions for rendering different tabs

def render_overview_tab(tab, trace_df, generation_df, selected_agents):
    """Render the Overview tab with summary metrics and charts.
    
    Args:
        tab: The Streamlit tab object
        trace_df: DataFrame containing trace data
        generation_df: DataFrame containing generation data
        selected_agents: List of selected agent IDs
    """
    with tab:
        st.subheader("System Overview")
        
        # Create metrics row
        metric_cols = st.columns(4)
        
        # Calculate metrics
        total_traces = len(trace_df) if not trace_df.empty else 0
        total_generations = len(generation_df) if not generation_df.empty else 0
        unique_agents = len(trace_df['agent_id'].unique()) if not trace_df.empty else 0
        avg_latency = trace_df['latency_ms'].mean() if not trace_df.empty else 0
        
        # Display metrics
        with metric_cols[0]:
            st.metric("Total Traces", total_traces)
        
        with metric_cols[1]:
            st.metric("Total Generations", total_generations)
        
        with metric_cols[2]:
            st.metric("Active Agents", unique_agents)
        
        with metric_cols[3]:
            st.metric("Avg Latency (ms)", f"{avg_latency:.2f}")
        
        # Create charts row
        if not trace_df.empty:
            st.subheader("Activity Timeline")
            
            # Group traces by timestamp (hourly)
            if 'timestamp' in trace_df.columns:
                try:
                    # Resample to hourly buckets
                    trace_df['hour'] = trace_df['timestamp'].dt.floor('H')
                    hourly_counts = trace_df.groupby('hour').size().reset_index(name='count')
                    
                    # Create a line chart
                    fig = px.line(
                        hourly_counts, 
                        x='hour', 
                        y='count',
                        title="Hourly Trace Activity",
                        labels={"hour": "Time", "count": "Number of Traces"}
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    logger.error(f"Error creating activity timeline: {str(e)}")
                    st.error("Could not create activity timeline.")
        
        # Token usage if generation data is available
        if not generation_df.empty:
            st.subheader("Token Usage")
            
            # Calculate total tokens by model
            if 'model' in generation_df.columns and 'total_tokens' in generation_df.columns:
                try:
                    model_tokens = generation_df.groupby('model')['total_tokens'].sum().reset_index()
                    
                    # Create a bar chart
                    fig = px.bar(
                        model_tokens,
                        x='model',
                        y='total_tokens',
                        title="Token Usage by Model",
                        labels={"model": "Model", "total_tokens": "Total Tokens"}
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    logger.error(f"Error creating token usage chart: {str(e)}")
                    st.error("Could not create token usage chart.")

def render_agent_activity_tab(tab, trace_df, generation_df, selected_agents):
    """Render the Agent Activity tab with agent-specific metrics and charts.
    
    Args:
        tab: The Streamlit tab object
        trace_df: DataFrame containing trace data
        generation_df: DataFrame containing generation data
        selected_agents: List of selected agent IDs
    """
    with tab:
        st.subheader("Agent Activity")
        
        if not trace_df.empty and 'agent_id' in trace_df.columns:
            # Agent selector for detailed view
            if len(selected_agents) > 0:
                agent_for_details = st.selectbox(
                    "Select an agent for detailed view",
                    options=selected_agents,
                    key="agent_details_selector"
                )
                
                # Filter data for the selected agent
                agent_traces = trace_df[trace_df['agent_id'] == agent_for_details]
                agent_generations = generation_df[generation_df['agent_id'] == agent_for_details] if not generation_df.empty else pd.DataFrame()
                
                # Display agent metrics
                metric_cols = st.columns(4)
                
                with metric_cols[0]:
                    st.metric("Total Traces", len(agent_traces))
                
                with metric_cols[1]:
                    st.metric("Total Generations", len(agent_generations) if not agent_generations.empty else 0)
                
                with metric_cols[2]:
                    avg_latency = agent_traces['latency_ms'].mean() if not agent_traces.empty else 0
                    st.metric("Avg Latency (ms)", f"{avg_latency:.2f}")
                
                with metric_cols[3]:
                    total_tokens = agent_generations['total_tokens'].sum() if not agent_generations.empty and 'total_tokens' in agent_generations.columns else 0
                    st.metric("Total Tokens", total_tokens)
                
                # Activity timeline for the agent
                if not agent_traces.empty and 'timestamp' in agent_traces.columns:
                    st.subheader(f"Activity Timeline for {agent_for_details}")
                    
                    try:
                        # Resample to hourly buckets
                        agent_traces['hour'] = agent_traces['timestamp'].dt.floor('H')
                        hourly_counts = agent_traces.groupby('hour').size().reset_index(name='count')
                        
                        # Create a line chart
                        fig = px.line(
                            hourly_counts, 
                            x='hour', 
                            y='count',
                            title=f"Hourly Activity for {agent_for_details}",
                            labels={"hour": "Time", "count": "Number of Traces"}
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        logger.error(f"Error creating agent activity timeline: {str(e)}")
                        st.error("Could not create agent activity timeline.")
            else:
                st.info("Please select at least one agent in the dashboard filters.")
        else:
            st.info("No agent activity data available.")

def render_performance_tab(tab, trace_df, generation_df, selected_agents):
    """Render the Performance Metrics tab with latency and cost analysis.
    
    Args:
        tab: The Streamlit tab object
        trace_df: DataFrame containing trace data
        generation_df: DataFrame containing generation data
        selected_agents: List of selected agent IDs
    """
    with tab:
        st.subheader("Performance Metrics")
        
        # Create tabs for different performance views
        perf_tab_latency, perf_tab_tokens, perf_tab_cost = st.tabs(["Latency", "Token Usage", "Cost Analysis"])
        
        # Latency Analysis
        with perf_tab_latency:
            if not trace_df.empty and 'latency_ms' in trace_df.columns and 'agent_id' in trace_df.columns:
                st.subheader("Latency Distribution")
                
                try:
                    # Create a box plot of latencies by agent
                    fig = px.box(
                        trace_df,
                        x='agent_id',
                        y='latency_ms',
                        title="Latency Distribution by Agent",
                        labels={"agent_id": "Agent", "latency_ms": "Latency (ms)"}
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Show latency statistics
                    st.subheader("Latency Statistics")
                    latency_stats = trace_df.groupby('agent_id')['latency_ms'].agg(['mean', 'median', 'min', 'max']).reset_index()
                    latency_stats = latency_stats.round(2)
                    st.dataframe(latency_stats, use_container_width=True)
                except Exception as e:
                    logger.error(f"Error creating latency distribution: {str(e)}")
                    st.error("Could not create latency distribution.")
            else:
                st.info("No latency data available.")
        
        # Token Usage Analysis
        with perf_tab_tokens:
            if not generation_df.empty and 'prompt_tokens' in generation_df.columns and 'completion_tokens' in generation_df.columns:
                st.subheader("Token Usage Analysis")
                
                try:
                    # Group by agent and calculate token statistics
                    token_stats = generation_df.groupby('agent_id').agg({
                        'prompt_tokens': 'sum',
                        'completion_tokens': 'sum',
                        'total_tokens': 'sum'
                    }).reset_index()
                    
                    # Create a stacked bar chart
                    token_data = []
                    for _, row in token_stats.iterrows():
                        token_data.append({
                            'agent_id': row['agent_id'],
                            'token_type': 'Prompt',
                            'tokens': row['prompt_tokens']
                        })
                        token_data.append({
                            'agent_id': row['agent_id'],
                            'token_type': 'Completion',
                            'tokens': row['completion_tokens']
                        })
                    
                    token_df = pd.DataFrame(token_data)
                    
                    fig = px.bar(
                        token_df,
                        x='agent_id',
                        y='tokens',
                        color='token_type',
                        title="Token Usage by Agent",
                        labels={"agent_id": "Agent", "tokens": "Token Count", "token_type": "Token Type"}
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Show token statistics
                    st.subheader("Token Usage Statistics")
                    st.dataframe(token_stats, use_container_width=True)
                except Exception as e:
                    logger.error(f"Error creating token usage analysis: {str(e)}")
                    st.error("Could not create token usage analysis.")
            else:
                st.info("No token usage data available.")
        
        # Cost Analysis
        with perf_tab_cost:
            if not generation_df.empty and 'cost' in generation_df.columns:
                st.subheader("Cost Analysis")
                
                try:
                    # Group by agent and calculate cost statistics
                    cost_stats = generation_df.groupby('agent_id')['cost'].agg(['sum', 'mean']).reset_index()
                    cost_stats = cost_stats.round(4)
                    
                    # Create a bar chart of total cost by agent
                    fig = px.bar(
                        cost_stats,
                        x='agent_id',
                        y='sum',
                        title="Total Cost by Agent",
                        labels={"agent_id": "Agent", "sum": "Total Cost ($)"}
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Show cost statistics
                    st.subheader("Cost Statistics")
                    st.dataframe(cost_stats.rename(columns={'sum': 'total_cost', 'mean': 'avg_cost'}), use_container_width=True)
                except Exception as e:
                    logger.error(f"Error creating cost analysis: {str(e)}")
                    st.error("Could not create cost analysis.")
            else:
                st.info("No cost data available.")

def filter_table(df, title, key_prefix):
    """Generic helper to filter and display a table with search and column filters.
    
    Args:
        df: DataFrame to filter and display
        title: Title to display above the table
        key_prefix: Prefix for Streamlit widget keys to ensure uniqueness
        
    Returns:
        Filtered DataFrame
    """
    if df.empty:
        st.info(f"No {title.lower()} data available.")
        return df
    
    st.subheader(title)
    
    # Create filter controls
    filter_container = st.container()
    with filter_container:
        # Create a row for filters
        filter_cols = st.columns([1, 1, 1])
        
        # Text search filter
        with filter_cols[0]:
            search_term = st.text_input(f"Search {title}", key=f"{key_prefix}_search")
        
        # Column filter
        with filter_cols[1]:
            # Select columns that are strings or could be searched
            searchable_cols = [col for col in df.columns if df[col].dtype == 'object' or 'id' in col.lower() or 'name' in col.lower()]
            if searchable_cols:
                search_column = st.selectbox(
                    "Search Column",
                    options=["All Columns"] + searchable_cols,
                    key=f"{key_prefix}_column"
                )
            else:
                search_column = "All Columns"
        
        # Row limit
        with filter_cols[2]:
            row_limit = st.number_input(
                "Max Rows",
                min_value=10,
                max_value=1000,
                value=100,
                step=10,
                key=f"{key_prefix}_limit"
            )
    
    # Apply filters
    filtered_df = df.copy()
    
    # Apply text search if provided
    if search_term:
        if search_column == "All Columns":
            # Search across all string columns
            mask = pd.Series(False, index=filtered_df.index)
            for col in searchable_cols:
                # Convert column to string and search
                mask = mask | filtered_df[col].astype(str).str.contains(search_term, case=False, na=False)
            filtered_df = filtered_df[mask]
        else:
            # Search in the specific column
            filtered_df = filtered_df[filtered_df[search_column].astype(str).str.contains(search_term, case=False, na=False)]
    
    # Apply row limit
    if len(filtered_df) > row_limit:
        st.info(f"Showing {row_limit} of {len(filtered_df)} rows. Use search to narrow results.")
        filtered_df = filtered_df.head(row_limit)
    
    # Display the filtered dataframe
    st.dataframe(filtered_df, use_container_width=True)
    
    return filtered_df

def render_raw_traces_tab(tab, trace_df, generation_df):
    """Render the Raw Traces tab with filterable tables of trace and generation data.
    
    Args:
        tab: The Streamlit tab object
        trace_df: DataFrame containing trace data
        generation_df: DataFrame containing generation data
    """
    with tab:
        st.subheader("Raw Data Explorer")
        
        # Create tabs for traces and generations
        raw_tab_traces, raw_tab_generations = st.tabs(["Traces", "Generations"])
        
        # Traces table
        with raw_tab_traces:
            filter_table(trace_df, "Traces", "traces")
        
        # Generations table
        with raw_tab_generations:
            filter_table(generation_df, "Generations", "generations")

def render_agent_interactions_tab(tab, trace_df, generation_df, selected_agents):
    """Render the Agent Interactions tab with visualizations of agent communication patterns.
    
    Args:
        tab: The Streamlit tab object
        trace_df: DataFrame containing trace data
        generation_df: DataFrame containing generation data
        selected_agents: List of selected agent IDs
    """
    with tab:
        st.subheader("Agent Interactions")
        
        st.markdown("""
        This view shows how agents communicate with each other. Each node represents an agent, 
        and each edge represents communication between agents.
        """)
        
        # Check if we have trace data with parent-child relationships
        if not trace_df.empty and len(selected_agents) > 1:
            try:
                # Extract parent-child relationships
                interactions = []
                
                # Check if we have the required columns for building interactions
                has_parent_trace_ids = "parent_trace_id" in trace_df.columns
                
                if not has_parent_trace_ids:
                    st.warning("No parent-child relationship data found in traces. "
                               "Make sure your agents are configured to log parent trace IDs.")
                else:
                    # Only process traces with parent trace IDs
                    parent_child_traces = trace_df[trace_df["parent_trace_id"].notnull()]
                    
                    if parent_child_traces.empty:
                        st.info("No parent-child relationships found between agents.")
                    else:
                        for _, trace in parent_child_traces.iterrows():
                            # Get the current agent - use expanded columns instead of metadata
                            agent_id = trace["agent_id"]
                            agent_name = trace["agent_name"]
                            parent_trace_id = trace["parent_trace_id"]
                            
                            # Find parent trace
                            parent_trace = trace_df[trace_df["id"] == parent_trace_id]
                            
                            if not parent_trace.empty:
                                parent_agent_id = parent_trace.iloc[0]["agent_id"]
                                parent_agent_name = parent_trace.iloc[0]["agent_name"]
                                
                                # Record interaction
                                interactions.append({
                                    "source_agent": parent_agent_id,
                                    "source_name": parent_agent_name,
                                    "target_agent": agent_id,
                                    "target_name": agent_name,
                                    "trace_id": trace["id"]
                                })
                        
                        # The rest of the code to visualize interactions remains mostly the same
                        # Create interaction dataframe
                        interaction_df = pd.DataFrame(interactions)
                
                        if len(interaction_df) > 0:
                            st.subheader("Agent Interaction Matrix")
                            
                            # Count interactions between agents
                            interaction_counts = interaction_df.groupby(['source_agent', 'target_agent']).size().reset_index(name='count')
                            
                            # Create interaction matrix
                            unique_agents = pd.concat([interaction_df['source_agent'], interaction_df['target_agent']]).unique()
                            interaction_matrix = pd.pivot_table(
                                interaction_counts,
                                values='count',
                                index='source_agent',
                                columns='target_agent',
                                fill_value=0
                            )
                            
                            # Fill in missing agents
                            for agent in unique_agents:
                                if agent not in interaction_matrix.index:
                                    interaction_matrix.loc[agent] = 0
                                if agent not in interaction_matrix.columns:
                                    interaction_matrix[agent] = 0
                            
                            # Display the interaction matrix
                            fig = px.imshow(
                                interaction_matrix,
                                labels=dict(x="Target Agent", y="Source Agent", color="Interactions"),
                                x=interaction_matrix.columns,
                                y=interaction_matrix.index,
                                color_continuous_scale="Viridis"
                            )
                            fig.update_layout(height=600)
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Create a network graph of agent interactions
                            st.subheader("Agent Interaction Network")
                            
                            # Prepare nodes and edges for the network graph
                            unique_agents = pd.concat([interaction_df['source_agent'], interaction_df['target_agent']]).unique()
                            
                            # Create edges with weights
                            edge_x = []
                            edge_y = []
                            edge_traces = []
                            
                            # Position nodes in a circle
                            radius = 1
                            node_positions = {}
                            for i, agent in enumerate(unique_agents):
                                angle = 2 * math.pi * i / len(unique_agents)
                                x = radius * math.cos(angle)
                                y = radius * math.sin(angle)
                                node_positions[agent] = (x, y)
                            
                            # Create edges
                            for _, row in interaction_counts.iterrows():
                                source = row['source_agent']
                                target = row['target_agent']
                                weight = row['count']
                                
                                x0, y0 = node_positions[source]
                                x1, y1 = node_positions[target]
                                
                                edge_trace = go.Scatter(
                                    x=[x0, x1, None],
                                    y=[y0, y1, None],
                                    line=dict(width=weight, color='#888'),
                                    hoverinfo='text',
                                    text=f"{source} → {target}: {weight} interactions",
                                    mode='lines'
                                )
                                edge_traces.append(edge_trace)
                            
                            # Create nodes
                            node_x = []
                            node_y = []
                            node_text = []
                            
                            for agent in unique_agents:
                                x, y = node_positions[agent]
                                node_x.append(x)
                                node_y.append(y)
                                
                                # Count incoming and outgoing interactions
                                incoming = interaction_counts[interaction_counts['target_agent'] == agent]['count'].sum()
                                outgoing = interaction_counts[interaction_counts['source_agent'] == agent]['count'].sum()
                                
                                node_text.append(f"Agent: {agent}<br>Incoming: {incoming}<br>Outgoing: {outgoing}")
                            
                            node_trace = go.Scatter(
                                x=node_x, y=node_y,
                                mode='markers+text',
                                text=unique_agents,
                                textposition="top center",
                                hoverinfo='text',
                                hovertext=node_text,
                                marker=dict(
                                    showscale=True,
                                    colorscale='YlGnBu',
                                    size=20,
                                    colorbar=dict(
                                        thickness=15,
                                        title='Node Connections',
                                        xanchor='left',
                                        titleside='right'
                                    ),
                                    line_width=2
                                )
                            )
                            
                            # Create the figure
                            fig = go.Figure(data=edge_traces + [node_trace],
                                            layout=go.Layout(
                                                title='Agent Interaction Network',
                                                titlefont_size=16,
                                                showlegend=False,
                                                hovermode='closest',
                                                margin=dict(b=20,l=5,r=5,t=40),
                                                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
                                            )
                                           )
                            
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No agent interactions found in the data. This could be because the traces don't have parent-child relationships recorded.")
            except Exception as e:
                logger.error(f"Error processing agent interactions: {str(e)}")
                st.error("Error processing agent interactions. See logs for details.")
        else:
            st.info("No trace data available or metadata missing. Select agents and a time range to see interaction data.")
            
            # Show a placeholder if no real data is available
            if len(selected_agents) > 1:
                st.subheader("Sample Interaction Visualization")
                # Create a dummy interaction matrix
                interaction_matrix = np.random.randint(0, 10, size=(len(selected_agents), len(selected_agents)))
                np.fill_diagonal(interaction_matrix, 0)  # No self-interactions
                
                # Create a heatmap
                fig = px.imshow(
                    interaction_matrix,
                    x=selected_agents,
                    y=selected_agents,
                    color_continuous_scale="Viridis",
                    title="Example Agent Interaction Heatmap (Sample Data)"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                st.info("Note: This is sample data for demonstration purposes only.")
            else:
                st.info("Select multiple agents to see their interaction patterns.")

# The function will be called by streamlit_ui.py when the Agent Insights tab is selected
# Do not call it directly here