"""
Agent Command Center - The Avengers-style mission control for your MCP Army

This dashboard provides a comprehensive view of your entire agent ecosystem,
with real-time monitoring, deployment controls, and system diagnostics.
"""
import os
import time
import json
import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from urllib.parse import urljoin
import subprocess
import socket
from typing import Dict, List, Any, Optional, Tuple

# Import custom modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from archon.discovery import discover_agents, AgentInfo
from archon.langfuse_tracing import MCPTracer

# Note: Page configuration is handled in the main streamlit_ui.py file

# Custom CSS
st.markdown("""
<style>
    .agent-card {
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        background-color: rgba(28, 131, 225, 0.1);
        transition: all 0.3s ease;
    }
    .agent-card:hover {
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        transform: translateY(-2px);
    }
    .agent-online {
        color: #00CC66;
        font-weight: bold;
    }
    .agent-offline {
        color: #FF6B6B;
        font-weight: bold;
    }
    .agent-warning {
        color: #FFCA3A;
        font-weight: bold;
    }
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
    .tab-subheader {
        font-size: 1.5rem;
        margin-bottom: 1rem;
    }
    .dashboard-title {
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
    }
    div[data-testid="stSidebarUserContent"] {
        padding-top: 1rem;
    }
    .stButton>button {
        width: 100%;
    }
    .deployment-controls {
        margin-top: 1rem;
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: rgba(49, 51, 63, 0.1);
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def fetch_agent_data() -> List[Dict[str, Any]]:
    """Discover and fetch data about all available agents."""
    try:
        agents = discover_agents()
        agent_data = []
        
        for agent_id, agent in agents.items():  
            # Basic info
            agent_info = {
                "id": agent_id,
                "name": agent.name,
                "endpoint": agent.endpoint,
                "host": agent.host,
                "port": agent.port,
                "capabilities": agent.capabilities,
                "description": agent.description,
                "status": agent.status,
                "metadata": agent.metadata,
                "health": check_agent_health(agent),
                "metrics": get_agent_metrics(agent)
            }
            agent_data.append(agent_info)
        
        return agent_data
    except Exception as e:
        st.error(f"Error fetching agent data: {str(e)}")
        return []

def check_agent_health(agent: AgentInfo) -> Dict[str, Any]:
    """Check the health of an agent by calling its health endpoint."""
    health_info = {
        "status": "unknown",
        "latency_ms": 0,
        "memory_usage": 0,
        "cpu_usage": 0,
        "uptime": 0
    }
    
    try:
        health_url = urljoin(agent.endpoint, "/health") if agent.endpoint else None
        if not health_url:
            return health_info
        start_time = time.time()
        response = requests.get(health_url, timeout=2)
        latency = (time.time() - start_time) * 1000  # Convert to ms
        
        if response.status_code == 200:
            health_info["status"] = "healthy"
            health_info["latency_ms"] = round(latency, 2)
            
            # Try to parse additional health metrics if available
            try:
                data = response.json()
                health_info["memory_usage"] = data.get("memory_usage", 0)
                health_info["cpu_usage"] = data.get("cpu_usage", 0)
                health_info["uptime"] = data.get("uptime", 0)
            except:
                pass
        else:
            health_info["status"] = "unhealthy"
    except:
        health_info["status"] = "offline"
    
    return health_info

def get_agent_metrics(agent: AgentInfo) -> Dict[str, Any]:
    """Get metrics for an agent."""
    metrics = {
        "requests_total": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "avg_response_time": 0
    }
    
    try:
        metrics_url = urljoin(agent.endpoint, "/metrics") if agent.endpoint else None
        if not metrics_url:
            return metrics
        response = requests.get(metrics_url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            metrics.update(data)
    except:
        pass
    
    return metrics

def render_agent_dashboard():
    """Render the main agent dashboard with real-time metrics."""
    st.markdown("<h1 class='dashboard-title'>🛡️ MCP ARMY COMMAND CENTER</h1>", unsafe_allow_html=True)
    
    # Fetch real agent data (no simulated data)
    agent_data = fetch_agent_data()
    
    # Calculate metrics based on real data only
    total_agents = len(agent_data)
    online_agents = sum(1 for a in agent_data if a.get("health", {}).get("status") in ["healthy", "unknown"])
    offline_agents = total_agents - online_agents
    
    # System status indicators
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Total Agents</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{total_agents}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col2:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Agents Online</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='big-number'>{online_agents}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col3:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>System Health</p>", unsafe_allow_html=True)
        health_status = "OPTIMAL" if online_agents == total_agents else "DEGRADED" if online_agents > 0 else "CRITICAL"
        health_color = "#00CC66" if health_status == "OPTIMAL" else "#FFCA3A" if health_status == "DEGRADED" else "#FF6B6B"
        st.markdown(f"<p class='big-number' style='color:{health_color}'>{health_status}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col4:
        st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
        st.markdown("<p>Average Response Time</p>", unsafe_allow_html=True)
        avg_latency = sum(a["health"]["latency_ms"] for a in agent_data if a["health"]["latency_ms"] > 0)
        avg_latency = avg_latency / max(1, sum(1 for a in agent_data if a["health"]["latency_ms"] > 0))
        st.markdown(f"<p class='big-number'>{avg_latency:.2f} ms</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["Agent Grid", "Performance Metrics", "Network Map", "Log Console"])
    
    with tab1:
        st.markdown("<h2 class='tab-subheader'>Agent Status Grid</h2>", unsafe_allow_html=True)
        
        # Filter controls
        col1, col2 = st.columns([3, 1])
        with col1:
            search = st.text_input("Search Agents", "")
        with col2:
            status_filter = st.selectbox("Status", ["All", "Online", "Offline", "Warning"])
        
        # Filter agents based on search and status
        filtered_agents = agent_data
        if search:
            filtered_agents = [a for a in filtered_agents if search.lower() in a["name"].lower() or search.lower() in a["description"].lower()]
        if status_filter != "All":
            status_map = {"Online": "healthy", "Offline": "offline", "Warning": "unhealthy"}
            filtered_agents = [a for a in filtered_agents if a["health"]["status"] == status_map.get(status_filter, a["health"]["status"])]
        
        # Display agents in a grid
        if not filtered_agents:
            st.info("No agents match your filters.")
        else:
            # Create rows of 3 agents each
            for i in range(0, len(filtered_agents), 3):
                cols = st.columns(3)
                for j in range(3):
                    if i + j < len(filtered_agents):
                        agent = filtered_agents[i + j]
                        with cols[j]:
                            st.markdown(f"""
                            <div class='agent-card'>
                                <h3>{agent['name']}</h3>
                                <p>{agent['description']}</p>
                                <p>Version: {agent['metadata'].get("version", "1.0.0")}</p>
                                <p>Status: <span class='agent-{'online' if agent['health']['status'] == 'healthy' else 'offline' if agent['health']['status'] == 'offline' else 'warning'}'>
                                    {agent['health']['status'].upper()}
                                </span></p>
                                <p>Latency: {agent['health']['latency_ms']} ms</p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Action buttons for each agent
                            col1, col2 = st.columns(2)
                            with col1:
                                st.button(f"Inspect", key=f"inspect_{agent['id']}")
                            with col2:
                                st.button(f"{'Restart' if agent['health']['status'] != 'offline' else 'Start'}", key=f"restart_{agent['id']}")
    
    with tab2:
        st.markdown("<h2 class='tab-subheader'>Performance Metrics</h2>", unsafe_allow_html=True)
        
        # Create performance metrics visualization
        if agent_data:
            # Prepare data for charts
            perf_data = []
            for agent in agent_data:
                perf_data.append({
                    "Agent": agent["name"],
                    "Response Time (ms)": agent["health"]["latency_ms"],
                    "CPU Usage (%)": agent["health"]["cpu_usage"],
                    "Memory Usage (MB)": agent["health"]["memory_usage"],
                    "Requests": agent.get("metrics", {}).get("requests_total", 0),
                    "Success Rate (%)": (agent.get("metrics", {}).get("successful_requests", 0) / max(1, agent.get("metrics", {}).get("requests_total", 1))) * 100
                })
            
            df = pd.DataFrame(perf_data)
            
            # Create charts
            col1, col2 = st.columns(2)
            
            with col1:
                # Response time bar chart
                fig = px.bar(df, x="Agent", y="Response Time (ms)", title="Average Response Time by Agent",
                             color="Response Time (ms)", color_continuous_scale="Viridis")
                st.plotly_chart(fig, use_container_width=True)
                
                # Success rate gauge chart
                overall_success = df["Success Rate (%)"].mean()
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=overall_success,
                    title={"text": "Overall Success Rate"},
                    gauge={"axis": {"range": [0, 100]},
                           "bar": {"color": "darkblue"},
                           "steps": [
                               {"range": [0, 50], "color": "red"},
                               {"range": [50, 80], "color": "yellow"},
                               {"range": [80, 100], "color": "green"}
                           ]}
                ))
                st.plotly_chart(fig, use_container_width=True)
                
            with col2:
                # CPU and Memory usage
                fig = px.scatter(df, x="CPU Usage (%)", y="Memory Usage (MB)", 
                                 size="Requests", hover_name="Agent", title="Resource Usage by Agent",
                                 color="Success Rate (%)", size_max=60)
                st.plotly_chart(fig, use_container_width=True)
                
                # Request volume
                fig = px.pie(df, values="Requests", names="Agent", title="Request Distribution")
                st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.markdown("<h2 class='tab-subheader'>Agent Network Map</h2>", unsafe_allow_html=True)
        st.info("Network visualization showing agent connections and communication pathways will appear here when agents are connected.")

    with tab4:
        st.markdown("<h2 class='tab-subheader'>System Log Console</h2>", unsafe_allow_html=True)
        
        # Log filter controls
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            log_search = st.text_input("Filter Logs", "")
        with col2:
            log_level = st.selectbox("Log Level", ["All", "INFO", "WARNING", "ERROR", "DEBUG"])
        with col3:
            auto_refresh = st.checkbox("Auto-refresh", value=True)
        
        # Fetch real system logs - currently returns empty until implemented
        log_entries = []  # Will be replaced with actual log fetching mechanism
        
        # Display a message when no logs are available
        if not log_entries:
            st.info("No system logs available. Connect agents to see their logs here.")
            return
        
        # Apply filters
        if log_search:
            log_entries = [log for log in log_entries if log_search.lower() in log["message"].lower() or log_search.lower() in log["agent"].lower()]
        if log_level != "All":
            log_entries = [log for log in log_entries if log["level"] == log_level]
        
        # Display logs
        log_df = pd.DataFrame(log_entries)
        if not log_df.empty:
            st.dataframe(log_df, use_container_width=True)
        else:
            st.info("No log entries match your filters.")
        
        if auto_refresh:
            st.markdown("<p style='font-size: 0.8rem'>Auto-refreshing logs every 5 seconds</p>", unsafe_allow_html=True)

# Sidebar content
def render_sidebar():
    st.sidebar.image("https://www.shareicon.net/data/128x128/2016/07/08/117367_logo_512x512.png", width=100)
    st.sidebar.title("MCP Army Controls")
    
    st.sidebar.markdown("### System Actions")
    deploy_new = st.sidebar.button("Deploy New Agent", use_container_width=True)
    scan_network = st.sidebar.button("Scan Network", use_container_width=True)
    system_health = st.sidebar.button("Full System Diagnostic", use_container_width=True)
    
    st.sidebar.markdown("### Quick Stats")
    st.sidebar.info("System stats will appear here when agents are connected.")
    
    st.sidebar.markdown("### Environment")
    env = st.sidebar.selectbox("Environment", ["Production", "Staging", "Development"])
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Deployment Controls")
    st.sidebar.info("Advanced deployment controls will be available when agents are connected to the system.")
    
    # Uncomment the code below once you have actual agents to control
    # with st.sidebar.expander("Advanced Controls"):
    #     st.markdown("**Scaling Configuration**")
    #     min_instances = st.number_input("Min Instances", min_value=1, max_value=10, value=1)
    #     max_instances = st.number_input("Max Instances", min_value=1, max_value=20, value=5)
    #     
    #     st.markdown("**Update Strategy**")
    #     strategy = st.radio("Update Strategy", ["Rolling", "Blue/Green", "Canary"])
    #     
    #     apply_settings = st.button("Apply Settings")

# Main application
def main():
    render_sidebar()
    render_agent_dashboard()

def command_center_tab():
    """Main entry point for the Command Center tab in the Streamlit UI"""
    main()

if __name__ == "__main__":
    main()
