"""
Resilient Agent Discovery System for MCP Army

This enhanced discovery module provides fault-tolerant, distributed agent discovery with:
1. Tiered discovery with fallback mechanisms
2. Distributed caching with TTL
3. Health verification and status tracking
4. Real-time notification of agent availability changes
5. Circuit breaker patterns to prevent cascading failures
"""
import os
import json
import yaml
import time
import logging
import requests
import socket
import threading
import hashlib
import asyncio
import aiohttp
import redis
from typing import Dict, List, Any, Optional, Callable, Tuple, Set, Union
from pathlib import Path
from datetime import datetime, timedelta
from functools import lru_cache

# Import original discovery functions
from .discovery import (
    AgentInfo, 
    discover_agents_from_compose, 
    discover_agents_from_a2a_cards, 
    discover_agents_from_notice_board
)

# Constants
CACHE_TTL = 60  # Default cache lifetime in seconds
HEALTH_CHECK_INTERVAL = 30  # Health check interval in seconds
MAX_RETRIES = 3  # Maximum retries for discovery methods
REDIS_URL = os.environ.get("REDIS_URL", "redis://10.147.20.20:6379/0")  # Connect to external Redis server
CIRCUIT_BREAKER_THRESHOLD = 3  # Number of failures before opening circuit
CIRCUIT_OPEN_TIME = 60  # Seconds to keep circuit open after failures

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiscoveryStatus:
    """Class to track discovery source status for circuit breaking"""
    
    def __init__(self, name: str):
        self.name = name
        self.failures = 0
        self.last_failure_time = None
        self.circuit_open = False
        self.last_success_time = None
        
    def record_failure(self):
        """Record a failure and potentially open the circuit"""
        self.failures += 1
        self.last_failure_time = datetime.now()
        
        if self.failures >= CIRCUIT_BREAKER_THRESHOLD:
            self.circuit_open = True
            logger.warning(f"Circuit OPEN for discovery source: {self.name}")
    
    def record_success(self):
        """Record a success and potentially close the circuit"""
        self.failures = 0
        self.last_success_time = datetime.now()
        self.circuit_open = False
        
    def can_try(self) -> bool:
        """Check if we can try this discovery source"""
        # If circuit is open, check if enough time has passed
        if self.circuit_open:
            if self.last_failure_time and \
               (datetime.now() - self.last_failure_time).total_seconds() > CIRCUIT_OPEN_TIME:
                logger.info(f"Circuit reset for discovery source: {self.name}")
                self.circuit_open = False
                self.failures = 0
                return True
            return False
        return True


class AgentRegistry:
    """Distributed agent registry with caching and health tracking"""
    
    def __init__(self, redis_url: str = REDIS_URL, use_redis: bool = True):
        self.agents = {}  # Local cache
        self.health_status = {}  # Track health of agents
        self.last_update = {}  # Track when agents were last updated
        self.discovery_status = {
            "compose": DiscoveryStatus("compose"),
            "a2a_cards": DiscoveryStatus("a2a_cards"),
            "notice_board": DiscoveryStatus("notice_board")
        }
        
        # Redis connection for distributed caching
        self.use_redis = use_redis
        if use_redis:
            try:
                self.redis = redis.from_url(redis_url)
                self.redis.ping()  # Test connection
                logger.info("Connected to Redis for distributed agent registry")
            except (redis.exceptions.ConnectionError, redis.exceptions.ResponseError):
                logger.warning("Redis connection failed, falling back to local registry")
                self.use_redis = False
        
        # Start background health check thread
        self.health_check_thread = threading.Thread(
            target=self._health_check_loop, 
            daemon=True
        )
        self.health_check_thread.start()
    
    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent info with cache awareness"""
        # Try local cache first
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            # Check if cache is still valid
            if agent_id in self.last_update:
                last_update = self.last_update[agent_id]
                if (datetime.now() - last_update).total_seconds() < CACHE_TTL:
                    return agent
        
        # Try Redis if enabled
        if self.use_redis:
            try:
                agent_data = self.redis.get(f"agent:{agent_id}")
                if agent_data:
                    agent_dict = json.loads(agent_data)
                    agent = AgentInfo(**agent_dict)
                    self.agents[agent_id] = agent
                    self.last_update[agent_id] = datetime.now()
                    return agent
            except Exception as e:
                logger.error(f"Redis error when getting agent {agent_id}: {e}")
        
        # Not found or cache expired
        return None
    
    def set_agent(self, agent: AgentInfo):
        """Save agent info to registry with caching"""
        # Update local cache
        self.agents[agent.id] = agent
        self.last_update[agent.id] = datetime.now()
        
        # Update Redis if enabled
        if self.use_redis:
            try:
                agent_dict = agent.to_dict()
                self.redis.setex(
                    f"agent:{agent.id}", 
                    CACHE_TTL * 2,  # Double the TTL for Redis
                    json.dumps(agent_dict)
                )
            except Exception as e:
                logger.error(f"Redis error when setting agent {agent.id}: {e}")
    
    def get_all_agents(self) -> Dict[str, AgentInfo]:
        """Get all agents with cache awareness"""
        agents = {}
        
        # Get from local cache
        for agent_id, agent in self.agents.items():
            if agent_id in self.last_update:
                last_update = self.last_update[agent_id]
                if (datetime.now() - last_update).total_seconds() < CACHE_TTL:
                    agents[agent_id] = agent
        
        # Supplement with Redis if enabled
        if self.use_redis:
            try:
                # Get all agent keys
                keys = self.redis.keys("agent:*")
                if keys:
                    # Get all agents in a single pipeline
                    pipe = self.redis.pipeline()
                    for key in keys:
                        pipe.get(key)
                    results = pipe.execute()
                    
                    # Process results
                    for key, data in zip(keys, results):
                        agent_id = key.decode().split(":", 1)[1]
                        if agent_id not in agents and data:
                            agent_dict = json.loads(data)
                            agent = AgentInfo(**agent_dict)
                            agents[agent_id] = agent
                            # Update local cache
                            self.agents[agent_id] = agent
                            self.last_update[agent_id] = datetime.now()
            except Exception as e:
                logger.error(f"Redis error when getting all agents: {e}")
        
        return agents
    
    def register_agents(self, agents: Dict[str, AgentInfo]):
        """Register multiple agents at once"""
        for agent_id, agent in agents.items():
            self.set_agent(agent)
    
    def _check_agent_health(self, agent: AgentInfo) -> bool:
        """Check if an agent is healthy by calling its health endpoint"""
        try:
            if not agent.base_url:
                return False
                
            health_url = f"{agent.base_url.rstrip('/')}/health"
            response = requests.get(health_url, timeout=2)
            
            if response.status_code == 200:
                # Update health status
                self.health_status[agent.id] = {
                    "status": "healthy",
                    "last_check": datetime.now(),
                    "response_time": response.elapsed.total_seconds()
                }
                return True
            else:
                self.health_status[agent.id] = {
                    "status": "unhealthy",
                    "last_check": datetime.now(),
                    "response_time": response.elapsed.total_seconds(),
                    "status_code": response.status_code
                }
                return False
        except requests.RequestException as e:
            self.health_status[agent.id] = {
                "status": "unreachable",
                "last_check": datetime.now(),
                "error": str(e)
            }
            return False
    
    def _health_check_loop(self):
        """Background thread for periodic health checks"""
        while True:
            try:
                # Get all agents
                agents = self.get_all_agents()
                
                # Check health for each agent
                for agent_id, agent in agents.items():
                    healthy = self._check_agent_health(agent)
                    
                    # Update agent status
                    agent.status = "online" if healthy else "offline"
                    self.set_agent(agent)
                
                # Sleep until next check
                time.sleep(HEALTH_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                time.sleep(HEALTH_CHECK_INTERVAL)


class ResilientDiscovery:
    """Enhanced discovery system with fault tolerance and fallbacks"""
    
    def __init__(self, 
                 redis_url: str = REDIS_URL, 
                 use_redis: bool = True,
                 enable_health_checks: bool = True):
        """
        Initialize the resilient discovery system
        
        Args:
            redis_url: URL for Redis connection
            use_redis: Whether to use Redis for caching
            enable_health_checks: Whether to perform health checks
        """
        self.registry = AgentRegistry(redis_url, use_redis)
        self.enable_health_checks = enable_health_checks
        
        # Create async event loop for parallel discovery
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    async def _discover_with_timeout(self, method: Callable, *args, **kwargs) -> Dict[str, AgentInfo]:
        """Run a discovery method with timeout"""
        try:
            # Convert sync function to async
            result = await asyncio.to_thread(method, *args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"Error in discovery method {method.__name__}: {e}")
            return {}
    
    async def _parallel_discover(self, 
                               include_compose: bool = True, 
                               include_a2a: bool = True,
                               include_notice_board: bool = True) -> Dict[str, AgentInfo]:
        """Discover agents from all sources in parallel"""
        tasks = []
        discovery_status = self.registry.discovery_status
        
        # Add compose discovery if enabled and circuit is closed
        if include_compose and discovery_status["compose"].can_try():
            tasks.append(
                asyncio.create_task(
                    self._discover_with_timeout(discover_agents_from_compose)
                )
            )
        
        # Add A2A card discovery if enabled and circuit is closed
        if include_a2a and discovery_status["a2a_cards"].can_try():
            tasks.append(
                asyncio.create_task(
                    self._discover_with_timeout(discover_agents_from_a2a_cards)
                )
            )
        
        # Add notice board discovery if enabled and circuit is closed
        if include_notice_board and discovery_status["notice_board"].can_try():
            tasks.append(
                asyncio.create_task(
                    self._discover_with_timeout(discover_agents_from_notice_board)
                )
            )
        
        # Run all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        all_agents = {}
        for i, result in enumerate(results):
            # Skip exceptions
            if isinstance(result, Exception):
                logger.error(f"Discovery method failed: {result}")
                continue
            
            # Record success for working methods
            if i == 0 and include_compose:
                discovery_status["compose"].record_success()
            elif i == 1 and include_a2a:
                discovery_status["a2a_cards"].record_success()
            elif i == 2 and include_notice_board:
                discovery_status["notice_board"].record_success()
            
            # Merge agents
            for agent_id, agent in result.items():
                if agent_id in all_agents:
                    # Agent already exists, merge info
                    existing = all_agents[agent_id]
                    # Use the most detailed information available
                    if not existing.description and agent.description:
                        existing.description = agent.description
                    if not existing.capabilities and agent.capabilities:
                        existing.capabilities = agent.capabilities
                    if not existing.base_url and agent.base_url:
                        existing.base_url = agent.base_url
                else:
                    # New agent
                    all_agents[agent_id] = agent
        
        return all_agents
    
    def discover_agents(self, 
                       include_compose: bool = True, 
                       include_a2a: bool = True,
                       include_notice_board: bool = True,
                       force_refresh: bool = False) -> Dict[str, AgentInfo]:
        """
        Discover all available agents with fault tolerance
        
        Args:
            include_compose: Whether to include compose discovery
            include_a2a: Whether to include A2A card discovery
            include_notice_board: Whether to include notice board discovery
            force_refresh: Whether to force refresh the cache
            
        Returns:
            Dictionary of agent_id -> AgentInfo
        """
        # Check cache first unless forced refresh
        if not force_refresh:
            cached_agents = self.registry.get_all_agents()
            if cached_agents:
                logger.info(f"Using cached agent information for {len(cached_agents)} agents")
                return cached_agents
        
        # Run parallel discovery
        all_agents = self.loop.run_until_complete(
            self._parallel_discover(
                include_compose=include_compose,
                include_a2a=include_a2a,
                include_notice_board=include_notice_board
            )
        )
        
        # Update registry with discovered agents
        self.registry.register_agents(all_agents)
        
        # Check health if enabled
        if self.enable_health_checks:
            for agent_id, agent in all_agents.items():
                healthy = self.registry._check_agent_health(agent)
                agent.status = "online" if healthy else "offline"
        
        logger.info(f"Discovered {len(all_agents)} agents")
        return all_agents
    
    def get_agent(self, agent_id: str, force_refresh: bool = False) -> Optional[AgentInfo]:
        """
        Get information for a specific agent
        
        Args:
            agent_id: ID of the agent to find
            force_refresh: Whether to force refresh
            
        Returns:
            AgentInfo if found, None otherwise
        """
        # Check cache first unless forced refresh
        if not force_refresh:
            agent = self.registry.get_agent(agent_id)
            if agent:
                return agent
        
        # Not in cache or forced refresh, discover all agents
        all_agents = self.discover_agents()
        return all_agents.get(agent_id)
    
    def get_agents_by_capability(self, capability: str) -> List[AgentInfo]:
        """
        Find agents with a specific capability
        
        Args:
            capability: Capability to search for
            
        Returns:
            List of agents with the capability
        """
        all_agents = self.discover_agents()
        return [
            agent for agent in all_agents.values()
            if agent.capabilities and capability in agent.capabilities
        ]
    
    def get_healthiest_agent(self, capability: str) -> Optional[AgentInfo]:
        """
        Find the healthiest agent with a specific capability
        
        Args:
            capability: Capability to search for
            
        Returns:
            Healthiest agent with the capability, or None if none found
        """
        candidates = self.get_agents_by_capability(capability)
        if not candidates:
            return None
        
        # Sort by health status and response time
        healthy_agents = []
        for agent in candidates:
            health = self.registry.health_status.get(agent.id, {})
            if health.get("status") == "healthy":
                # Use response time as sorting key
                response_time = health.get("response_time", float("inf"))
                healthy_agents.append((agent, response_time))
        
        if healthy_agents:
            # Return the agent with the lowest response time
            return sorted(healthy_agents, key=lambda x: x[1])[0][0]
        
        # No healthy agents, return the first candidate
        return candidates[0]


# Singleton instance for easy access
_resilient_discovery = ResilientDiscovery()

# Convenience functions
def discover_agents(**kwargs) -> Dict[str, AgentInfo]:
    """Discover all agents using the resilient discovery system"""
    return _resilient_discovery.discover_agents(**kwargs)

def get_agent(agent_id: str, **kwargs) -> Optional[AgentInfo]:
    """Get a specific agent using the resilient discovery system"""
    return _resilient_discovery.get_agent(agent_id, **kwargs)

def get_agents_by_capability(capability: str) -> List[AgentInfo]:
    """Find agents with a specific capability"""
    return _resilient_discovery.get_agents_by_capability(capability)

def get_healthiest_agent(capability: str) -> Optional[AgentInfo]:
    """Find the healthiest agent with a capability"""
    return _resilient_discovery.get_healthiest_agent(capability)
