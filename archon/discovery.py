# discovery.py
"""
Utility for dynamic agent discovery, registration, and communication.

This module provides functions to discover available agents through multiple methods:
1. Static discovery via docker-compose.yml
2. Dynamic discovery via A2A cards in the features directory
3. Runtime discovery via Agent Notice Board

The discovered agents can be registered as LangGraph nodes or accessed directly
via their endpoints for agent-to-agent (A2A) communication.
"""
import os
import json
import yaml
import logging
import requests
from typing import Dict, List, Any, Optional, Callable, Tuple
from pathlib import Path
from .agent_node import agent_node

try:
    from .agent_notice_board_client import AgentNoticeBoardClient
except ImportError:
    # Mock for when running outside the full environment
    class AgentNoticeBoardClient:
        def __init__(self, *args, **kwargs):
            pass
        def get_notices(self, *args, **kwargs):
            return []

# Constants
FEATURES_PATH = Path(__file__).parent.parent / "features"
COMPOSE_PATH = Path(__file__).parent.parent / "docker-compose.yml"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentInfo:
    """Class to hold agent information from various discovery sources"""
    
    def __init__(self, agent_id: str, name: str = None, endpoint: str = None, 
                 host: str = None, port: int = None, capabilities: List[str] = None,
                 description: str = None, status: str = "unknown", metadata: Dict = None):
        self.agent_id = agent_id
        self.name = name or agent_id
        self.endpoint = endpoint
        self.host = host
        self.port = port
        self.capabilities = capabilities or []
        self.description = description or ""
        self.status = status
        self.metadata = metadata or {}
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "endpoint": self.endpoint,
            "host": self.host,
            "port": self.port,
            "capabilities": self.capabilities,
            "description": self.description,
            "status": self.status,
            "metadata": self.metadata
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentInfo':
        """Create from dictionary representation"""
        return cls(
            agent_id=data["agent_id"],
            name=data.get("name"),
            endpoint=data.get("endpoint"),
            host=data.get("host"),
            port=data.get("port"),
            capabilities=data.get("capabilities"),
            description=data.get("description"),
            status=data.get("status", "unknown"),
            metadata=data.get("metadata", {})
        )
    
    @classmethod
    def from_a2a_card(cls, a2a_data: Dict[str, Any]) -> 'AgentInfo':
        """Create from A2A card format"""
        # Extract endpoint from endpoints object
        endpoints = a2a_data.get("endpoints", {})
        endpoint = endpoints.get("invoke") if endpoints else None
        
        # Parse host and port from endpoint if available
        host, port = None, None
        if endpoint and "://" in endpoint:
            try:
                url_parts = endpoint.split("://")[1].split(":")
                if len(url_parts) >= 2:
                    host = url_parts[0]
                    port = int(url_parts[1].split("/")[0])
            except (ValueError, IndexError):
                pass
        
        return cls(
            agent_id=a2a_data.get("agent_id"),
            name=a2a_data.get("agent_name"),
            endpoint=endpoint,
            host=host,
            port=port,
            capabilities=a2a_data.get("capabilities", []),
            description=a2a_data.get("description", ""),
            status="available",
            metadata=a2a_data.get("metadata", {})
        )
    
    def test_health(self) -> bool:
        """Test if the agent is healthy by calling its health endpoint"""
        if not self.endpoint:
            return False
        
        try:
            # Extract base URL without the /invoke part
            base_url = self.endpoint.split("/invoke")[0] if "/invoke" in self.endpoint else self.endpoint
            health_endpoint = f"{base_url}/health"
            
            response = requests.get(health_endpoint, timeout=2)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed for agent {self.agent_id}: {e}")
            return False


def discover_agents_from_compose(compose_path: str = None) -> Dict[str, AgentInfo]:
    """
    Discover agents from docker-compose.yml
    
    Args:
        compose_path: Path to docker-compose.yml file
        
    Returns:
        Dictionary mapping agent_id to AgentInfo
    """
    compose_file = Path(compose_path) if compose_path else COMPOSE_PATH
    
    try:
        with open(compose_file, 'r') as f:
            compose = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading docker-compose.yml: {e}")
        return {}
    
    agents = {}
    
    for svc, cfg in compose.get('services', {}).items():
        # Skip services that don't seem to be agents
        is_agent = (
            'ports' in cfg and 
            ('build' in cfg or 'image' in cfg) and
            (svc.startswith(('agent_', 'rag-')) or 
             cfg.get('container_name', '').startswith('rag-'))
        )
        
        if not is_agent:
            continue
            
        # Extract port mapping (host:container)
        port = None
        for port_mapping in cfg.get('ports', []):
            if isinstance(port_mapping, str) and ':' in port_mapping:
                port = int(port_mapping.split(":")[0])
                break
        
        if not port:
            continue
            
        # Create agent info
        host = svc  # In Docker network, service name is the hostname
        endpoint = f"http://{host}:{port}/invoke"
        
        # Extract metadata from environment
        env_vars = cfg.get('environment', {})
        metadata = {}
        description = ""
        
        if isinstance(env_vars, dict):
            description = env_vars.get('AGENT_DESCRIPTION', '')
            
        if isinstance(env_vars, list):
            # Handle list format (KEY=VALUE)
            for env in env_vars:
                if isinstance(env, str) and '=' in env:
                    key, value = env.split('=', 1)
                    if key == 'AGENT_DESCRIPTION':
                        description = value
        
        agents[svc] = AgentInfo(
            agent_id=svc,
            name=cfg.get('container_name', svc).replace('rag-', ''),
            endpoint=endpoint,
            host=host,
            port=port,
            description=description,
            status="running",
            metadata={
                "image": cfg.get('image', ''),
                "container_name": cfg.get('container_name', f"rag-{svc}")
            }
        )
    
    return agents


def discover_agents_from_a2a_cards(features_path: str = None) -> Dict[str, AgentInfo]:
    """
    Discover agents from A2A cards in the features directory
    
    Args:
        features_path: Path to features directory
        
    Returns:
        Dictionary mapping agent_id to AgentInfo
    """
    features_dir = Path(features_path) if features_path else FEATURES_PATH
    
    if not features_dir.exists():
        logger.warning(f"Features directory not found: {features_dir}")
        return {}
    
    agents = {}
    
    # Scan all subdirectories in features
    for agent_dir in features_dir.iterdir():
        if not agent_dir.is_dir():
            continue
            
        # Look for A2A card files (json or yaml)
        a2a_files = list(agent_dir.glob("*_a2a_card.json"))
        
        if not a2a_files:
            # Check for agent_card.yaml and convert to A2A format
            card_file = agent_dir.joinpath("agent_card.yaml")
            if card_file.exists():
                try:
                    with open(card_file, 'r') as f:
                        card_data = yaml.safe_load(f)
                        
                    # Convert agent_card.yaml to A2A format
                    port = card_data.get('port', 9000)
                    agent_name = card_data.get('agent_name', agent_dir.name)
                    
                    a2a_data = {
                        "agent_id": agent_name,
                        "agent_name": agent_name,
                        "description": card_data.get('description', f"Agent created from {agent_name}"),
                        "capabilities": ["basic_response", "text_processing"],
                        "endpoints": {
                            "invoke": f"http://localhost:{port}/invoke",
                            "health": f"http://localhost:{port}/health"
                        },
                        "metadata": {
                            "docker_image": card_data.get('docker_image', ''),
                            "repo_url": card_data.get('repo_url', '')
                        }
                    }
                    
                    agents[agent_name] = AgentInfo.from_a2a_card(a2a_data)
                except Exception as e:
                    logger.warning(f"Error processing agent card {card_file}: {e}")
            continue
            
        # Process A2A card files
        for a2a_file in a2a_files:
            try:
                with open(a2a_file, 'r') as f:
                    a2a_data = json.load(f)
                    
                agent_id = a2a_data.get("agent_id")
                if not agent_id:
                    continue
                    
                agents[agent_id] = AgentInfo.from_a2a_card(a2a_data)
            except Exception as e:
                logger.warning(f"Error processing A2A card {a2a_file}: {e}")
    
    return agents


def discover_agents_from_notice_board() -> Dict[str, AgentInfo]:
    """
    Discover agents from the Agent Notice Board
    
    Returns:
        Dictionary mapping agent_id to AgentInfo
    """
    try:
        notice_client = AgentNoticeBoardClient()
        
        # Get registration notices
        notices = notice_client.get_notices({
            "notice_type": "agent_registration"
        }, limit=100)
        
        agents = {}
        
        for notice in notices:
            try:
                agent_id = notice.get("agent_id")
                payload = notice.get("payload", {})
                
                if not agent_id or not payload:
                    continue
                
                # Convert notice payload to AgentInfo
                if "agent_info" in payload:
                    # Direct AgentInfo format
                    agent_info = AgentInfo.from_dict(payload["agent_info"])
                elif "a2a_card" in payload:
                    # A2A card format
                    agent_info = AgentInfo.from_a2a_card(payload["a2a_card"])
                else:
                    # Try to extract basic info
                    endpoint = payload.get("endpoint")
                    if not endpoint:
                        continue
                        
                    agent_info = AgentInfo(
                        agent_id=agent_id,
                        name=payload.get("name", agent_id),
                        endpoint=endpoint,
                        description=payload.get("description", ""),
                        capabilities=payload.get("capabilities", []),
                        status="registered"
                    )
                
                agents[agent_id] = agent_info
            except Exception as e:
                logger.warning(f"Error processing notice: {e}")
        
        return agents
    except Exception as e:
        logger.warning(f"Error accessing Agent Notice Board: {e}")
        return {}


def discover_agents(include_compose: bool = True, include_a2a: bool = True, 
                  include_notice_board: bool = True, test_health: bool = False) -> Dict[str, AgentInfo]:
    """
    Discover all available agents from multiple sources and combine results
    
    Args:
        include_compose: Whether to include agents from docker-compose.yml
        include_a2a: Whether to include agents from A2A cards
        include_notice_board: Whether to include agents from the Notice Board
        test_health: Whether to test agent health
        
    Returns:
        Dictionary mapping agent_id to AgentInfo
    """
    agents = {}
    
    # Discover from docker-compose.yml
    if include_compose:
        compose_agents = discover_agents_from_compose()
        agents.update(compose_agents)
    
    # Discover from A2A cards
    if include_a2a:
        a2a_agents = discover_agents_from_a2a_cards()
        for agent_id, agent_info in a2a_agents.items():
            if agent_id in agents:
                # Merge data, preferring docker-compose for endpoint info
                existing = agents[agent_id]
                agent_info.endpoint = existing.endpoint or agent_info.endpoint
                agent_info.host = existing.host or agent_info.host
                agent_info.port = existing.port or agent_info.port
                agent_info.status = existing.status
                
                # Merge metadata
                merged_metadata = {**agent_info.metadata, **existing.metadata}
                agent_info.metadata = merged_metadata
            
            agents[agent_id] = agent_info
    
    # Discover from Notice Board
    if include_notice_board:
        notice_agents = discover_agents_from_notice_board()
        for agent_id, agent_info in notice_agents.items():
            if agent_id in agents:
                # Update status to active
                agents[agent_id].status = "active"
                
                # Keep existing endpoint info if available
                if not agents[agent_id].endpoint and agent_info.endpoint:
                    agents[agent_id].endpoint = agent_info.endpoint
                    agents[agent_id].host = agent_info.host
                    agents[agent_id].port = agent_info.port
            else:
                agents[agent_id] = agent_info
    
    # Test health if requested
    if test_health:
        for agent_id, agent_info in agents.items():
            if agent_info.test_health():
                agent_info.status = "healthy"
            elif agent_info.status != "unknown":
                agent_info.status = "unhealthy"
    
    return agents


def get_agent_node_functions(agents: Dict[str, AgentInfo] = None) -> Dict[str, Callable]:
    """
    Get LangGraph node functions for discovered agents
    
    Args:
        agents: Dictionary of discovered agents, or None to discover them
        
    Returns:
        Dictionary mapping agent_id to node function
    """
    if agents is None:
        agents = discover_agents()
    
    node_fns = {}
    
    for agent_id, agent_info in agents.items():
        if agent_info.endpoint:
            node_fns[agent_id] = agent_node(agent_info.endpoint)
    
    return node_fns


# Backwards compatibility
def discover_agents_legacy(compose_path="../docker-compose.yml"):
    """
    Reads docker-compose.yml and returns a dict of service_name: LangGraph node_fn.
    Only includes services with 'build' and 'ports' defined.
    
    This function is maintained for backwards compatibility.
    """
    compose_file = Path(__file__).parent / compose_path
    with open(compose_file, 'r') as f:
        compose = yaml.safe_load(f)
    nodes = {}
    for svc, cfg in compose.get('services', {}).items():
        if 'build' in cfg and 'ports' in cfg:
            # Extract port mapping (host:container)
            port = str(cfg['ports'][0]).split(":")[0]
            url = f"http://{svc}:{port}"
            nodes[svc] = agent_node(url)
    return nodes
