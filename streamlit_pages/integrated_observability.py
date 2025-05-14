"""
Integrated Observability Dashboard for MCP Army

This dashboard provides a comprehensive view of agent performance, federated learning progress, 
and system health metrics all in one unified interface.
"""
import os
import time
import json
import datetime
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
from urllib.parse import urljoin
from typing import Dict, List, Any, Optional, Tuple
import logging

# Add parent directory to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import custom modules
from archon.resilient_discovery import ResilientDiscovery
from archon.federated_learning import get_all_stats, get_agent_stats

# Try to import Langfuse for tracing visualization
try:
    from langfuse.client import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

# Note: Page configuration is handled in the main streamlit_ui.py file
# The following was removed to avoid conflicts:
# st.set_page_config(
#     page_title="MCP Army Observability", 
#     page_icon="📈",
#     layout="wide",
#     initial_sidebar_state="expanded"
# )

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize discovery system
discovery = ResilientDiscovery()

# Define constants
REFRESH_INTERVAL = 60  # seconds
LANGFUSE_URL = "http://localhost:3000"

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: rgba(49, 51, 63, 0.1);
        border-radius: 0.5rem;
        padding: 1rem;
        text-align: center;
    }
    .big-number {
        font-size: 2.5rem;
        font-weight: bold;
        margin: 0.5rem 0;
    }
    .sub-number {
        font-size: 1rem;
        color: #808495;
    }
    .dashboard-title {
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: rgba(28, 131, 225, 0.1);
        border-radius: 5px 5px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(28, 131, 225, 0.2);
        border-bottom: 2px solid rgb(28, 131, 225);
    }
    iframe {
        width: 100%;
        height: 700px;
        border: none;
    }
    .chart-container {
        background-color: white;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    .highlight-card {
        border-left: 4px solid rgb(28, 131, 225);
        padding-left: 1rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# Helper Functions

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_agent_data():
    """Fetch information about all agents"""
    try:
        agents = discovery.discover_agents(force_refresh=True)
        return agents
    except Exception as e:
        logger.error(f"Error fetching agent data: {e}")
        return {}

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_agent_performance():
    """Fetch performance metrics for all agents"""
    try:
        return get_all_stats()
    except Exception as e:
        logger.error(f"Error fetching agent performance: {e}")
        return {}

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_system_metrics():
    """Fetch system-wide performance metrics"""
    # This would ideally connect to a metrics database or service
    # For now, we'll return simulated data
    return {
        "agent_count": 5,
        "total_requests": 1243,
        "success_rate": 0.97,
        "avg_response_time": 428,  # ms
        "cpu_usage": 34,  # percent
        "memory_usage": 2.7,  # GB
        "uptime": 86400 * 3 + 14400,  # 3 days, 4 hours in seconds
        "error_count": 37
    }

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_federation_metrics():
    """Fetch metrics about federated learning"""
    # This would ideally pull from the federated learning service
    # For now, we'll return simulated data
    return {
        "total_contributions": 1578,
        "unique_contributors": 5,
        "knowledge_types": {
            "embedding": 1203,
            "weights": 287,
            "logits": 88
        },
        "quality_scores": {
            "browser-use": 0.92,
            "hallno": 0.88,
            "docker-sandbox": 0.76,
            "lightrag": 0.95,
            "data-analyzer": 0.81
        },
        "improvement_rate": 0.12  # 12% performance improvement from federation
    }

def get_langfuse_client():
    """Get a Langfuse client instance"""
    if not LANGFUSE_AVAILABLE:
        return None
        
    try:
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "DARCON_PK_langfuse")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "DARCON_SK_langfuse")
        host = os.environ.get("LANGFUSE_HOST", "http://localhost:3002")
        
        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host
        )
    except Exception as e:
        logger.error(f"Error initializing Langfuse client: {e}")
        return None

@st.cache_data(ttl=REFRESH_INTERVAL)
def fetch_trace_data(limit=100):
    """Fetch trace data from Langfuse"""
    client = get_langfuse_client()
    if not client:
        return []
        
    try:
        # This would use the Langfuse API to fetch traces
        # Since direct API access isn't available in the client yet,
        # we'll return simulated data
        return [
            {"id": f"trace_{i}", "name": f"Agent Request {i}", "timestamp": time.time() - i * 100, 
             "agent": ["browser-use", "hallno", "docker-sandbox", "lightrag", "data-analyzer"][i % 5],
             "duration": np.random.randint(50, 1000),
             "tokens": np.random.randint(100, 5000),
             "status": "success" if np.random.random() > 0.1 else "error"}
            for i in range(limit)
        ]
    except Exception as e:
        logger.error(f"Error fetching trace data: {e}")
        return []

def format_uptime(seconds):
    """Format uptime in seconds to a human-readable string"""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{int(days)}d")
    if hours > 0:
        parts.append(f"{int(hours)}h")
    if minutes > 0:
        parts.append(f"{int(minutes)}m")
    if seconds > 0 or not parts:
        parts.append(f"{int(seconds)}s")
    
    return " ".join(parts)


# Dashboard Sections

def render_header():
    """Render the dashboard header with key metrics"""
    st.markdown("<h1 class='dashboard-title'>📊 MCP ARMY INTEGRATED OBSERVABILITY</h1>", unsafe_allow_html=True)
    
    # Fetch data
    system_metrics = fetch_system_metrics()
    federation_metrics = fetch_federation_metrics()
    
    # Create metric cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Agents Online</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{system_metrics['agent_count']}</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='sub-number'>Uptime: {format_uptime(system_metrics['uptime'])}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Success Rate</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{system_metrics['success_rate']*100:.1f}%</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='sub-number'>{system_metrics['total_requests']} total requests</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col3:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Avg Response Time</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{system_metrics['avg_response_time']} ms</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='sub-number'>{system_metrics['error_count']} errors</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col4:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Federation Contributions</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{federation_metrics['total_contributions']}</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='sub-number'>From {federation_metrics['unique_contributors']} agents</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

def render_agent_performance():
    """Render agent performance metrics"""
    st.subheader("Agent Performance")
    
    # Fetch data
    agents = fetch_agent_data()
    performance = fetch_agent_performance()
    
    if not agents:
        st.warning("No agent data available. Please check your discovery configuration.")
        return
    
    # Create dataframe for visualization
    agent_data = []
    for agent_id, agent in agents.items():
        perf = performance.get(agent_id, {})
        agent_data.append({
            "Agent ID": agent_id,
            "Agent Name": agent.name,
            "Status": agent.status,
            "Contributions": perf.get("contributions", 0),
            "Accuracy": perf.get("accuracy", 0) * 100,  # Convert to percentage
            "Requests": perf.get("total", 0),
            "Success Rate": perf.get("correct", 0) / max(1, perf.get("total", 1)) * 100
        })
    
    if not agent_data:
        st.info("No performance data available yet.")
        return
    
    df = pd.DataFrame(agent_data)
    
    # Create visualizations
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        fig = px.bar(
            df, 
            x="Agent Name", 
            y="Contributions",
            color="Accuracy",
            color_continuous_scale="Viridis",
            title="Agent Contributions and Accuracy"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        fig = px.scatter(
            df,
            x="Requests",
            y="Success Rate",
            size="Contributions",
            color="Agent Name",
            hover_name="Agent Name",
            size_max=40,
            title="Agent Performance Matrix"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Detailed table
    st.markdown("<h3>Detailed Agent Metrics</h3>", unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True)

def render_federated_learning():
    """Render federated learning metrics"""
    st.subheader("Federated Learning Insights")
    
    # Fetch data
    federation_metrics = fetch_federation_metrics()
    
    # Knowledge type distribution
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        knowledge_df = pd.DataFrame([
            {"Type": k, "Count": v} 
            for k, v in federation_metrics["knowledge_types"].items()
        ])
        
        fig = px.pie(
            knowledge_df,
            values="Count",
            names="Type",
            title="Knowledge Vector Distribution",
            color_discrete_sequence=px.colors.sequential.Viridis
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        quality_df = pd.DataFrame([
            {"Agent": k, "Quality Score": v} 
            for k, v in federation_metrics["quality_scores"].items()
        ])
        
        fig = px.bar(
            quality_df,
            x="Agent",
            y="Quality Score",
            color="Quality Score",
            color_continuous_scale="Viridis",
            title="Agent Contribution Quality"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Federation impact
    st.markdown("<h3>Federation Impact</h3>", unsafe_allow_html=True)
    st.markdown("<div class='highlight-card'>", unsafe_allow_html=True)
    st.markdown(f"""
        <p>Federated learning has improved agent performance by 
        <strong>{federation_metrics['improvement_rate']*100:.1f}%</strong> based on 
        accuracy and response quality metrics.</p>
    """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Create simulated time series data for federation progress
    days = 14
    base = np.linspace(0.7, 0.9, days)  # Base performance trend
    federated = base + federation_metrics['improvement_rate'] * np.linspace(0, 1, days)  # With federation
    
    # Ensure values stay below 1.0
    federated = np.minimum(federated, 0.99)
    
    dates = [datetime.datetime.now() - datetime.timedelta(days=i) for i in range(days)][::-1]
    
    progress_df = pd.DataFrame({
        'Date': dates,
        'Without Federation': base,
        'With Federation': federated
    })
    
    st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
    fig = px.line(
        progress_df, 
        x='Date', 
        y=['Without Federation', 'With Federation'],
        title='Agent Performance Over Time',
        labels={'value': 'Performance Score', 'variable': 'Mode'}
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

def render_trace_analysis():
    """Render trace analysis from Langfuse"""
    st.subheader("Agent Request Tracing")
    
    # Fetch trace data
    traces = fetch_trace_data()
    
    if not traces:
        st.warning("No trace data available. Langfuse may not be configured correctly.")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(traces)
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        avg_duration = df['duration'].mean()
        st.metric("Avg Duration", f"{avg_duration:.0f} ms")
    
    with col2:
        avg_tokens = df['tokens'].mean()
        st.metric("Avg Tokens", f"{avg_tokens:.0f}")
    
    with col3:
        success_rate = (df['status'] == 'success').mean() * 100
        st.metric("Success Rate", f"{success_rate:.1f}%")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        # Group by agent and calculate average duration
        agent_perf = df.groupby('agent')['duration'].mean().reset_index()
        fig = px.bar(
            agent_perf,
            x='agent',
            y='duration',
            title="Average Response Time by Agent",
            labels={'duration': 'Duration (ms)', 'agent': 'Agent'}
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
        # Group by agent and calculate token usage
        token_usage = df.groupby('agent')['tokens'].mean().reset_index()
        fig = px.bar(
            token_usage,
            x='agent',
            y='tokens',
            title="Average Token Usage by Agent",
            labels={'tokens': 'Tokens', 'agent': 'Agent'}
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Recent traces table
    st.markdown("<h3>Recent Agent Traces</h3>", unsafe_allow_html=True)
    
    # Format the dataframe for display
    display_df = df.copy()
    display_df['timestamp'] = pd.to_datetime(display_df['timestamp'], unit='s')
    display_df = display_df.sort_values('timestamp', ascending=False)
    
    # Add status colors
    def color_status(val):
        color = 'green' if val == 'success' else 'red'
        return f'background-color: {color}; color: white'
    
    st.dataframe(
        display_df.style.applymap(
            color_status, 
            subset=['status']
        ),
        use_container_width=True
    )
    
    # Link to Langfuse UI
    st.markdown(f"""
        <p>For detailed trace analysis, visit the 
        <a href="{LANGFUSE_URL}" target="_blank">Langfuse UI</a>.</p>
    """, unsafe_allow_html=True)

def render_system_health():
    """Render system health metrics"""
    st.subheader("System Health")
    
    # Fetch system metrics
    metrics = fetch_system_metrics()
    
    # Display key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>CPU Usage</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{metrics['cpu_usage']}%</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Memory Usage</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{metrics['memory_usage']} GB</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col3:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Uptime</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{format_uptime(metrics['uptime'])}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col4:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Error Rate</p>", unsafe_allow_html=True)
        error_rate = metrics['error_count'] / max(1, metrics['total_requests']) * 100
        st.markdown(f"<p class='big-number'>{error_rate:.2f}%</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Generate some simulated time series data for CPU and memory
    # In a real implementation, this would come from a time series database
    timestamps = [datetime.datetime.now() - datetime.timedelta(minutes=i*15) for i in range(24)][::-1]
    
    # Add some randomness to the CPU/memory data
    cpu_data = [metrics['cpu_usage'] + np.random.normal(0, 5) for _ in range(24)]
    cpu_data = [max(0, min(100, x)) for x in cpu_data]  # Clamp between 0-100
    
    memory_data = [metrics['memory_usage'] + np.random.normal(0, 0.2) for _ in range(24)]
    memory_data = [max(0, x) for x in memory_data]  # Ensure positive
    
    resource_df = pd.DataFrame({
        'Timestamp': timestamps,
        'CPU Usage (%)': cpu_data,
        'Memory Usage (GB)': memory_data
    })
    
    # Plot resource usage over time
    st.markdown("<div class='chart-container'>", unsafe_allow_html=True)
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=resource_df['Timestamp'],
        y=resource_df['CPU Usage (%)'],
        name='CPU Usage (%)',
        line=dict(color='#1f77b4')
    ))
    
    fig.add_trace(go.Scatter(
        x=resource_df['Timestamp'],
        y=resource_df['Memory Usage (GB)'] * 10,  # Scale up for visibility
        name='Memory Usage (GB)',
        line=dict(color='#ff7f0e'),
        yaxis='y2'
    ))
    
    fig.update_layout(
        title='System Resource Usage Over Time',
        xaxis=dict(title='Time'),
        yaxis=dict(title='CPU Usage (%)'),
        yaxis2=dict(
            title='Memory Usage (GB)',
            overlaying='y',
            side='right',
            range=[0, 50],  # Adjust based on memory scale
            tickformat='.1f'
        ),
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255, 255, 255, 0.5)')
    )
    
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

def render_langfuse_iframe():
    """Render Langfuse UI in an iframe"""
    st.subheader("Langfuse Tracing")
    
    # Check if Langfuse is available
    langfuse_url = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    
    # Try to check if Langfuse is actually available
    langfuse_available = False
    try:
        response = requests.get(f"{langfuse_url}/api/health", timeout=1)
        langfuse_available = response.status_code == 200
    except:
        pass
    
    if langfuse_available:
        st.markdown(f"""
            <iframe src="{langfuse_url}" 
                    title="Langfuse Tracing Dashboard"
                    allowfullscreen>
            </iframe>
        """, unsafe_allow_html=True)
    else:
        st.warning(f"Langfuse is not available at {langfuse_url}. Please check your configuration.")
        st.info("To enable Langfuse, make sure the Langfuse container is running and accessible.")


def main():
    """Main dashboard application"""
    # Sidebar for controls
    with st.sidebar:
        st.image("https://www.shareicon.net/data/128x128/2016/07/08/117367_logo_512x512.png", width=100)
        st.title("MCP Army Observability")
        
        # Refresh control
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
        
        # Time range selector
        time_range = st.selectbox(
            "Time Range",
            ["Last Hour", "Last Day", "Last Week", "Last Month"]
        )
        
        # Environment selector
        environment = st.selectbox(
            "Environment",
            ["Production", "Staging", "Development"]
        )
        
        st.divider()
        
        # Agent filter
        agents = fetch_agent_data()
        agent_names = ["All Agents"] + [a.name for a in agents.values()]
        selected_agent = st.selectbox("Filter by Agent", agent_names)
        
        st.divider()
        
        # About section
        st.markdown("### About")
        st.markdown("""
            This dashboard provides a unified view of your MCP Army's performance, 
            including agent metrics, federated learning progress, and system health.
        """)
        
        # Last update indicator
        st.markdown(f"**Last updated:** {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    # Render header with key metrics
    render_header()
    
    # Main content tabs
    tabs = st.tabs([
        "📈 Agent Performance", 
        "🧠 Federated Learning", 
        "🔍 Trace Analysis",
        "💻 System Health"
    ])
    
    with tabs[0]:
        render_agent_performance()
    
    with tabs[1]:
        render_federated_learning()
    
    with tabs[2]:
        render_trace_analysis()
    
    with tabs[3]:
        render_system_health()
    
    # Langfuse tab removed as requested
    
    # Footer
    st.markdown("---")
    st.markdown(
        "MCP Army Integrated Observability Dashboard | "
        f"Version 1.0 | System Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def integrated_observability_tab():
    """Main entry point for the Integrated Observability tab in the Streamlit UI"""
    main()

if __name__ == "__main__":
    main()
