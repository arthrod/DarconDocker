"""
Onboarding Graph: Modular Agent Onboarding Workflow for MCP Army

- This graph/chain handles the onboarding of new agents/tools.
- Agents are prebuilt and registered in docker-compose.yml as onboarding helpers.
- Each agent in the chain specializes in a step: requirements, repo setup, code scaffolding, config, ranking/decision.
- The onboarding graph can communicate with the main MCP graph to notify about onboarding progress and capabilities.
- Once onboarding is complete, the new agent is registered and migrates to the main MCP agent graph.
"""

import os
import yaml
import shutil
import json
import re
import subprocess
import git
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import sys

# Add the parent directory to the path to fix import issues
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from archon.agent_notice_board_client import AgentNoticeBoardClient

# Define paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_PATH = os.path.join(PROJECT_ROOT, 'docker-compose.yml')
FEATURES_PATH = os.path.join(PROJECT_ROOT, 'features')
DOCKER_REPOS_PATH = os.path.join(PROJECT_ROOT, 'docker_repos')
class OnboardingGraph:
    """
    OnboardingGraph wires in the Agent Notice Board (Supabase) for context sharing.
    Posts notices at onboarding start, after each agent stage, and on completion.
    """
    def __init__(self):
        self.agents = [
            NeedsAgent(),
            RepoAgent(),
            CodingAgent(),
            ConfigAgent(),
            RankingAgent(),
        ]
        self.server_graph_callback = None  # Function to notify MCP server graph
        self.notice_client = AgentNoticeBoardClient()

    def set_server_graph_callback(self, callback):
        self.server_graph_callback = callback

    def onboard(self, user_input: Dict[str, Any]):
        context = user_input
        # Post onboarding start notice
        self.notice_client.post_notice(
            agent_id="onboarding_graph",
            notice_type="onboarding_start",
            payload={"context": context}
        )
        for agent in self.agents:
            context = agent.handle(context)
            # Post progress after each agent step
            self.notice_client.post_notice(
                agent_id=agent.name,
                notice_type="onboarding_progress",
                payload={"step": agent.name, "context": context}
            )
            if self.server_graph_callback:
                self.server_graph_callback(agent.name, context)
        # Post onboarding completion notice
        self.notice_client.post_notice(
            agent_id="onboarding_graph",
            notice_type="onboarding_complete",
            payload={"final_context": context}
        )
        # At the end, migrate agent to MCP server graph
        return context

class NeedsAgent:
    """
    Gathers user requirements and presents options for agent creation.
    Validates input parameters and ensures uniqueness.
    """
    name = "NeedsAgent"
    
    def handle(self, context):
        # Extract required parameters from context or use defaults
        agent_name = context.get('agent_name', '')
        port = context.get('port', 9000)
        
        # Validate agent name (must be unique)
        if agent_name:
            with open(COMPOSE_PATH, 'r') as f:
                compose = yaml.safe_load(f) or {}
                services = compose.get('services', {})
                
                if agent_name in services:
                    context['error'] = f"Agent name '{agent_name}' already exists in docker-compose.yml"
                    return context
        
        # Validate port (must be available)
        if port:
            with open(COMPOSE_PATH, 'r') as f:
                compose = yaml.safe_load(f) or {}
                services = compose.get('services', {})
                
                used_ports = []
                for svc in services.values():
                    ports = svc.get('ports', [])
                    for port_mapping in ports:
                        if isinstance(port_mapping, str):
                            host_port = port_mapping.split(':')[0]
                            used_ports.append(int(host_port))
                
                if port in used_ports:
                    context['error'] = f"Port {port} is already in use in docker-compose.yml"
                    return context
        
        # Store validated requirements
        context['needs'] = {
            'agent_name': agent_name,
            'port': port,
            'validation': 'passed'
        }
        
        return context

class RepoAgent:
    """
    Handles repository discovery, cloning, and analysis.
    Identifies Dockerfile, env files, and agent capabilities.
    """
    name = "RepoAgent"
    
    def handle(self, context):
        repo_url = context.get('repo_url')
        agent_name = context.get('agent_name', '')
        
        # Create agent directory in docker_repos if it doesn't exist
        agent_dir = os.path.join(DOCKER_REPOS_PATH, agent_name)
        
        # Dictionary to store repository analysis results
        repo_analysis = {
            'has_dockerfile': False,
            'env_files': [],
            'capabilities': [],
            'repo_path': agent_dir
        }
        
        if repo_url:
            try:
                # Clone the repository if it's a URL
                if repo_url.startswith(('http://', 'https://', 'git@')):
                    if os.path.exists(agent_dir):
                        # Update existing repo
                        try:
                            repo = git.Repo(agent_dir)
                            repo.remotes.origin.pull()
                        except Exception as e:
                            # If failed to pull, remove and clone fresh
                            shutil.rmtree(agent_dir)
                            git.Repo.clone_from(repo_url, agent_dir)
                    else:
                        # Clone new repo
                        os.makedirs(agent_dir, exist_ok=True)
                        git.Repo.clone_from(repo_url, agent_dir)
                else:
                    # If it's not a URL, assume it's a local path or just create a directory
                    os.makedirs(agent_dir, exist_ok=True)
                    
                # Analyze repository structure
                repo_analysis = self._analyze_repository(agent_dir)
                
            except Exception as e:
                context['error'] = f"Failed to process repository: {str(e)}"
                return context
        
        # Store repository analysis in context
        context['repo'] = repo_analysis
        return context
    
    def _analyze_repository(self, repo_path: str) -> Dict[str, Any]:
        """Analyze repository structure to identify key components"""
        analysis = {
            'has_dockerfile': False,
            'env_files': [],
            'capabilities': [],
            'repo_path': repo_path
        }
        
        if not os.path.exists(repo_path):
            return analysis
            
        # Check for Dockerfile
        dockerfile_path = os.path.join(repo_path, 'Dockerfile')
        if os.path.exists(dockerfile_path):
            analysis['has_dockerfile'] = True
            
            # Parse Dockerfile to identify exposed ports
            with open(dockerfile_path, 'r') as f:
                content = f.read()
                # Look for EXPOSE directives
                expose_matches = re.findall(r'EXPOSE\s+(\d+)', content)
                if expose_matches:
                    analysis['exposed_ports'] = [int(port) for port in expose_matches]
        
        # Find env files
        for file in os.listdir(repo_path):
            if file.endswith('.env') or file.endswith('.env.example') or file.endswith('.env.template'):
                env_file_path = os.path.join(repo_path, file)
                env_vars = self._parse_env_file(env_file_path)
                analysis['env_files'].append({
                    'path': env_file_path,
                    'vars': env_vars
                })
        
        # Check for agent card or capabilities description
        agent_card_path = os.path.join(repo_path, 'agent_card.json')
        if os.path.exists(agent_card_path):
            try:
                with open(agent_card_path, 'r') as f:
                    card_data = json.load(f)
                    if 'capabilities' in card_data:
                        analysis['capabilities'] = card_data['capabilities']
            except:
                pass
                
        return analysis
    
    def _parse_env_file(self, env_file_path: str) -> List[Dict[str, str]]:
        """Parse an env file to extract variable names and default values"""
        env_vars = []
        
        if not os.path.exists(env_file_path):
            return env_vars
            
        with open(env_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                    
                # Extract variable name and optional value
                parts = line.split('=', 1)
                if len(parts) == 2:
                    var_name, var_value = parts
                    env_vars.append({
                        'name': var_name.strip(),
                        'default': var_value.strip() if var_value.strip() else None
                    })
                elif len(parts) == 1:
                    env_vars.append({
                        'name': parts[0].strip(),
                        'default': None
                    })
                    
        return env_vars

class CodingAgent:
    """
    Handles code generation and tool wiring for the agent.
    Creates or updates agent code files if needed.
    """
    name = "CodingAgent"
    
    def handle(self, context):
        agent_name = context.get('agent_name', '')
        repo_analysis = context.get('repo', {})
        repo_path = repo_analysis.get('repo_path', '')
        
        if not repo_path or not os.path.exists(repo_path):
            context['error'] = "Repository path not found or invalid"
            return context
            
        # Check if we need to scaffold any code
        if not repo_analysis.get('has_dockerfile', False):
            # Generate a basic Dockerfile if none exists
            dockerfile_path = os.path.join(repo_path, 'Dockerfile')
            with open(dockerfile_path, 'w') as f:
                f.write("""FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn pydantic requests
EXPOSE {port}
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
""".format(port=context.get('port', 8000)))
                
            # Generate a basic FastAPI app if none exists
            main_py_path = os.path.join(repo_path, 'main.py')
            if not os.path.exists(main_py_path):
                with open(main_py_path, 'w') as f:
                    f.write("""from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

app = FastAPI()

class InvokeRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    is_first_message: bool = False
    config: Optional[Dict[str, Any]] = None

@app.get('/health')
def health_check():
    return {"status": "ok"}

@app.post('/invoke')
async def invoke(request: InvokeRequest):
    # Process a message through the agent's logic and return the response
    try:
        # Add your agent logic here
        system_prompt = "{system_prompt}"
        
        # Simple implementation - in a real agent, you'd call your AI model here
        response = f"I am {agent_name}. You sent: {{request.message}}"
        
        return {{"response": response}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
""".format(
    agent_name=agent_name,
    system_prompt=context.get('system_prompt', 'You are a helpful AI agent.')
))
            
            # Generate a basic agent_card.json if none exists
            agent_card_path = os.path.join(repo_path, 'agent_card.json')
            if not os.path.exists(agent_card_path):
                with open(agent_card_path, 'w') as f:
                    json.dump({
                        "name": agent_name,
                        "description": context.get('description', f"A {agent_name} agent"),
                        "capabilities": context.get('capabilities', ["basic_response"]),
                        "endpoints": ["/invoke", "/health"],
                        "version": "1.0.0"
                    }, f, indent=2)
        
        # Store coding results
        context['code'] = {
            'files_generated': [],
            'files_updated': [],
            'status': 'complete'
        }
        
        return context

class ConfigAgent:
    """
    Handles configuration generation for the agent.
    Sets up environment files, config, and ensures proper port configuration.
    """
    name = "ConfigAgent"
    
    def handle(self, context):
        agent_name = context.get('agent_name', '')
        repo_analysis = context.get('repo', {})
        repo_path = repo_analysis.get('repo_path', '')
        
        if not repo_path or not os.path.exists(repo_path):
            context['error'] = "Repository path not found or invalid"
            return context
        
        # Setup agent directory in features/
        agent_dir = os.path.join(FEATURES_PATH, agent_name)
        os.makedirs(agent_dir, exist_ok=True)
        
        # Create agent_card.yaml in features/
        config = {
            'agent_name': agent_name,
            'system_prompt': context.get('system_prompt', 'You are a helpful AI agent.'),
            'repo_url': context.get('repo_url', ''),
            'docker_image': context.get('image', ''),
            'network': context.get('network', 'mightrag-net'),
            'port': context.get('port', 9000)
        }
        
        with open(os.path.join(agent_dir, 'agent_card.yaml'), 'w') as f:
            yaml.safe_dump(config, f, sort_keys=False)
        
        # Create .env file from template if env_files were found in repo
        env_files = repo_analysis.get('env_files', [])
        if env_files:
            for env_file in env_files:
                source_path = env_file.get('path', '')
                if source_path and os.path.exists(source_path):
                    # Create .env from .env.example or .env.template
                    if '.env.example' in source_path or '.env.template' in source_path:
                        target_path = os.path.join(repo_path, '.env')
                        shutil.copyfile(source_path, target_path)
        
        # Update docker-compose.yml
        self._update_docker_compose(context)
        
        # Store config generation results
        context['config'] = {
            'agent_card_yaml': os.path.join(agent_dir, 'agent_card.yaml'),
            'docker_compose_updated': True,
            'status': 'complete'
        }
        
        return context
    
    def _update_docker_compose(self, context: Dict[str, Any]) -> bool:
        """Update docker-compose.yml with the new agent configuration"""
        agent_name = context.get('agent_name', '')
        port = context.get('port', 9000)
        image = context.get('image', 'mightrag-agent-base:latest')
        network = context.get('network', 'mightrag-net')
        system_prompt = context.get('system_prompt', 'You are a helpful AI agent.')
        repo_url = context.get('repo_url', '')
        ssh_volume = context.get('ssh_volume', True)
        
        try:
            # Read existing docker-compose.yml
            with open(COMPOSE_PATH, 'r') as f:
                compose = yaml.safe_load(f) or {}
            
            # Ensure services section exists
            if 'services' not in compose:
                compose['services'] = {}
                
            # Create service block
            service_block = {
                'image': image,
                'container_name': f"rag-{agent_name}",
                'restart': 'unless-stopped',
                'networks': [network],
                'environment': {
                    'AGENT_NAME': agent_name,
                    'SYSTEM_PROMPT': system_prompt,
                    'REPO_URL': repo_url,
                    'MCP_PORT': str(port)
                },
                'ports': [f"{port}:{port}"]
            }
            
            if ssh_volume:
                service_block['volumes'] = ["shared-ssh:/home/rag/.ssh:ro"]
                
            # Add to services
            compose['services'][agent_name] = service_block
            
            # Ensure networks section exists and includes the specified network
            if 'networks' not in compose:
                compose['networks'] = {}
                
            if network not in compose['networks']:
                compose['networks'][network] = {
                    'driver': 'bridge'
                }
                
            # Ensure volumes section exists if using ssh_volume
            if ssh_volume and 'volumes' not in compose:
                compose['volumes'] = {
                    'shared-ssh': {'external': True}
                }
            elif ssh_volume and 'shared-ssh' not in compose.get('volumes', {}):
                if 'volumes' not in compose:
                    compose['volumes'] = {}
                compose['volumes']['shared-ssh'] = {'external': True}
            
            # Write updated docker-compose.yml
            with open(COMPOSE_PATH, 'w') as f:
                yaml.safe_dump(compose, f, sort_keys=False)
                
            return True
        except Exception as e:
            print(f"Error updating docker-compose.yml: {e}")
            return False

class RankingAgent:
    """
    Finalizes the onboarding process and runs any necessary checks.
    Tests the agent and ensures it's ready for use.
    """
    name = "RankingAgent"
    
    def handle(self, context):
        agent_name = context.get('agent_name', '')
        
        # Report any errors encountered during onboarding
        if 'error' in context:
            context['rank'] = {
                'status': 'failed',
                'error': context['error'],
                'recommendations': [
                    "Fix the error and try again",
                    "Check if the agent name or port is already in use",
                    "Verify that the repository URL is correct"
                ]
            }
            return context
            
        # Verify docker-compose.yml was updated
        if not os.path.exists(COMPOSE_PATH):
            context['rank'] = {
                'status': 'failed',
                'error': 'docker-compose.yml not found',
                'recommendations': [
                    "Create docker-compose.yml file",
                    "Verify file permissions"
                ]
            }
            return context
            
        with open(COMPOSE_PATH, 'r') as f:
            compose = yaml.safe_load(f) or {}
            if 'services' not in compose or agent_name not in compose.get('services', {}):
                context['rank'] = {
                    'status': 'failed',
                    'error': f"Agent '{agent_name}' not found in docker-compose.yml",
                    'recommendations': [
                        "Verify that ConfigAgent completed successfully",
                        "Check docker-compose.yml file permissions"
                    ]
                }
                return context
                
        # Store successful ranking results
        context['rank'] = {
            'status': 'success',
            'message': f"Agent '{agent_name}' successfully onboarded",
            'next_steps': [
                f"Start the agent with 'docker-compose up -d {agent_name}'",
                "Check agent health with 'docker logs rag-{agent_name}'",
                "Interact with the agent through the MCP system"
            ]
        }
        
        return context


# CLI Testing and Benchmarking functionality
class AgentTester:
    """Handles testing and benchmarking of deployed agents"""
    
    @staticmethod
    def test_agent(agent_name: str, port: int, test_query: str = "Hello") -> Dict[str, Any]:
        """Run a basic test against an agent and return the results"""
        import datetime
        import requests
        import uuid
        
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
            # Prepare test data
            test_data = {
                "message": test_query,
                "thread_id": f"{agent_name}_test_{uuid.uuid4().hex[:8]}",
                "is_first_message": True
            }
            
            # Make request to agent
            response = requests.post(
                f"http://localhost:{port}/invoke", 
                json=test_data,
                timeout=10
            )
            
            # Calculate response time
            end_time = datetime.datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000  # ms
            
            # Update result
            result["response_time_ms"] = round(response_time, 2)
            
            if response.status_code == 200:
                result["success"] = True
                result["response"] = response.json()
            else:
                result["error"] = f"Status code: {response.status_code}, Response: {response.text}"
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    @staticmethod
    def benchmark_agent(agent_name: str, port: int, num_requests: int = 5, interval_ms: int = 500) -> Dict[str, Any]:
        """Benchmark an agent with multiple requests and measure performance"""
        import datetime
        import time
        
        benchmark_results = {
            "agent_name": agent_name,
            "port": port,
            "timestamp": datetime.datetime.now().isoformat(),
            "num_requests": num_requests,
            "interval_ms": interval_ms,
            "tests": [],
            "summary": {
                "success_rate": 0,
                "avg_response_time_ms": 0,
                "min_response_time_ms": 0,
                "max_response_time_ms": 0
            }
        }
        
        # Test queries
        test_queries = [
            "Hello, who are you?",
            "What can you do?",
            "Tell me about yourself",
            "How do you work?",
            "What are your capabilities?"
        ]
        
        # Run tests
        successful_tests = 0
        response_times = []
        
        for i in range(num_requests):
            query_idx = i % len(test_queries)
            print(f"Running test {i+1}/{num_requests}: '{test_queries[query_idx]}'")
            
            test_result = AgentTester.test_agent(agent_name, port, test_queries[query_idx])
            benchmark_results["tests"].append(test_result)
            
            if test_result["success"]:
                successful_tests += 1
                response_times.append(test_result["response_time_ms"])
                print(f"✅ Success: {test_result['response_time_ms']}ms")
            else:
                print(f"❌ Failed: {test_result['error']}")
            
            # Wait between requests
            if i < num_requests - 1:
                time.sleep(interval_ms / 1000)  # Convert ms to seconds
        
        # Calculate summary statistics
        if response_times:
            benchmark_results["summary"]["success_rate"] = successful_tests / num_requests
            benchmark_results["summary"]["avg_response_time_ms"] = round(sum(response_times) / len(response_times), 2)
            benchmark_results["summary"]["min_response_time_ms"] = round(min(response_times), 2)
            benchmark_results["summary"]["max_response_time_ms"] = round(max(response_times), 2)
        
        return benchmark_results
    
    @staticmethod
    def get_agent_list() -> List[Dict[str, Any]]:
        """Get a list of all registered agents from docker-compose.yml"""
        agents = []
        
        try:
            if os.path.exists(COMPOSE_PATH):
                with open(COMPOSE_PATH, 'r') as f:
                    compose = yaml.safe_load(f) or {}
                    
                    for service_name, service in compose.get('services', {}).items():
                        # Only include services that are likely agents
                        if service_name.startswith(('agent_', 'rag-')) or service.get('container_name', '').startswith('rag-'):
                            port = None
                            for port_mapping in service.get('ports', []):
                                if isinstance(port_mapping, str) and ':' in port_mapping:
                                    port = int(port_mapping.split(':')[0])
                                    break
                            
                            agents.append({
                                "name": service_name,
                                "port": port,
                                "image": service.get('image', 'unknown'),
                                "container_name": service.get('container_name', f"rag-{service_name}")
                            })
        except Exception as e:
            print(f"Error retrieving agent list: {e}")
        
        return agents
    
    @staticmethod
    def display_benchmark_results(results: Dict[str, Any], json_output: bool = False):
        """Display benchmark results in a readable format"""
        import json
        
        if json_output:
            print(json.dumps(results, indent=2))
            return
        
        # Text output
        summary = results["summary"]
        success_rate = summary.get("success_rate", 0) * 100
        
        print("\n" + "=" * 60)
        print(f"📊 BENCHMARK RESULTS FOR '{results['agent_name']}'")
        print("=" * 60)
        
        print(f"\nSUMMARY:")
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"Avg Response Time: {summary.get('avg_response_time_ms', 0)}ms")
        print(f"Min Response Time: {summary.get('min_response_time_ms', 0)}ms")
        print(f"Max Response Time: {summary.get('max_response_time_ms', 0)}ms")
        print(f"Total Requests: {results.get('num_requests', 0)}")
        print(f"Request Interval: {results.get('interval_ms', 0)}ms")
        
        print("\nDETAILED RESULTS:")
        for i, test in enumerate(results.get("tests", [])):
            status = "✅ Success" if test.get("success") else "❌ Failed"
            response_time = f"{test.get('response_time_ms')}ms" if test.get("response_time_ms") else "N/A"
            
            print(f"Test #{i+1}: {status} | {response_time} | Query: '{test.get('query', '')[:50]}'")
        
        # Sample response
        success_tests = [t for t in results.get("tests", []) if t.get("success")]
        if success_tests:
            print("\nSAMPLE RESPONSE:")
            print(json.dumps(success_tests[0]["response"], indent=2))


# Command-line interface for onboarding and testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Agent Onboarding and Testing CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Onboard command
    onboard_parser = subparsers.add_parser("onboard", help="Onboard a new agent")
    onboard_parser.add_argument("--name", required=True, help="Agent name")
    onboard_parser.add_argument("--port", type=int, default=9000, help="Port for the agent")
    onboard_parser.add_argument("--repo", required=True, help="Repository URL or path")
    onboard_parser.add_argument("--prompt", default="You are a helpful AI agent.", help="System prompt")
    onboard_parser.add_argument("--image", default="mightrag-agent-base:latest", help="Docker image")
    onboard_parser.add_argument("--network", default="mightrag-net", help="Docker network")
    onboard_parser.add_argument("--ssh", action="store_true", help="Mount SSH volume")
    
    # List agents command
    list_parser = subparsers.add_parser("list", help="List available agents")
    
    # Test agent command
    test_parser = subparsers.add_parser("test", help="Test an agent")
    test_parser.add_argument("agent", help="Agent name to test")
    test_parser.add_argument("--port", type=int, help="Override port from docker-compose.yml")
    test_parser.add_argument("--query", default="Hello, who are you?", help="Test query")
    
    # Benchmark agent command
    benchmark_parser = subparsers.add_parser("benchmark", help="Benchmark an agent")
    benchmark_parser.add_argument("agent", help="Agent name to benchmark")
    benchmark_parser.add_argument("--port", type=int, help="Override port from docker-compose.yml")
    benchmark_parser.add_argument("--requests", type=int, default=5, help="Number of requests")
    benchmark_parser.add_argument("--interval", type=int, default=500, help="Interval between requests (ms)")
    benchmark_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    benchmark_parser.add_argument("--output", help="Save results to file")
    
    args = parser.parse_args()
    
    if args.command == "onboard":
        # Onboard a new agent
        print(f"Onboarding agent '{args.name}'...")
        
        onboarding_context = {
            'agent_name': args.name,
            'port': args.port,
            'system_prompt': args.prompt,
            'repo_url': args.repo,
            'image': args.image,
            'network': args.network,
            'ssh_volume': args.ssh,
            'description': f"Agent created via CLI"
        }
        
        onboarder = OnboardingGraph()
        result = onboarder.onboard(onboarding_context)
        
        if 'error' in result:
            print(f"\n❌ Onboarding failed: {result['error']}")
            sys.exit(1)
        
        # Print completion message
        if 'rank' in result and result['rank'].get('status') == 'success':
            print(f"\n✅ {result['rank'].get('message', 'Agent successfully onboarded')}")
            print("\nNext steps:")
            for step in result['rank'].get('next_steps', []):
                print(f"  - {step}")
        else:
            print("\n⚠️ Onboarding completed but with potential issues.")
    
    elif args.command == "list":
        # List available agents
        agents = AgentTester.get_agent_list()
        
        if not agents:
            print("No agents found in docker-compose.yml")
            sys.exit(0)
        
        print("\nAvailable Agents:")
        print("-" * 80)
        print(f"{'Name':<20} {'Port':<10} {'Container':<30} {'Image':<20}")
        print("-" * 80)
        
        for agent in agents:
            print(f"{agent['name']:<20} {agent['port'] or 'N/A':<10} {agent['container_name']:<30} {agent['image']:<20}")
    
    elif args.command == "test":
        # Test an agent
        agents = AgentTester.get_agent_list()
        agent = next((a for a in agents if a["name"] == args.agent), None)
        
        if not agent:
            print(f"❌ Agent '{args.agent}' not found")
            sys.exit(1)
        
        port = args.port if args.port else agent["port"]
        
        if not port:
            print(f"❌ No port specified for agent '{args.agent}'")
            sys.exit(1)
        
        print(f"Testing agent '{args.agent}' on port {port}...")
        print(f"Query: {args.query}\n")
        
        result = AgentTester.test_agent(args.agent, port, args.query)
        
        if result["success"]:
            print(f"✅ Test successful in {result['response_time_ms']}ms")
            print("\nResponse:")
            import json
            print(json.dumps(result["response"], indent=2))
        else:
            print(f"❌ Test failed: {result['error']}")
    
    elif args.command == "benchmark":
        # Benchmark an agent
        agents = AgentTester.get_agent_list()
        agent = next((a for a in agents if a["name"] == args.agent), None)
        
        if not agent:
            print(f"❌ Agent '{args.agent}' not found")
            sys.exit(1)
        
        port = args.port if args.port else agent["port"]
        
        if not port:
            print(f"❌ No port specified for agent '{args.agent}'")
            sys.exit(1)
        
        print(f"Benchmarking agent '{args.agent}' on port {port}...")
        print(f"Requests: {args.requests} with {args.interval}ms interval\n")
        
        results = AgentTester.benchmark_agent(args.agent, port, args.requests, args.interval)
        
        # Display results
        AgentTester.display_benchmark_results(results, args.json)
        
        # Save results if output file specified
        if args.output:
            import json
            try:
                with open(args.output, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"\nResults saved to {args.output}")
            except Exception as e:
                print(f"\n❌ Error saving results: {e}")
    
    else:
        parser.print_help()
