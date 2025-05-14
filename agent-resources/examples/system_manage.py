# Try to import Plotly; if it fails, exit with an error message.
try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    import sys
    sys.exit("Plotly is required for this dashboard. Please run 'pip install plotly' and try again.")

import streamlit as st
import psutil
import subprocess
from datetime import datetime
import pandas as pd

# --- Custom CSS for a Better Look ---
st.markdown("""
    <style>
    /* Change the background color */
    .reportview-container {
        background: #f0f2f6;
    }
    /* Style for headers */
    h1, h2, h3 {
        color: #333333;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Helper Functions ---

def bytes_to_gb(b: int) -> str:
    """Convert bytes to a formatted gigabytes string."""
    return f"{b / (1024**3):.2f} GB"

def get_cpu_stats() -> dict:
    """Return CPU usage and frequency information."""
    cpu_usage = psutil.cpu_percent(interval=0.5)
    per_core = psutil.cpu_percent(percpu=True, interval=0.5)
    cpu_freq = psutil.cpu_freq()
    return {
        "Total CPU Usage": f"{cpu_usage}%",
        "CPU Frequency": f"{cpu_freq.current:.2f} MHz" if cpu_freq else "N/A",
        "Per Core Usage": per_core,
    }

def get_memory_stats() -> dict:
    """Return memory usage statistics."""
    mem = psutil.virtual_memory()
    return {
        "Total Memory": bytes_to_gb(mem.total),
        "Available Memory": bytes_to_gb(mem.available),
        "Used Memory": bytes_to_gb(mem.used),
        "Memory Usage": f"{mem.percent}%",
    }

def get_disk_stats() -> dict:
    """Return disk usage statistics for the root partition."""
    disk = psutil.disk_usage('/')
    return {
        "Total Disk": bytes_to_gb(disk.total),
        "Used Disk": bytes_to_gb(disk.used),
        "Free Disk": bytes_to_gb(disk.free),
        "Disk Usage": f"{disk.percent}%",
    }

def get_network_stats() -> dict:
    """Return network I/O statistics (formatted)."""
    net_io = psutil.net_io_counters()
    return {
        "Bytes Sent": bytes_to_gb(net_io.bytes_sent),
        "Bytes Received": bytes_to_gb(net_io.bytes_recv),
        "Packets Sent": net_io.packets_sent,
        "Packets Received": net_io.packets_recv,
    }

def get_gpu_stats() -> list:
    """
    Return a list of dictionaries (one per GPU) containing GPU temperature,
    utilization, and memory statistics. This uses nvidia-smi for the metrics.
    """
    try:
        query = (
            "nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,utilization.memory,"
            "memory.total,memory.free,memory.used --format=csv,noheader,nounits"
        )
        result = subprocess.check_output(query, shell=True).decode("utf-8").strip()
        gpu_stats = []
        for line in result.splitlines():
            parts = line.split(',')
            if len(parts) == 6:
                stats = {
                    "Temperature (°C)": parts[0].strip(),
                    "GPU Utilization (%)": parts[1].strip(),
                    "Memory Utilization (%)": parts[2].strip(),
                    "Total Memory (MiB)": parts[3].strip(),
                    "Free Memory (MiB)": parts[4].strip(),
                    "Used Memory (MiB)": parts[5].strip(),
                }
                gpu_stats.append(stats)
        return gpu_stats
    except Exception as e:
        return [{"Error": str(e)}]

def get_sensor_temps() -> dict:
    """Return all available sensor temperature readings."""
    try:
        return psutil.sensors_temperatures()
    except Exception as e:
        return {"Error": str(e)}

def system_stats() -> dict:
    """
    Aggregate and return all system statistics:
      - CPU
      - Memory
      - Disk
      - Network
      - GPU
      - Sensor Temperatures
    """
    return {
        "cpu": get_cpu_stats(),
        "memory": get_memory_stats(),
        "disk": get_disk_stats(),
        "network": get_network_stats(),
        "gpu": get_gpu_stats(),
        "sensors": get_sensor_temps(),
    }

# --- Main Dashboard Function ---

def main():
    # Optional: auto-refresh every 2 seconds.
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=2000, key="system_dashboard")
    except ImportError:
        st.warning("For auto-refresh install streamlit-autorefresh: pip install streamlit-autorefresh")
    
    st.title("💻 System Management Dashboard")
    
    # Fetch all system stats in one call.
    stats = system_stats()
    
    # Create tabs to organize the display
    tabs = st.tabs(["Overview", "GPU 🎮", "Sensors 🌡️", "Network 📡"])
    
    # --- Overview Tab: CPU, Memory, Disk ---
    with tabs[0]:
        st.header("🔥 CPU Stats")
        # CPU Gauge: Total CPU Usage
        cpu_usage = psutil.cpu_percent(interval=0.5)
        fig_cpu = go.Figure(go.Indicator(
            mode="gauge+number",
            value=cpu_usage,
            title={"text": "Total CPU Usage (%)"},
            gauge={"axis": {"range": [0, 100]},
                   "bar": {"color": "royalblue"}}
        ))
        # Adjust the gauge height here (e.g., change 300 to a different value)
        fig_cpu.update_layout(height=300)
        st.plotly_chart(fig_cpu, use_container_width=True)
        
        st.subheader("Per Core Usage")
        # Create a Plotly bar chart for per-core usage with a different color for each core.
        per_core_usage = stats["cpu"]["Per Core Usage"]
        df_cores = pd.DataFrame({
            "Core": [f"Core {i+1}" for i in range(len(per_core_usage))],
            "Usage": per_core_usage
        })
        # The color_discrete_sequence assigns a unique color for each bar,
        # and showlegend is set to False to hide the legend.
        fig_cores = px.bar(
            df_cores, 
            x="Core", 
            y="Usage", 
            color="Core",
            color_discrete_sequence=px.colors.qualitative.Bold,
            title="Per Core CPU Usage"
        )
        fig_cores.update_layout(showlegend=False)
        st.plotly_chart(fig_cores, use_container_width=True)
        
        st.header("💾 Memory Stats")
        # Memory Gauge: Memory Usage (%)
        mem = psutil.virtual_memory()
        mem_usage = mem.percent
        fig_mem = go.Figure(go.Indicator(
            mode="gauge+number",
            value=mem_usage,
            title={"text": "Memory Usage (%)"},
            gauge={"axis": {"range": [0, 100]},
                   "bar": {"color": "darkorange"}}
        ))
        fig_mem.update_layout(height=300)
        st.plotly_chart(fig_mem, use_container_width=True)
        # Show additional memory metrics
        mem_stats = stats["memory"]
        col_mem1, col_mem2, col_mem3 = st.columns(3)
        col_mem1.metric("Total Memory", mem_stats["Total Memory"])
        col_mem2.metric("Used Memory", mem_stats["Used Memory"])
        col_mem3.metric("Available Memory", mem_stats["Available Memory"])
        
        st.header("💽 Disk Stats")
        # Disk Gauge: Disk Usage (%)
        dsk = psutil.disk_usage('/')
        disk_usage = dsk.percent
        fig_disk = go.Figure(go.Indicator(
            mode="gauge+number",
            value=disk_usage,
            title={"text": "Disk Usage (%)"},
            gauge={"axis": {"range": [0, 100]},
                   "bar": {"color": "firebrick"}}
        ))
        fig_disk.update_layout(height=300)
        st.plotly_chart(fig_disk, use_container_width=True)
        # Show additional disk metrics
        disk_stats = stats["disk"]
        col_disk1, col_disk2, col_disk3 = st.columns(3)
        col_disk1.metric("Total Disk", disk_stats["Total Disk"])
        col_disk2.metric("Used Disk", disk_stats["Used Disk"])
        col_disk3.metric("Free Disk", disk_stats["Free Disk"])
    
    # --- GPU Tab ---
    with tabs[1]:
        st.header("🎮 GPU Stats")
        gpu_stats = stats["gpu"]
        if gpu_stats and "Error" not in gpu_stats[0]:
            for idx, gpu in enumerate(gpu_stats):
                st.subheader(f"GPU {idx}")
                col1, col2, col3 = st.columns(3)
                # GPU Utilization Gauge
                with col1:
                    try:
                        value_util = float(gpu["GPU Utilization (%)"])
                    except ValueError:
                        value_util = 0
                    fig_util = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=value_util,
                        title={"text": "GPU Utilization (%)"},
                        gauge={"axis": {"range": [0, 100]},
                               "bar": {"color": "royalblue"}}
                    ))
                    st.plotly_chart(fig_util, use_container_width=True)
                # Memory Utilization Gauge
                with col2:
                    try:
                        value_mem = float(gpu["Memory Utilization (%)"])
                    except ValueError:
                        value_mem = 0
                    fig_mem_gpu = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=value_mem,
                        title={"text": "Memory Utilization (%)"},
                        gauge={"axis": {"range": [0, 100]},
                               "bar": {"color": "darkorange"}}
                    ))
                    st.plotly_chart(fig_mem_gpu, use_container_width=True)
                # Temperature Gauge
                with col3:
                    try:
                        value_temp = float(gpu["Temperature (°C)"])
                    except ValueError:
                        value_temp = 0
                    fig_temp = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=value_temp,
                        title={"text": "Temperature (°C)"},
                        gauge={"axis": {"range": [0, 100]},
                               "bar": {"color": "firebrick"}}
                    ))
                    st.plotly_chart(fig_temp, use_container_width=True)
        else:
            st.write("No GPU data available or an error occurred.")
    
    # --- Sensors Tab ---
    with tabs[2]:
        st.header("🌡️ Sensor Temperatures")
        sensors = stats["sensors"]
        if sensors and "Error" not in sensors:
            for sensor_label, entries in sensors.items():
                st.subheader(f"{sensor_label} Sensors")
                data = []
                for entry in entries:
                    data.append({
                        "Sensor": entry.label if entry.label else "Sensor",
                        "Current (°C)": entry.current,
                        "High (°C)": entry.high if entry.high is not None else None,
                        "Critical (°C)": entry.critical if entry.critical is not None else None,
                    })
                if data:
                    df_sensors = pd.DataFrame(data)
                    st.dataframe(df_sensors)
                else:
                    st.write("No data available for", sensor_label)
        else:
            st.write("No sensor data available.")
    
    # --- Network Tab ---
    with tabs[3]:
        st.header("📡 Network Stats")
        net = psutil.net_io_counters()
        bytes_sent_gb = net.bytes_sent / (1024**3)
        bytes_recv_gb = net.bytes_recv / (1024**3)
        # For gauge ranges, use a dynamic maximum (1.2 times the current value, or at least 1)
        max_sent = max(bytes_sent_gb * 1.2, 1)
        max_recv = max(bytes_recv_gb * 1.2, 1)
        col_net1, col_net2 = st.columns(2)
        with col_net1:
            fig_sent = go.Figure(go.Indicator(
                mode="gauge+number",
                value=bytes_sent_gb,
                title={"text": "Bytes Sent (GB)"},
                gauge={"axis": {"range": [0, max_sent]},
                       "bar": {"color": "seagreen"}}
            ))
            st.plotly_chart(fig_sent, use_container_width=True)
        with col_net2:
            fig_recv = go.Figure(go.Indicator(
                mode="gauge+number",
                value=bytes_recv_gb,
                title={"text": "Bytes Received (GB)"},
                gauge={"axis": {"range": [0, max_recv]},
                       "bar": {"color": "mediumvioletred"}}
            ))
            st.plotly_chart(fig_recv, use_container_width=True)
        # Optionally, also show packets as simple metrics
        col_pkt1, col_pkt2 = st.columns(2)
        col_pkt1.metric("Packets Sent", net.packets_sent)
        col_pkt2.metric("Packets Received", net.packets_recv)
    
    st.markdown(f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# --- Run the Dashboard if Executed as Main ---
if __name__ == '__main__':
    main()
