"""
Langfuse Tracing Module for MCP Army

Provides tracing and observability for agent-to-agent communication and MCP tool invocation.
"""
import os
import time
import uuid
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import langfuse, but handle case where it's not installed
try:
    from langfuse import Langfuse
    from langfuse.decorators import trace as langfuse_trace
    from langfuse.api.resources.commons.errors import AuthenticationError
    LANGFUSE_AVAILABLE = True
except ImportError:
    logger.warning("Langfuse not installed. Install with: pip install langfuse")
    LANGFUSE_AVAILABLE = False
    
    # Create mock decorator if langfuse not available
    def langfuse_trace(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args or callable(args[0]) else decorator(args[0])


class TracingDisabled:
    """Mock implementation when tracing is disabled"""
    
    def __init__(self, *args, **kwargs):
        pass
    
    def trace(self, *args, **kwargs):
        return self
    
    def span(self, *args, **kwargs):
        return self
    
    def generation(self, *args, **kwargs):
        return self
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def end(self, *args, **kwargs):
        pass
    
    def update(self, *args, **kwargs):
        pass


class MCPTracer:
    """Langfuse-based tracing for MCP Army"""
    
    def __init__(self, 
                 agent_id: str = None, 
                 agent_name: str = None,
                 public_key: str = None, 
                 secret_key: str = None,
                 host: str = None,
                 enabled: bool = True):
        """
        Initialize the tracer.
        
        Args:
            agent_id: Unique identifier for the agent
            agent_name: Display name for the agent
            public_key: Langfuse public key
            secret_key: Langfuse secret key
            host: Langfuse host URL (defaults to local, or env var)
            enabled: Whether tracing is enabled
        """
        self.agent_id = agent_id or os.environ.get("AGENT_ID", str(uuid.uuid4()))
        self.agent_name = agent_name or os.environ.get("AGENT_NAME", "default-agent")
        self.enabled = enabled and LANGFUSE_AVAILABLE
        
        # Get credentials from args or environment
        # Default to the self-hosted Langfuse credentials
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "DARCON_PK_langfuse")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "DARCON_SK_langfuse")
        
        # First try local Langfuse, then check environment, then fall back to cloud
        self.host = self._detect_langfuse_host(host)
        
        if not self.public_key or not self.secret_key:
            logger.warning("Langfuse credentials not provided. Tracing will be disabled.")
            self.enabled = False
        
        # Initialize Langfuse if enabled
        if self.enabled:
            self._initialize_client()
        
        # Thread-local storage for current trace
        self.current_trace_id = None
        
    def _detect_langfuse_host(self, host: Optional[str] = None) -> str:
        """Detect available Langfuse host."""
        # Priority: 1. Explicitly provided host, 2. Environment variable, 3. Local instance, 4. Cloud
        if host:
            return host
            
        env_host = os.environ.get("LANGFUSE_HOST")
        if env_host:
            return env_host
        
        # Try to connect to self-hosted Langfuse first
        import socket
        import http.client
        
        # Try localhost:3000 first
        try:
            conn = http.client.HTTPConnection("localhost", 3000, timeout=1)
            conn.request("GET", "/api/health")
            response = conn.getresponse()
            if response.status == 200:
                logger.info("Detected local Langfuse instance at http://localhost:3000")
                return "http://localhost:3000"
            conn.close()
        except (socket.error, http.client.HTTPException, ConnectionRefusedError):
            pass
            
        # Try container name darchon-langfuse:3000 (for internal container comms)
        try:
            conn = http.client.HTTPConnection("darchon-langfuse", 3000, timeout=1)
            conn.request("GET", "/api/health")
            response = conn.getresponse()
            if response.status == 200:
                logger.info("Detected Langfuse container at http://darchon-langfuse:3000")
                return "http://darchon-langfuse:3000"
            conn.close()
        except (socket.error, http.client.HTTPException, ConnectionRefusedError):
            pass
        
        # Fall back to cloud if we can't find a local instance
        logger.warning("No local Langfuse instance detected, falling back to cloud.langfuse.com")
        return "https://cloud.langfuse.com"
        
    def _initialize_client(self):
        """Initialize the Langfuse client with error handling."""
        try:
            self.client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host
            )
            logger.info(f"Langfuse tracing initialized for agent: {self.agent_name} at {self.host}")
        except (AuthenticationError, Exception) as e:
            logger.error(f"Failed to initialize Langfuse at {self.host}: {e}")
            self.enabled = False
    
    def trace_request(self, 
                      name: str,
                      input_data: Dict[str, Any],
                      metadata: Optional[Dict[str, Any]] = None,
                      tags: Optional[List[str]] = None,
                      trace_id: Optional[str] = None,
                      user_id: Optional[str] = None) -> Any:
        """
        Create a new trace for an incoming request.
        
        Args:
            name: Name of the trace
            input_data: Input data for the trace
            metadata: Additional metadata
            tags: Tags for the trace
            trace_id: Optional existing trace ID to continue
            user_id: Optional user ID
            
        Returns:
            Trace object or mock if tracing is disabled
        """
        if not self.enabled:
            return TracingDisabled()
        
        metadata = metadata or {}
        metadata.update({
            "agent_id": self.agent_id,
            "agent_name": self.agent_name
        })
        
        tags = tags or []
        tags.extend(["mcp-army", f"agent:{self.agent_name}"])
        
        try:
            trace = self.client.trace(
                name=name,
                input=input_data,
                metadata=metadata,
                tags=tags,
                id=trace_id,
                user_id=user_id
            )
            self.current_trace_id = trace.id
            return trace
        except Exception as e:
            logger.error(f"Error creating trace: {e}")
            return TracingDisabled()
    
    def trace_invoke(self,
                     agent_id: str,
                     input_data: Dict[str, Any],
                     parent_trace_id: Optional[str] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> Any:
        """
        Create a trace for an agent invocation.
        
        Args:
            agent_id: Target agent ID
            input_data: Input data for the invocation
            parent_trace_id: Optional parent trace ID
            metadata: Additional metadata
            
        Returns:
            Trace object or mock if tracing is disabled
        """
        if not self.enabled:
            return TracingDisabled()
        
        try:
            metadata = metadata or {}
            metadata.update({
                "source_agent_id": self.agent_id,
                "target_agent_id": agent_id
            })
            
            trace_id = parent_trace_id or self.current_trace_id
            
            if trace_id:
                # Create a span within the existing trace
                return self.client.trace(
                    id=trace_id
                ).span(
                    name=f"invoke:{agent_id}",
                    input=input_data,
                    metadata=metadata,
                    tags=["agent-invoke", f"target:{agent_id}"]
                )
            else:
                # Create a new trace
                return self.trace_request(
                    name=f"invoke:{agent_id}",
                    input_data=input_data,
                    metadata=metadata,
                    tags=["agent-invoke", f"target:{agent_id}"]
                )
        except Exception as e:
            logger.error(f"Error tracing invocation: {e}")
            return TracingDisabled()
    
    def trace_tool_call(self,
                       tool_name: str,
                       input_data: Dict[str, Any],
                       parent_trace_id: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> Any:
        """
        Create a trace for a tool call.
        
        Args:
            tool_name: Name of the tool
            input_data: Input data for the tool
            parent_trace_id: Optional parent trace ID
            metadata: Additional metadata
            
        Returns:
            Trace span or mock if tracing is disabled
        """
        if not self.enabled:
            return TracingDisabled()
        
        try:
            metadata = metadata or {}
            metadata.update({
                "agent_id": self.agent_id,
                "tool_name": tool_name
            })
            
            trace_id = parent_trace_id or self.current_trace_id
            
            if trace_id:
                # Create a span within the existing trace
                return self.client.trace(
                    id=trace_id
                ).span(
                    name=f"tool:{tool_name}",
                    input=input_data,
                    metadata=metadata,
                    tags=["tool-call", f"tool:{tool_name}"]
                )
            else:
                # Create a new trace
                return self.trace_request(
                    name=f"tool:{tool_name}",
                    input_data=input_data,
                    metadata=metadata,
                    tags=["tool-call", f"tool:{tool_name}"]
                )
        except Exception as e:
            logger.error(f"Error tracing tool call: {e}")
            return TracingDisabled()
    
    def trace_llm_call(self,
                      prompt: Union[str, Dict, List],
                      model: str,
                      completion: Optional[str] = None,
                      parent_trace_id: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None,
                      prompt_tokens: Optional[int] = None,
                      completion_tokens: Optional[int] = None,
                      cost: Optional[float] = None) -> Any:
        """
        Create a trace for an LLM call.
        
        Args:
            prompt: The prompt sent to the LLM
            model: The model name
            completion: Optional completion if already received
            parent_trace_id: Optional parent trace ID
            metadata: Additional metadata
            prompt_tokens: Optional count of prompt tokens
            completion_tokens: Optional count of completion tokens
            cost: Optional cost
            
        Returns:
            Generation object or mock if tracing is disabled
        """
        if not self.enabled:
            return TracingDisabled()
        
        try:
            metadata = metadata or {}
            metadata.update({
                "agent_id": self.agent_id,
                "model": model
            })
            
            trace_id = parent_trace_id or self.current_trace_id
            
            generation_params = {
                "name": f"llm:{model}",
                "model": model,
                "prompt": prompt,
                "metadata": metadata,
                "tags": ["llm-call", f"model:{model}"]
            }
            
            if completion:
                generation_params["completion"] = completion
            
            if prompt_tokens:
                generation_params["prompt_tokens"] = prompt_tokens
            
            if completion_tokens:
                generation_params["completion_tokens"] = completion_tokens
                
            if cost:
                generation_params["cost"] = cost
            
            if trace_id:
                # Create a generation within the existing trace
                return self.client.trace(
                    id=trace_id
                ).generation(**generation_params)
            else:
                # Create a new trace with a generation
                trace = self.trace_request(
                    name=f"llm:{model}",
                    input_data={"prompt": prompt},
                    metadata=metadata,
                    tags=["llm-call", f"model:{model}"]
                )
                return trace.generation(**generation_params)
        except Exception as e:
            logger.error(f"Error tracing LLM call: {e}")
            return TracingDisabled()


# Simplified trace decorator for MCP Army functions
def trace(name=None, metadata=None, tags=None):
    """
    Decorator for tracing MCP Army functions.
    
    Args:
        name: Name of the trace (defaults to function name)
        metadata: Additional metadata
        tags: Tags for the trace
    """
    def decorator(func):
        # If langfuse is not available, return the original function
        if not LANGFUSE_AVAILABLE:
            return func
        
        # Use langfuse decorator with our parameters
        return langfuse_trace(
            name_fn=lambda *args, **kwargs: name or func.__name__,
            metadata_fn=lambda *args, **kwargs: metadata or {},
            tags_fn=lambda *args, **kwargs: tags or []
        )(func)
    
    return decorator


# Create default tracer
default_tracer = MCPTracer()


# Usage example
if __name__ == "__main__":
    # Example usage
    tracer = MCPTracer(
        agent_id="example-agent",
        agent_name="Example Agent"
    )
    
    # Trace an entire request
    with tracer.trace_request("example_request", {"query": "test query"}) as trace:
        # Trace a tool call within the request
        with tracer.trace_tool_call("example_tool", {"param": "value"}) as tool_span:
            # Simulate tool execution
            time.sleep(0.5)
            tool_span.end(output={"result": "tool result"})
        
        # Trace an LLM call
        with tracer.trace_llm_call(
            prompt="Generate a response",
            model="gpt-4",
            prompt_tokens=10
        ) as generation:
            # Simulate LLM call
            time.sleep(1)
            generation.end(
                completion="This is a generated response",
                completion_tokens=5,
                cost=0.001
            )
        
        # End the trace with the final result
        trace.end(output={"response": "Final response"})
