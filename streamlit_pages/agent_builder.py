import streamlit as st
import yaml
import os
import subprocess
import sys
import json
import re
import uuid
import datetime
import time
import threading
from pathlib import Path
import requests
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional, Union
import pandas as pd
import altair as alt
import base64

# Add the parent directory to the path to fix import issues
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the OnboardingGraph and MCP Stdio Generator
from archon.onboarding_graph import OnboardingGraph
from archon.mcp_stdio_generator import (
    generate_mcp_stdio_config,
    save_mcp_stdio_config,
    generate_chat_interface_html,
    save_chat_interface,
    generate_embedded_chat_widget_code
)

# Paths
COMPOSE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'docker-compose.yml'))
FEATURES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'features'))


def validate_github_url(url: str) -> Tuple[bool, str]:
    """Validate a GitHub repository URL"""
    if not url:
        return False, "URL cannot be empty"
    ssh_pattern = r'^git@github\.com:[\w\.-]+/[\w\.-]+(\.git)?$'
    https_pattern = r'^https://github\.com/[\w\.-]+/[\w\.-]+(\.git)?$'
    if re.match(ssh_pattern, url) or re.match(https_pattern, url):
        return True, ""
    return False, "Invalid GitHub repository format"


@st.cache_data(ttl=300)
def get_available_ports() -> List[int]:
    """Get a list of ports that aren't already used in docker-compose.yml"""
    used_ports = []
    if os.path.exists(COMPOSE_PATH):
        try:
            with open(COMPOSE_PATH, 'r') as f:
                compose = yaml.safe_load(f) or {}
                for svc in compose.get('services', {}).values():
                    for mapping in svc.get('ports', []):
                        if isinstance(mapping, str) and ':' in mapping:
                            host = mapping.split(':')[0]
                            if host.isdigit():
                                used_ports.append(int(host))
                        elif isinstance(mapping, dict) and 'published' in mapping:
                            used_ports.append(int(mapping['published']))
        except Exception:
            pass
    # return the first 10 free ports from 9000–9999
    return [p for p in range(9000, 10000) if p not in used_ports][:10]


def validate_agent_name(name: str) -> Tuple[bool, str]:
    """Validate the agent name (alphanumeric and underscore only)"""
    if not name:
        return False, "Agent name cannot be empty"
    if not re.match(r'^[A-Za-z0-9_]+$', name):
        return False, "Agent name can only contain letters, numbers, and underscores"
    if len(name) < 3:
        return False, "Agent name must be at least 3 characters long"
    if len(name) > 30:
        return False, "Agent name must be at most 30 characters long"
    return True, ""


@st.cache_data(ttl=300)
def get_existing_agent_names() -> List[str]:
    """Get a list of existing agent names from docker-compose.yml"""
    if not os.path.exists(COMPOSE_PATH):
        return []
    try:
        with open(COMPOSE_PATH, 'r') as f:
            compose = yaml.safe_load(f) or {}
            return list(compose.get('services', {}).keys())
    except Exception:
        return []


def test_agent_health(agent_name: str, port: int) -> Dict[str, Any]:
    """Test if the agent is responding to health checks"""
    try:
        res = requests.get(f"http://localhost:{port}/health", timeout=2)
        if res.status_code == 200:
            return {"status": "healthy", "message": res.json()}
        else:
            return {"status": "unhealthy", "message": f"Status code: {res.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@st.cache_data(ttl=300)
def get_default_capabilities() -> List[str]:
    """Get a list of default capabilities for a new agent"""
    return ["basic_response", "text_processing", "invoke_endpoint"]


def validate_form_inputs(form_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate all form inputs and return a list of validation errors"""
    errors = []

    # Agent name
    ok, msg = validate_agent_name(form_data.get('agent_name', ''))
    if not ok:
        errors.append(f"Agent Name: {msg}")

    # Port
    port = form_data.get('port')
    if not isinstance(port, int) or not (1024 <= port <= 65535):
        errors.append("Port: Must be an integer between 1024 and 65535")

    # System prompt
    prompt = form_data.get('system_prompt', '')
    if not prompt or len(prompt) < 10:
        errors.append("System Prompt: Must be at least 10 characters long")

    # Repo URL if provided
    if form_data.get('repo_source') == 'URL':
        ok, msg = validate_github_url(form_data.get('repo_url', ''))
        if not ok:
            errors.append(f"Repository URL: {msg}")

    # Docker image & network
    if not form_data.get('image'):
        errors.append("Docker Image: Cannot be empty")
    if not form_data.get('network'):
        errors.append("Docker Network: Cannot be empty")

    return len(errors) == 0, errors


def get_onboarding_assistant_response(query: str) -> str:
    """Get a response from the onboarding assistant for the given query"""
    faq = {
        "repository": "You can provide a GitHub repository URL (SSH or HTTPS) in the Repository URL field. The system will clone this repository during the onboarding process. Make sure your SSH keys are set up correctly if using an SSH URL.",
        "capabilities": "Capabilities define what your agent can do. Basic capabilities include 'basic_response', 'text_processing', and 'invoke_endpoint'. You can add custom capabilities as needed.",
        "docker": "The Docker image should be a valid image that contains your agent code. The default 'mightrag-agent-base:latest' works for most agents. Make sure your Docker image is accessible.",
        "port": "The port is used to expose your agent's API. Choose an available port that isn't already used by another service.",
        "system prompt": "The system prompt defines your agent's behavior. It should include instructions and context for your agent to function properly.",
        "a2a": "Agent-to-Agent (A2A) cards are automatically generated for your agent. These cards contain metadata that allows other agents to discover and communicate with your agent.",
        "test": "You can test your agent using the Test & Benchmark tab. This allows you to run predefined tests and measure your agent's performance.",
        "benchmark": "Benchmarking helps you evaluate your agent's performance across multiple metrics like response time, accuracy, and resource usage."
    }
    for keyword, response in faq.items():
        if keyword in query.lower():
            return response
    return "I can help you with the agent onboarding process. You can ask about repositories, capabilities, Docker settings, or any other part of the onboarding process."


def test_agent_basic(agent_name: str, port: int, test_query: str = "Hello") -> Dict[str, Any]:
    """Run a basic test against an agent and return the results"""
    start_time = datetime.datetime.now()
    result = {
        "agent_name": agent_name,
        "port": port,
        "query": test_query,
        "timestamp": start_time.isoformat(),
        "success": False,
        "response_time_ms": None,
        "response": None,
        "error": None
    }
    try:
        payload = {
            "message": test_query,
            "thread_id": f"{agent_name}_test_{uuid.uuid4().hex[:8]}",
            "is_first_message": True
        }
        resp = requests.post(f"http://localhost:{port}/invoke", json=payload, timeout=10)
        elapsed = (datetime.datetime.now() - start_time).total_seconds() * 1000
        result["response_time_ms"] = round(elapsed, 2)
        if resp.status_code == 200:
            result["success"] = True
            result["response"] = resp.json()
        else:
            result["error"] = f"Status code: {resp.status_code}, Response: {resp.text}"
    except Exception as e:
        result["error"] = str(e)
    return result


def benchmark_agent(agent_name: str, port: int, num_requests: int = 5, interval_ms: int = 500) -> Dict[str, Any]:
    """Benchmark an agent with multiple requests and measure performance"""
    summary = {"success_rate": 0, "avg_response_time_ms": 0, "min_response_time_ms": 0, "max_response_time_ms": 0}
    tests = []
    successes = 0
    times = []
    queries = [
        "Hello, who are you?",
        "What can you do?",
        "Tell me about yourself",
        "How do you work?",
        "What are your capabilities?"
    ]
    for i in range(num_requests):
        res = test_agent_basic(agent_name, port, queries[i % len(queries)])
        tests.append(res)
        if res["success"]:
            successes += 1
            times.append(res["response_time_ms"])
        if i < num_requests - 1:
            time.sleep(interval_ms / 1000)
    if times:
        summary["success_rate"] = successes / num_requests
        summary["avg_response_time_ms"] = round(sum(times) / len(times), 2)
        summary["min_response_time_ms"] = round(min(times), 2)
        summary["max_response_time_ms"] = round(max(times), 2)
    return {
        "agent_name": agent_name,
        "port": port,
        "timestamp": datetime.datetime.now().isoformat(),
        "num_requests": num_requests,
        "interval_ms": interval_ms,
        "tests": tests,
        "summary": summary
    }


@st.cache_data(ttl=300)
def get_agent_list() -> List[Dict[str, Any]]:
    """Get a list of all registered agents from docker-compose.yml"""
    agents = []
    if os.path.exists(COMPOSE_PATH):
        try:
            with open(COMPOSE_PATH, 'r') as f:
                compose = yaml.safe_load(f) or {}
                for svc_name, svc in compose.get('services', {}).items():
                    if svc_name.startswith(('agent_', 'rag-')) or svc.get('container_name', '').startswith('rag-'):
                        port = None
                        for m in svc.get('ports', []):
                            if isinstance(m, str) and ':' in m:
                                port = int(m.split(':')[0])
                                break
                        agents.append({
                            "name": svc_name,
                            "port": port,
                            "image": svc.get('image', 'unknown'),
                            "container_name": svc.get('container_name', f"rag-{svc_name}")
                        })
        except Exception:
            pass
    return agents


# -- Streamlit UI -- #
def agent_builder_tab():

    st.title("🛠️ Agent Builder: Create & Launch New Agents")
    st.write("""
    Configure your new agent below. When you hit **Fire Up Agent**, the system will:
    - Create a new Docker service for your agent
    - Configure it with your specified settings
    - Start the container automatically
    - Show you a 'Ready to Use' message when complete
    """)

    existing_agent_names = get_existing_agent_names()
    available_ports = get_available_ports()

    tabs = st.tabs([
        "Basic Config",
        "Advanced Config",
        "Import Agent",
        "Test & Benchmark",
        "Standalone Tools",
        "Onboarding Assistant"
    ])

    # --- Basic Config --- #
    with tabs[0]:
        with st.form("agent_form_basic"):
            st.subheader("Basic Agent Information")
            agent_name = st.text_input(
                "Agent Name (unique, alphanumeric with underscores only)",
                help="This will be used as the service name in docker-compose.yml"
            )
            if agent_name and agent_name in existing_agent_names:
                st.warning(f"⚠️ Agent '{agent_name}' already exists! Creating it will update the existing agent.")
            port = st.selectbox("Port Number", available_ports, help="Select a port for your agent's API")
            system_prompt = st.text_area(
                "System Prompt",
                value="You are a helpful AI agent.",
                help="This will be used as the agent's system prompt"
            )
            submit_basic = st.form_submit_button("Fire Up Agent")

        if submit_basic:
            valid, errors = validate_form_inputs({
                'agent_name': agent_name,
                'port': port,
                'system_prompt': system_prompt,
                'repo_url': '',
                'repo_source': '',
                'image': '',
                'network': ''
            })
            if not valid:
                st.error("Please fix the following errors:")
                for e in errors:
                    st.error(f"- {e}")
            else:
                with st.spinner("Onboarding your agent..."):
                    try:
                        ctx = {'agent_name': agent_name, 'port': port, 'system_prompt': system_prompt}
                        og = OnboardingGraph()
                        result = og.onboard(ctx)
                        if result.get('error'):
                            st.error(f"Onboarding failed: {result['error']}")
                        else:
                            # Launch container
                            subprocess.run(
                                ['docker-compose', '-f', COMPOSE_PATH, 'up', '-d', agent_name],
                                check=True
                            )
                            st.success("✅ Agent created and container launched!")
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

    # --- Advanced Config --- #
    with tabs[1]:
        with st.form("agent_form_advanced"):
            st.subheader("Advanced Agent Configuration")
            adv_agent_name = st.text_input("Agent Name", help="Unique, alphanumeric with underscores only")
            if adv_agent_name and adv_agent_name in existing_agent_names:
                st.warning(f"⚠️ Agent '{adv_agent_name}' already exists! This will update it.")
            adv_port = st.selectbox("Port Number", available_ports)
            adv_system_prompt = st.text_area("System Prompt", value="You are a helpful AI agent.")
            endpoints_text = st.text_area("Additional Endpoints (one per line)", value="/invoke\n/health", height=100)
            adv_image = st.text_input("Docker Image", value="mightrag-agent-base:latest")
            adv_network = st.text_input("Docker Network", value="mightrag-net")
            restart_policy = st.selectbox(
                "Restart Policy",
                options=["no", "always", "on-failure", "unless-stopped"],
                index=3
            )
            custom_volumes = st.text_area("Custom Volumes (one per line)", value="shared-ssh:/home/rag/.ssh:ro")
            custom_networks = st.text_area("Additional Networks (one per line)", value="")
            version = st.text_input("Version", value="1.0.0")
            author = st.text_input("Author", value="")
            tags = st.text_input("Tags (comma-separated)", value="")
            submit_advanced = st.form_submit_button("Fire Up Advanced Agent 🚀")

        if submit_advanced:
            form = {
                'agent_name': adv_agent_name,
                'port': adv_port,
                'system_prompt': adv_system_prompt,
                'repo_url': '',
                'repo_source': '',
                'image': adv_image,
                'network': adv_network
            }
            valid, errors = validate_form_inputs(form)
            if not valid:
                st.error("Please fix the following errors:")
                for e in errors:
                    st.error(f"- {e}")
            else:
                # Parse additional fields
                endpoints = [e.strip() for e in endpoints_text.splitlines() if e.strip()]
                volumes = [v.strip() for v in custom_volumes.splitlines() if v.strip()]
                networks = [adv_network] + [n.strip() for n in custom_networks.splitlines() if n.strip()]
                tag_list = [t.strip() for t in tags.split(',') if t.strip()]
                advanced_metadata = {
                    "version": version,
                    "author": author,
                    "tags": tag_list,
                    "restart_policy": restart_policy,
                    "endpoints": endpoints,
                    "volumes": volumes,
                    "networks": networks
                }
                with st.spinner("Onboarding your advanced agent..."):
                    try:
                        ctx = {
                            'agent_name': adv_agent_name,
                            'port': adv_port,
                            'system_prompt': adv_system_prompt,
                            'image': adv_image,
                            'network': adv_network,
                            'capabilities': get_default_capabilities(),
                        }
                        ctx.update(advanced_metadata)
                        og = OnboardingGraph()
                        result = og.onboard(ctx)
                        if result.get('error'):
                            st.error(f"Onboarding failed: {result['error']}")
                        else:
                            subprocess.run(
                                ['docker-compose', '-f', COMPOSE_PATH, 'up', '-d', adv_agent_name],
                                check=True
                            )
                            st.success("✅ Advanced agent created and container launched!")
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

    # --- Import Agent --- #
    with tabs[2]:
        with st.form("agent_form_import"):
            st.subheader("Import Existing Agent")
            uploaded_file = st.file_uploader("Agent Card (YAML or JSON)", type=["yaml", "yml", "json"])
            import_repo_url = st.text_input("Repository URL (optional)")
            import_image = st.text_input("Docker Image (optional)")
            submit_import = st.form_submit_button("Import Agent 🚀")

        if submit_import:
            if not uploaded_file:
                st.error("Please upload a valid agent card file")
            else:
                try:
                    content = uploaded_file.read().decode()
                    agent_data = json.loads(content) if uploaded_file.name.endswith('.json') else yaml.safe_load(content)
                    st.success(f"Successfully loaded agent card for '{agent_data.get('agent_name','')}'")
                    st.json(agent_data)
                except Exception as e:
                    st.error(f"Error parsing agent card: {e}")

    # --- Test & Benchmark --- #
    with tabs[3]:
        st.subheader("Test & Benchmark Agents")
        available_agents = get_agent_list()
        agent_names = [a["name"] for a in available_agents]

        if not agent_names:
            st.warning("No agents found. Please create an agent first.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                selected_agent_name = st.selectbox("Select Agent to Test", agent_names)
                selected_agent = next(a for a in available_agents if a["name"] == selected_agent_name)
                st.info(f"Port: {selected_agent['port']}")
                st.info(f"Container: {selected_agent['container_name']}")
            with col2:
                test_type = st.radio("Test Type", ["Quick Test", "Comprehensive Benchmark", "Custom Test"])

            if test_type == "Quick Test":
                test_query = st.text_input("Test Query", value="Hello, who are you?")
                if st.button("Run Quick Test"):
                    if not selected_agent.get("port"):
                        st.error("Port information not available.")
                    else:
                        with st.spinner("Running quick test..."):
                            res = test_agent_basic(selected_agent_name, selected_agent["port"], test_query)
                        if res["success"]:
                            st.success(f"✅ Test succeeded in {res['response_time_ms']}ms")
                            st.subheader("Response")
                            st.json(res["response"])
                        else:
                            st.error(f"❌ Test failed: {res['error']}")

            elif test_type == "Comprehensive Benchmark":
                num_requests = st.slider("Number of Requests", 3, 20, 5)
                interval_ms = st.slider("Interval between Requests (ms)", 100, 2000, 500, step=100)
                if st.button("Run Benchmark"):
                    if not selected_agent.get("port"):
                        st.error("Port information not available.")
                    else:
                        with st.spinner("Benchmarking..."):
                            bench = benchmark_agent(selected_agent_name, selected_agent["port"], num_requests, interval_ms)
                        st.success("✅ Benchmark complete!")
                        summary = bench["summary"]
                        success_rate_pct = summary["success_rate"] * 100

                        # Display Success Rate
                        st.markdown(f"""
    <div style="background-color: {'#e6fff2' if success_rate_pct>80 else '#fff2e6'}; padding:20px; border-radius:10px; text-align:center;">
    <h2 style="margin:0; font-size:48px; color:{'#00cc66' if success_rate_pct>80 else '#ff8c1a'};">
        {success_rate_pct:.1f}%
    </h2>
    <p style="margin:5px 0 0;font-size:18px;">Success Rate</p>
    </div>
    """, unsafe_allow_html=True)

                        # Metrics cards
                        cols = st.columns(4)
                        avg_time = summary["avg_response_time_ms"]
                        time_color = '#00cc66' if avg_time<500 else ('#ff8c1a' if avg_time<1000 else '#cc3300')
                        cards = [
                            ("Avg Response Time", f"{avg_time}ms", time_color),
                            ("Min Response Time", f"{summary['min_response_time_ms']}ms", "#00cc66"),
                            ("Max Response Time", f"{summary['max_response_time_ms']}ms", "#ff8c1a"),
                            ("Total Requests", str(len(bench["tests"])), "#3366ff"),
                        ]
                        for col, (label, val, color) in zip(cols, cards):
                            col.markdown(f"""
    <div style="background-color:#f0f8ff; padding:15px; border-radius:5px; text-align:center;">
    <p style="margin:0;font-size:14px;color:#666;">{label}</p>
    <h3 style="margin:5px 0; color:{color};">{val}</h3>
    </div>
    """, unsafe_allow_html=True)

                        # Donut chart
                        success_count = sum(1 for t in bench["tests"] if t["success"])
                        fail_count = len(bench["tests"]) - success_count
                        df = pd.DataFrame({
                            "category": ["Successful", "Failed"],
                            "value": [success_count, fail_count]
                        })
                        base = alt.Chart(df).encode(
                            theta=alt.Theta("value:Q", stack=True),
                            color=alt.Color("category:N", legend=alt.Legend(title="Status")),
                            tooltip=["category:N","value:Q"]
                        )
                        donut = base.mark_arc(innerRadius=50, outerRadius=100).properties(width=300,height=300)
                        text = base.mark_text(
                            align='center', baseline='middle', fontSize=20, fontWeight='bold'
                        ).encode(text=alt.value(f"{success_count}/{len(bench['tests'])}"))
                        c1, c2 = st.columns([1,2])
                        with c1:
                            st.altair_chart(donut + text, use_container_width=True)
                        with c2:
                            # Response time trend
                            df2 = pd.DataFrame(bench["tests"])
                            df2 = df2[df2["success"]].copy()
                            if not df2.empty:
                                df2["req_num"] = range(1, len(df2)+1)
                                line = alt.Chart(df2).mark_line(point=True).encode(
                                    x=alt.X("req_num:O", title="Request #"),
                                    y=alt.Y("response_time_ms:Q", title="Response Time (ms)"),
                                    tooltip=["req_num","response_time_ms","query"]
                                )
                                area = alt.Chart(df2).mark_area(opacity=0.3).encode(
                                    x="req_num:O", y="response_time_ms:Q"
                                )
                                st.altair_chart(line + area, use_container_width=True)

                        # Detailed table
                        with st.expander("View Detailed Test Results"):
                            df3 = pd.DataFrame(bench["tests"])
                            df3["status"] = df3["success"].apply(lambda x: "✅" if x else "❌")
                            st.dataframe(df3[["query","response_time_ms","status"]])

            else:  # Custom Test
                st.subheader("Custom Test Configuration")
                custom_query = st.text_area("Custom Query", value="Tell me about yourself and what you can do?", height=100)
                timeout = st.slider("Request Timeout (s)", 1, 60, 10)
                repetitions = st.slider("Test Repetitions", 1, 10, 1)
                include_headers = st.checkbox("Include Custom Headers")
                custom_headers = ""
                if include_headers:
                    custom_headers = st.text_area("Custom Headers (JSON)", value='{ "X-Test-Header": "Value" }', height=100)
                if st.button("Run Custom Test"):
                    if not selected_agent.get("port"):
                        st.error("Port information not available.")
                    else:
                        try:
                            headers = {}
                            if include_headers:
                                headers = json.loads(custom_headers)
                            results = []
                            for i in range(repetitions):
                                start = datetime.datetime.now()
                                res = requests.post(
                                    f"http://localhost:{selected_agent['port']}/invoke",
                                    json={"message": custom_query, "thread_id": f"{selected_agent_name}_custom_{i}", "is_first_message": True},
                                    headers=headers,
                                    timeout=timeout
                                )
                                elapsed = (datetime.datetime.now() - start).total_seconds()*1000
                                results.append({
                                    "repetition": i+1,
                                    "response_time_ms": round(elapsed,2),
                                    "status_code": res.status_code,
                                    "success": res.status_code==200,
                                    "response": res.json() if res.status_code==200 else None,
                                    "error": None if res.status_code==200 else res.text
                                })
                            succ = sum(1 for r in results if r["success"])
                            if succ>0:
                                st.success(f"✅ {succ}/{repetitions} succeeded")
                            else:
                                st.error(f"❌ All {repetitions} tests failed")
                            for r in results:
                                with st.expander(f"Test #{r['repetition']} - {'Success' if r['success'] else 'Failed'}"):
                                    st.write(f"Response Time: {r['response_time_ms']}ms")
                                    st.write(f"Status Code: {r['status_code']}")
                                    if r['success']:
                                        st.json(r['response'])
                                    else:
                                        st.error(r['error'])
                        except Exception as e:
                            st.error(f"Error during custom test: {e}")

            # Agent Status Check
            with st.expander("Agent Status"):
                if st.button("Check Agent Status"):
                    try:
                        out = subprocess.run(
                            ['docker', 'ps', '--filter', f"name={selected_agent['container_name']}", '--format', '{{.Names}}'],
                            capture_output=True, text=True, check=True
                        )
                        if selected_agent['container_name'] in out.stdout:
                            st.success(f"✅ Container '{selected_agent['container_name']}' is running")
                            health = test_agent_health(selected_agent_name, selected_agent["port"])
                            if health["status"] == "healthy":
                                st.success(f"✅ Health check passed: {health['message']}")
                            else:
                                st.warning(f"⚠️ Health: {health['message']}")
                        else:
                            st.error(f"❌ Container '{selected_agent['container_name']}' is not running")
                            if st.button("Start Container"):
                                subprocess.run(
                                    ['docker-compose', '-f', COMPOSE_PATH, 'up', '-d', selected_agent_name],
                                    check=True
                                )
                                st.success("Container started!")
                    except Exception as e:
                        st.error(f"Error checking status: {e}")

    # --- Standalone Tools & Interfaces --- #
    with tabs[4]:
        st.subheader("🔌 Standalone Tools & Interfaces")
        st.markdown("""
    Generate standalone tools and interfaces for your agents.
    This allows your agents to be used as individual components outside the MCP Army ecosystem.
    """)
        agents = get_agent_list()
        names = [a["name"] for a in agents]
        if not names:
            st.warning("No agents available. Create one first.")
        else:
            sel = st.selectbox("Select an agent", names)
            agent = next(a for a in agents if a["name"] == sel)
            st.info(f"**Name:** {agent['name']}    **Port:** {agent['port']}")
            color_options = {"Green":"#4CAF50","Blue":"#2196F3","Purple":"#9C27B0","Orange":"#FF9800","Red":"#F44336","Teal":"#009688"}
            col = st.selectbox("Choose interface color", list(color_options.keys()))
            cap_list = get_default_capabilities()
            if st.checkbox("Enable Code Generation"): cap_list.append("code_generation")
            if st.checkbox("Enable Data Analysis"):  cap_list.append("data_analysis")
            if st.checkbox("Enable Image Processing"):cap_list.append("image_processing")
            if st.checkbox("Enable Document Processing"):cap_list.append("document_processing")
            if st.button("Generate MCP Tools & Chat Interface"):
                with st.spinner("Generating..."):
                    try:
                        agent_id = agent["name"]
                        endpoint = f"http://localhost:{agent['port']}/invoke"
                        desc = f"A helpful {agent_id} agent"
                        agent_dir = os.path.join(FEATURES_PATH, agent_id)
                        os.makedirs(agent_dir, exist_ok=True)
                        mcp = generate_mcp_stdio_config(agent_id, agent_id, endpoint, desc, cap_list)
                        cfg_path = save_mcp_stdio_config(agent_id, mcp, agent_dir)
                        html = generate_chat_interface_html(agent_id, agent_id, endpoint, desc, color_options[col])
                        chat_path = save_chat_interface(agent_id, html, agent_dir)
                        embed = generate_embedded_chat_widget_code(agent_id, agent_id, endpoint)
                        st.success("✅ Generated!")
                        t0, t1, t2 = st.tabs(["MCP Config","Chat Interface","Embed Code"])
                        with t0:
                            st.code(json.dumps(mcp, indent=2), language="json")
                            b64 = base64.b64encode(json.dumps(mcp).encode()).decode()
                            st.markdown(f'<a href="data:application/json;base64,{b64}" download="{agent_id}_mcp_config.json">Download</a>', unsafe_allow_html=True)
                        with t1:
                            st.components.v1.html(html, height=400)
                            b64 = base64.b64encode(html.encode()).decode()
                            st.markdown(f'<a href="data:text/html;base64,{b64}" download="{agent_id}_chat.html">Download</a>', unsafe_allow_html=True)
                        with t2:
                            st.code(embed, language="html")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # Add Onboarding Assistant Chat UI
    with tabs[5]:
        st.subheader("Onboarding Assistant")
        st.markdown("""
        Need help with the agent onboarding process? Ask me anything about:
        - Repository configuration
        - Agent capabilities
        - Docker settings
        - System prompts
        - A2A communication
        - Best practices
        """)
        
        # Initialize chat history
        if 'onboarding_chat_history' not in st.session_state:
            st.session_state.onboarding_chat_history = []
        
        # Display chat history
        for i, (role, message) in enumerate(st.session_state.onboarding_chat_history):
            if role == "user":
                st.markdown(f"<div style='text-align: right; background-color: #e6f7ff; padding: 10px; border-radius: 10px; margin: 5px 0;'><b>You:</b> {message}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='background-color: #f0f0f0; padding: 10px; border-radius: 10px; margin: 5px 0;'><b>Assistant:</b> {message}</div>", unsafe_allow_html=True)
        
        # Chat input
        user_input = st.text_input("Ask a question about the onboarding process:", key="onboarding_question")
        
        if st.button("Send", key="send_onboarding_question"):
            if user_input:
                # Add user message to history
                st.session_state.onboarding_chat_history.append(("user", user_input))
                
                # Get response from assistant
                response = get_onboarding_assistant_response(user_input)
                
                # Add assistant response to history
                st.session_state.onboarding_chat_history.append(("assistant", response))
                
                # Clear input
                st.session_state.onboarding_question = ""
                
                # Rerun to update UI
                st.rerun()

    # Set the submit status based on which form was submitted
    submit = submit_basic or submit_advanced or submit_import

    # Use the appropriate form data based on which was submitted
    if submit_advanced:
        agent_name = adv_agent_name
        port = adv_port
        system_prompt = adv_system_prompt
        image = adv_image
        network = adv_network
        
        # Parse environment variables
        env_vars = {}
        for line in env_vars_text.split('\n'):
            line = line.strip()
            if line and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
        
        # Parse endpoints
        endpoints = [endpoint.strip() for endpoint in endpoints_text.split('\n') if endpoint.strip()]
        
        # Parse volumes
        volumes = [volume.strip() for volume in custom_volumes.split('\n') if volume.strip()]
        
        # Parse additional networks
        additional_networks = [net.strip() for net in custom_networks.split('\n') if net.strip()]
        networks = [network] + additional_networks if network else additional_networks
        
        # Parse tags
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # Additional metadata
        advanced_metadata = {
            "version": version,
            "author": author,
            "tags": tag_list,
            "restart_policy": restart_policy,
            "env_vars": env_vars,
            "endpoints": endpoints,
            "volumes": volumes,
            "networks": networks
        }
    elif submit_import and uploaded_file is not None:
        # Parse uploaded agent card
        try:
            content = uploaded_file.read().decode()
            if uploaded_file.name.endswith('.json'):
                agent_data = json.loads(content)
            else:  # YAML
                agent_data = yaml.safe_load(content)
                
            # Extract values from agent card
            agent_name = agent_data.get('agent_name', '')
            system_prompt = agent_data.get('system_prompt', 'You are a helpful AI agent.')
            port = agent_data.get('port', 9000)
            repo_url = import_repo_url or agent_data.get('repo_url', '')
            image = import_image or agent_data.get('docker_image', 'mightrag-agent-base:latest')
            network = agent_data.get('network', 'mightrag-net')
            
            st.success(f"Successfully loaded agent card for '{agent_name}'")
        except Exception as e:
            st.error(f"Error parsing agent card: {e}")
            submit = False

    if submit:
        # Validate form inputs
        form_valid, validation_errors = validate_form_inputs({
            'agent_name': agent_name,
            'port': port,
            'system_prompt': system_prompt,
            'repo_url': repo_url,
            'repo_source': repo_source if 'repo_source' in locals() else 'URL',
            'image': image,
            'network': network
        })
        
        if not form_valid:
            st.error("Please fix the following errors:")
            for error in validation_errors:
                st.error(f"• {error}")
            st.stop()
        
        with st.spinner("Setting up your agent - this may take a moment..."):
            # Collect all form data into a single context dictionary
            onboarding_context = {
                'agent_name': agent_name,
                'port': port,
                'system_prompt': system_prompt,
                'repo_url': repo_url,
                'image': image,
                'network': network,
                'ssh_volume': ssh_volume,
                'description': description if 'description' in locals() and description else f"Agent created via Agent Builder UI",
                'capabilities': capabilities if 'capabilities' in locals() and capabilities else get_default_capabilities()
            }
            
            # Add advanced metadata if available
            if 'advanced_metadata' in locals() and advanced_metadata:
                onboarding_context.update(advanced_metadata)
            # Create progress container
            progress_container = st.empty()
            progress_container.info("Starting agent onboarding process...")
            
            # Initialize the onboarding graph and process the agent
            onboarding_graph = OnboardingGraph()
            result = onboarding_graph.onboard(onboarding_context)
            
            # Check for errors
            if 'error' in result:
                st.error(f"Onboarding failed: {result['error']}")
                st.stop()
                
            # Display the progress of each agent in the pipeline
            if 'needs' in result:
                progress_container.info("✅ Requirements validated")
            
            if 'repo' in result:
                repo_info = result['repo']
                progress_container.info("✅ Repository processed")
                if repo_info.get('has_dockerfile', False):
                    st.success("Dockerfile found in repository")
                if repo_info.get('env_files', []):
                    st.success(f"Found {len(repo_info['env_files'])} environment files")
            
            if 'code' in result:
                progress_container.info("✅ Code generation complete")
            
            if 'config' in result:
                progress_container.info("✅ Configuration generated")
                
            # Check final rank/status
            if 'rank' in result:
                rank_info = result['rank']
                if rank_info.get('status') == 'success':
                    st.success(rank_info.get('message', f"Agent '{agent_name}' successfully onboarded!"))
                    
                    # Display next steps
                    if 'next_steps' in rank_info:
                        st.subheader("Next Steps:")
                        for step in rank_info['next_steps']:
                            st.markdown(f"- {step}")
                else:
                    st.error(f"Onboarding failed at final stage: {rank_info.get('error', 'Unknown error')}")
                    if 'recommendations' in rank_info:
                        st.subheader("Recommendations:")
                        for rec in rank_info['recommendations']:
                            st.markdown(f"- {rec}")
            
            # --- 3. Fire up the agent container ---
            st.info("Launching agent container...")
            try:
                result = subprocess.run([
                    'docker-compose',
                    '-f', COMPOSE_PATH,
                    'up', '-d', agent_name
                ], capture_output=True, text=True, check=True)
                st.success(f"Agent '{agent_name}' is ready to use! 🚀")
                st.code(result.stdout)
            except subprocess.CalledProcessError as e:
                st.error(f"Failed to launch agent: {e.stderr}")
                st.stop()
            
            # --- 4. Show summary ---
            st.subheader("Agent Created!")
            
            # Create a cleaner version of the context for display
            display_config = {
                'agent_name': agent_name,
                'system_prompt': system_prompt,
                'repo_url': repo_url,
                'docker_image': image,
                'network': network,
                'port': port,
                'capabilities': onboarding_context.get('capabilities', [])
            }
            
            st.json(display_config)
            st.info("You can now interact with your agent via the MCP system.")

            # Add a testing section
            st.subheader("Agent Testing")

            # Test container is running
            container_name = f"rag-{agent_name}"
            try:
                container_check = subprocess.run(
                    ['docker', 'ps', '--filter', f"name={container_name}", '--format', '{{.Names}}'],
                    capture_output=True, text=True, check=True
                )

                if container_name in container_check.stdout:
                    st.success(f"✅ Container '{container_name}' is running")

                    # Health check
                    health_check = test_agent_health(agent_name, port)
                    if health_check["status"] == "healthy":
                        st.success(f"✅ Agent health check passed: {health_check['message']}")
                    else:
                        st.warning(f"⚠️ Agent health check: {health_check['message']}")

                    # Offer a quick test of the agent
                    st.subheader("Quick Test")
                    test_message = st.text_input("Send a test message to your agent", value="Hello, who are you?")
                    if st.button("Send Test"):
                        with st.spinner("Testing agent response..."):
                            try:
                                test_data = {
                                    "message": test_message,
                                    "thread_id": str(agent_name) + "_test",
                                    "is_first_message": True
                                }
                                response = requests.post(
                                    f"http://localhost:{port}/invoke", 
                                    json=test_data,
                                    timeout=5
                                )

                                if response.status_code == 200:
                                    st.success("Agent responded successfully!")
                                    st.json(response.json())
                                else:
                                    st.error(f"Error: Status code {response.status_code}")
                                    st.text(response.text)
                            except Exception as e:
                                st.error(f"Error testing agent: {str(e)}")
                else:
                    st.error(f"Container '{container_name}' is not running. Check docker logs.")
            except Exception as e:
                st.error(f"Error checking container status: {str(e)}")

            # Generate the A2A card
            try:
                agent_dir = os.path.join(FEATURES_PATH, agent_name)
                a2a_card_path, a2a_card = generate_a2a_card(display_config, agent_dir)
                st.success(f"✅ A2A card generated: `{os.path.basename(a2a_card_path)}`")

                # Show A2A card contents
                with open(a2a_card_path, 'r') as f:
                    a2a_card = json.load(f)

                with st.expander("View A2A Card"):
                    st.json(a2a_card)
            except Exception as e:
                st.warning(f"⚠️ Could not generate A2A card: {str(e)}")

            # Add links to interact with the agent
            st.subheader("Next Steps")
            st.markdown(f"""  
            - View agent in **Chat Interface**: Go to the Chat tab and your agent will be available  
            - Monitor agent: `docker logs -f {container_name}`  
            - Update configuration: Edit `features/{agent_name}/agent_card.yaml`  
            - Access agent directly: `http://localhost:{port}/invoke`
            """)
