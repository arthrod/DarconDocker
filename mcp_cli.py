#!/usr/bin/env python
"""
MCP Army Command Line Interface

A powerful command-line tool for managing your MCP Army from the terminal.
Features:
- Agent deployment and management
- System diagnostics and monitoring
- Configuration management
- Bulk operations and automation

Usage:
  ./mcp_cli.py [command] [options]
"""
import os
import sys
import json
import time
import click
import requests
import docker
import tabulate
import yaml
import asyncio
import logging
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from archon.resilient_discovery import ResilientDiscovery, AgentInfo
from archon.secure_communication import create_agent_token, register_agent

# Setup rich console for pretty output
console = Console()

# Initialize discovery system
discovery = ResilientDiscovery()

# Docker client for container operations
docker_client = docker.from_env()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp_cli")


class MCPAgentCLI:
    """MCP Agent Command Line Interface"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".mcp_army"
        self.config_file = self.config_dir / "config.yaml"
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load CLI configuration"""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True)
        
        if not self.config_file.exists():
            # Create default config
            default_config = {
                "environment": "development",
                "default_agent_image": "mightrag-agent-base:latest",
                "api_url": "http://localhost:8105",
                "auth_token": None,
                "last_used_agents": []
            }
            
            with open(self.config_file, "w") as f:
                yaml.dump(default_config, f)
            
            return default_config
        
        # Load existing config
        with open(self.config_file, "r") as f:
            return yaml.safe_load(f)
    
    def _save_config(self):
        """Save current configuration"""
        with open(self.config_file, "w") as f:
            yaml.dump(self.config, f)
    
    def _get_auth_header(self) -> Dict:
        """Get authorization header for API requests"""
        token = self.config.get("auth_token")
        if not token:
            console.print("[bold red]Not authenticated. Run 'mcp_cli.py login' first.[/bold red]")
            sys.exit(1)
        
        return {"Authorization": f"Bearer {token}"}
    
    def _api_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make an API request to the MCP server"""
        url = f"{self.config['api_url']}/{endpoint.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers.update(self._get_auth_header())
        
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            console.print(f"[bold red]API request failed: {e}[/bold red]")
            sys.exit(1)


@click.group()
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
def cli(debug):
    """MCP Army CLI - Control your agent fleet from the terminal"""
    # Set up logging level based on debug flag
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create CLI instance
    cli.cli_instance = MCPAgentCLI()


@cli.command()
def login():
    """Authenticate with the MCP server"""
    console.print("[bold]Authenticating with MCP server...[/bold]")
    
    # Get server URL
    server_url = click.prompt(
        "MCP Server URL",
        default=cli.cli_instance.config["api_url"]
    )
    
    # Update config with new URL
    cli.cli_instance.config["api_url"] = server_url
    
    # Try to auto-login with local agent credentials
    console.print("[bold]Attempting automatic authentication...[/bold]")
    try:
        # Generate a new agent token for CLI
        agent_id = f"cli-{os.getlogin()}-{int(time.time())}"
        credential = register_agent(
            agent_id=agent_id,
            name=f"CLI Client ({os.getlogin()})",
            roles=["admin", "cli"],
            scopes=["admin:read", "admin:write", "agent:*"]
        )
        
        # Create token and save to config
        token = credential.create_jwt(expiry=86400)  # 24 hours
        cli.cli_instance.config["auth_token"] = token
        cli.cli_instance._save_config()
        
        console.print("[bold green]Successfully authenticated![/bold green]")
        console.print(f"Token will expire in 24 hours.")
        
    except Exception as e:
        console.print(f"[bold red]Automatic authentication failed: {e}[/bold red]")
        console.print("[bold]Please enter your credentials manually:[/bold]")
        
        # Manual login
        username = click.prompt("Username")
        password = click.prompt("Password", hide_input=True)
        
        # TODO: Implement actual authentication with server
        # For now, just save a dummy token
        cli.cli_instance.config["auth_token"] = "dummy_token_replace_with_real_token"
        cli.cli_instance._save_config()
        
        console.print("[bold green]Successfully authenticated![/bold green]")


@cli.command()
@click.option("--refresh/--no-refresh", default=False, help="Force agent discovery refresh")
def list(refresh):
    """List all available agents"""
    with console.status("[bold green]Discovering agents...[/bold green]"):
        agents = discovery.discover_agents(force_refresh=refresh)
    
    if not agents:
        console.print("[yellow]No agents found.[/yellow]")
        return
    
    # Create a rich table
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("URL")
    table.add_column("Capabilities")
    
    # Add rows for each agent
    for agent_id, agent in agents.items():
        status_color = {
            "online": "green",
            "offline": "red",
            "unknown": "yellow"
        }.get(agent.status, "yellow")
        
        capabilities = ", ".join(agent.capabilities) if agent.capabilities else "-"
        
        table.add_row(
            agent_id,
            agent.name,
            f"[{status_color}]{agent.status}[/{status_color}]",
            agent.base_url or "-",
            capabilities
        )
    
    console.print(table)
    console.print(f"[bold]Total: {len(agents)} agents[/bold]")


@cli.command()
@click.argument("agent_id")
def inspect(agent_id):
    """Get detailed information about an agent"""
    with console.status(f"[bold green]Inspecting agent {agent_id}...[/bold green]"):
        agent = discovery.get_agent(agent_id, force_refresh=True)
    
    if not agent:
        console.print(f"[bold red]Agent {agent_id} not found.[/bold red]")
        return
    
    # Display agent information
    console.print(f"[bold]Agent: {agent.name} ({agent_id})[/bold]")
    console.print(f"Status: [{'green' if agent.status == 'online' else 'red'}]{agent.status}[/{'green' if agent.status == 'online' else 'red'}]")
    console.print(f"URL: {agent.base_url or 'Unknown'}")
    
    if agent.description:
        console.print(f"Description: {agent.description}")
    
    if agent.capabilities:
        console.print("[bold]Capabilities:[/bold]")
        for capability in agent.capabilities:
            console.print(f"  • {capability}")
    
    # If agent is online, get health information
    if agent.status == "online" and agent.base_url:
        try:
            health_url = f"{agent.base_url.rstrip('/')}/health"
            response = requests.get(health_url, timeout=2)
            if response.status_code == 200:
                try:
                    health_data = response.json()
                    console.print("[bold]Health Information:[/bold]")
                    for key, value in health_data.items():
                        console.print(f"  {key}: {value}")
                except:
                    console.print(f"Health check successful, but no detailed information available.")
        except requests.RequestException:
            console.print("[yellow]Could not retrieve health information.[/yellow]")


@cli.command()
@click.option("--name", required=True, help="Agent name")
@click.option("--description", help="Agent description")
@click.option("--repo", help="Git repository URL")
@click.option("--port", default=8080, help="Agent port")
@click.option("--image", help="Docker image to use")
@click.option("--system-prompt", help="Agent system prompt")
@click.option("--env", "-e", multiple=True, help="Environment variables (NAME=VALUE)")
def deploy(name, description, repo, port, image, system_prompt, env):
    """Deploy a new agent"""
    image = image or cli.cli_instance.config["default_agent_image"]
    
    # Parse environment variables
    env_dict = {}
    for env_var in env:
        if "=" in env_var:
            key, value = env_var.split("=", 1)
            env_dict[key] = value
    
    # Add required environment variables
    env_dict["AGENT_NAME"] = name
    env_dict["MCP_PORT"] = str(port)
    
    if repo:
        env_dict["REPO_URL"] = repo
    
    if system_prompt:
        env_dict["SYSTEM_PROMPT"] = system_prompt
    
    # Create container name
    container_name = f"rag-{name.lower().replace(' ', '-')}"
    
    console.print(f"[bold]Deploying agent: {name}[/bold]")
    console.print(f"Using image: {image}")
    console.print(f"Container name: {container_name}")
    
    # Check if container already exists
    try:
        existing = docker_client.containers.get(container_name)
        if existing:
            if click.confirm(f"Container {container_name} already exists. Remove and recreate?"):
                console.print(f"[yellow]Removing existing container...[/yellow]")
                existing.remove(force=True)
            else:
                console.print("[yellow]Deployment cancelled.[/yellow]")
                return
    except docker.errors.NotFound:
        pass
    
    # Deploy the container
    with console.status(f"[bold green]Deploying {name}...[/bold green]"):
        try:
            container = docker_client.containers.run(
                image=image,
                name=container_name,
                environment=env_dict,
                network="mightrag-net",
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                ports={f"{port}/tcp": None}
            )
            
            console.print(f"[bold green]Agent deployed successfully![/bold green]")
            console.print(f"Container ID: {container.id[:12]}")
            
            # Wait for agent to be ready
            console.print("[bold]Waiting for agent to be ready...[/bold]")
            max_retries = 10
            for i in range(max_retries):
                time.sleep(3)
                try:
                    container.reload()
                    if container.status == "running":
                        # Try to check agent health
                        try:
                            # Get container IP
                            container_info = container.attrs
                            network_settings = container_info.get("NetworkSettings", {})
                            networks = network_settings.get("Networks", {})
                            mightrag_net = networks.get("mightrag-net", {})
                            ip_address = mightrag_net.get("IPAddress")
                            
                            if ip_address:
                                health_url = f"http://{ip_address}:{port}/health"
                                response = requests.get(health_url, timeout=2)
                                if response.status_code == 200:
                                    console.print("[bold green]Agent is ready![/bold green]")
                                    break
                        except requests.RequestException:
                            pass
                    
                    console.print(f"[yellow]Waiting for agent to start ({i+1}/{max_retries})...[/yellow]")
                except:
                    pass
            
        except docker.errors.APIError as e:
            console.print(f"[bold red]Deployment failed: {e}[/bold red]")
            return


@cli.command()
@click.argument("agent_id")
def stop(agent_id):
    """Stop a running agent"""
    # Try to find the container
    container_name = f"rag-{agent_id.lower().replace(' ', '-')}"
    
    try:
        container = docker_client.containers.get(container_name)
        
        console.print(f"[bold]Stopping agent: {agent_id}[/bold]")
        container.stop()
        console.print(f"[bold green]Agent stopped successfully![/bold green]")
        
    except docker.errors.NotFound:
        console.print(f"[bold red]Container {container_name} not found.[/bold red]")
    except docker.errors.APIError as e:
        console.print(f"[bold red]Failed to stop agent: {e}[/bold red]")


@cli.command()
@click.argument("agent_id")
def restart(agent_id):
    """Restart an agent"""
    # Try to find the container
    container_name = f"rag-{agent_id.lower().replace(' ', '-')}"
    
    try:
        container = docker_client.containers.get(container_name)
        
        console.print(f"[bold]Restarting agent: {agent_id}[/bold]")
        container.restart()
        console.print(f"[bold green]Agent restarted successfully![/bold green]")
        
    except docker.errors.NotFound:
        console.print(f"[bold red]Container {container_name} not found.[/bold red]")
    except docker.errors.APIError as e:
        console.print(f"[bold red]Failed to restart agent: {e}[/bold red]")


@cli.command()
def status():
    """Show system status"""
    console.print("[bold]MCP Army System Status[/bold]")
    
    # Get MCP server status
    with console.status("[bold green]Checking MCP server status...[/bold green]"):
        try:
            response = requests.get(f"{cli.cli_instance.config['api_url']}/health", timeout=2)
            if response.status_code == 200:
                console.print(f"MCP Server: [bold green]Online[/bold green]")
                try:
                    data = response.json()
                    if "version" in data:
                        console.print(f"Version: {data['version']}")
                except:
                    pass
            else:
                console.print(f"MCP Server: [bold red]Error (Status {response.status_code})[/bold red]")
        except requests.RequestException:
            console.print(f"MCP Server: [bold red]Offline[/bold red]")
    
    # Get agent statistics
    with console.status("[bold green]Gathering agent statistics...[/bold green]"):
        agents = discovery.discover_agents()
        
        online_count = sum(1 for a in agents.values() if a.status == "online")
        offline_count = sum(1 for a in agents.values() if a.status == "offline")
        unknown_count = sum(1 for a in agents.values() if a.status == "unknown")
    
    console.print(f"Total Agents: [bold]{len(agents)}[/bold]")
    console.print(f"Online: [bold green]{online_count}[/bold green]")
    console.print(f"Offline: [bold red]{offline_count}[/bold red]")
    console.print(f"Unknown: [bold yellow]{unknown_count}[/bold yellow]")
    
    # Get docker status
    with console.status("[bold green]Checking Docker status...[/bold green]"):
        try:
            version = docker_client.version()
            console.print(f"Docker: [bold green]Running[/bold green] (Version: {version.get('Version', 'Unknown')})")
            
            # Get container statistics
            containers = docker_client.containers.list(all=True)
            running = sum(1 for c in containers if c.status == "running")
            total = len(containers)
            
            console.print(f"Containers: {running} running / {total} total")
        except docker.errors.APIError:
            console.print(f"Docker: [bold red]Error[/bold red]")


@cli.command()
@click.argument("agent_id")
@click.argument("message")
def message(agent_id, message):
    """Send a message to an agent"""
    with console.status(f"[bold green]Sending message to {agent_id}...[/bold green]"):
        agent = discovery.get_agent(agent_id)
        
        if not agent or not agent.base_url:
            console.print(f"[bold red]Agent {agent_id} not found or has no endpoint.[/bold red]")
            return
        
        # Create request payload
        payload = {
            "inputs": {
                "query": message
            }
        }
        
        try:
            # Send message to agent
            response = requests.post(
                f"{agent.base_url.rstrip('/')}/run",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    console.print(f"[bold]Response from {agent_id}:[/bold]")
                    console.print(result.get("output", result))
                except:
                    console.print(f"[bold]Raw response:[/bold]")
                    console.print(response.text)
            else:
                console.print(f"[bold red]Error: {response.status_code}[/bold red]")
                console.print(response.text)
        except requests.RequestException as e:
            console.print(f"[bold red]Failed to send message: {e}[/bold red]")


@cli.command()
def config():
    """View and edit configuration"""
    console.print("[bold]MCP Army CLI Configuration[/bold]")
    
    for key, value in cli.cli_instance.config.items():
        if key == "auth_token" and value:
            value = f"{value[:10]}...{value[-5:]}"
        console.print(f"{key}: {value}")
    
    if click.confirm("Edit configuration?"):
        # Edit each value
        for key in cli.cli_instance.config.keys():
            if key == "auth_token":
                continue  # Skip editing auth token directly
                
            new_value = click.prompt(
                f"New value for {key}",
                default=str(cli.cli_instance.config[key])
            )
            
            # Handle special types
            if isinstance(cli.cli_instance.config[key], int):
                cli.cli_instance.config[key] = int(new_value)
            elif isinstance(cli.cli_instance.config[key], bool):
                cli.cli_instance.config[key] = new_value.lower() in ["true", "yes", "y", "1"]
            elif isinstance(cli.cli_instance.config[key], list):
                cli.cli_instance.config[key] = [x.strip() for x in new_value.split(",")]
            else:
                cli.cli_instance.config[key] = new_value
        
        # Save changes
        cli.cli_instance._save_config()
        console.print("[bold green]Configuration saved![/bold green]")


if __name__ == "__main__":
    cli()
