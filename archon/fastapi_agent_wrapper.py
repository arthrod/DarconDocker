"""
Generic FastAPI Wrapper for Plug-in Agents
- Dynamically loads agent logic (graph/node) based on environment/config
- Exposes /invoke and /health endpoints for agent-to-agent and orchestrator communication
- Supports both static and dynamic agent graphs
"""
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Union, Callable
import importlib
import os
import json
import uuid
import time
import logging
import requests
import pkg_resources
from pathlib import Path

# Import Langfuse tracing
try:
    from .langfuse_tracing import MCPTracer, trace
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    # Create mock decorator if langfuse not available
    def trace(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args or callable(args[0]) else decorator(args[0])

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables for agent configuration
AGENT_NAME = os.environ.get("AGENT_NAME", "default-agent")
AGENT_PORT = int(os.environ.get("AGENT_PORT", 8000))
AGENT_DESCRIPTION = os.environ.get("AGENT_DESCRIPTION", "")
AGENT_SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", "")
AGENT_CAPABILITIES = os.environ.get("AGENT_CAPABILITIES", "basic_response,text_processing").split(",")
AGENT_VERSION = os.environ.get("AGENT_VERSION", "1.0.0")

# Supabase configuration for Agent Notice Board
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

# Langfuse configuration
LANGFUSE_ENABLED = os.environ.get("LANGFUSE_ENABLED", "true").lower() == "true"
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://10.147.20.5:3030")

# App configuration
app = FastAPI(
    title=f"{AGENT_NAME} Agent",
    description=AGENT_DESCRIPTION or f"FastAPI wrapper for {AGENT_NAME} agent",
    version=AGENT_VERSION,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for agent-to-agent communication
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directory for chat interface if it doesn't exist
STATIC_DIR = Path("/tmp/static")
CHAT_INTERFACE_PATH = STATIC_DIR / "chat.html"
os.makedirs(STATIC_DIR, exist_ok=True)

# Try to mount static files directory
try:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
except Exception as e:
    logger.warning(f"Could not mount static directory: {e}")

# Pydantic models
class InvokeRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    is_first_message: bool = False
    config: Optional[Dict[str, Any]] = None

class AgentRegistration(BaseModel):
    agent_id: str
    name: str
    description: str
    capabilities: List[str]
    endpoints: Dict[str, str]
    metadata: Optional[Dict[str, Any]] = None

# Dynamically load agent graph/node from environment or config
AGENT_GRAPH_PATH = os.environ.get("AGENT_GRAPH_PATH", "agent_graph:main")

# Generate a unique agent ID if not provided
AGENT_ID = os.environ.get("AGENT_ID", f"{AGENT_NAME.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}")

# Initialize Langfuse tracer
tracer = None
if LANGFUSE_AVAILABLE and LANGFUSE_ENABLED and LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
    try:
        from .langfuse_tracing import MCPTracer
        tracer = MCPTracer(
            agent_id=AGENT_ID,
            agent_name=AGENT_NAME,
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
            enabled=True
        )
        logger.info(f"Langfuse tracing initialized for agent {AGENT_NAME}")
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse tracer: {e}")
        tracer = None

# Dependency for getting tracer in endpoints
def get_tracer():
    return tracer

# AGENT_GRAPH_PATH format: "module_path:attr_name"
def load_agent_graph():
    """Dynamically load the agent's graph or node function"""
    try:
        module_path, attr_name = AGENT_GRAPH_PATH.split(":")
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    except Exception as e:
        logger.error(f"Error loading agent graph: {e}")
        # Return a fallback function that just echoes the input
        return lambda input_data: input_data.get("input", "No input provided")

# Try to import agent notice board client if available
try:
    from agent_notice_board_client import AgentNoticeBoardClient
    notice_board_client = AgentNoticeBoardClient(SUPABASE_URL, SUPABASE_API_KEY) if SUPABASE_URL and SUPABASE_API_KEY else None
except ImportError:
    notice_board_client = None
    logger.warning("Agent Notice Board client not available. Agent will not register with the notice board.")

def register_with_notice_board():
    """Register the agent with the Agent Notice Board"""
    if not notice_board_client:
        return
    
    try:
        # Create A2A card for registration
        a2a_card = {
            "agent_id": AGENT_ID,
            "agent_name": AGENT_NAME,
            "description": AGENT_DESCRIPTION or AGENT_SYSTEM_PROMPT,
            "capabilities": AGENT_CAPABILITIES,
            "endpoints": {
                "invoke": f"http://localhost:{AGENT_PORT}/invoke",
                "health": f"http://localhost:{AGENT_PORT}/health"
            },
            "metadata": {
                "version": AGENT_VERSION,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
        }
        
        # Post registration notice
        notice_board_client.post_notice(
            agent_id=AGENT_ID,
            notice_type="agent_registration",
            payload={
                "agent_info": {
                    "agent_id": AGENT_ID,
                    "name": AGENT_NAME,
                    "endpoint": f"http://localhost:{AGENT_PORT}/invoke",
                    "description": AGENT_DESCRIPTION or AGENT_SYSTEM_PROMPT,
                    "capabilities": AGENT_CAPABILITIES,
                    "status": "active",
                    "metadata": {
                        "version": AGENT_VERSION
                    }
                },
                "a2a_card": a2a_card
            },
            visibility="public"
        )
        logger.info(f"Agent {AGENT_ID} registered with Notice Board")
    except Exception as e:
        logger.error(f"Failed to register with Notice Board: {e}")

# HTML template for the chat interface
def generate_chat_interface_html():
    """Generate a simple chat interface for the agent"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{AGENT_NAME} - Chat Interface</title>
        <style>
            :root {{
                --primary-color: #4CAF50;
                --primary-light: #4CAF5022;
                --text-color: #333;
                --bg-color: #f9f9f9;
                --border-color: #ddd;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 0;
                background-color: var(--bg-color);
                color: var(--text-color);
            }}
            
            .chat-container {{
                max-width: 800px;
                margin: 20px auto;
                border: 1px solid var(--border-color);
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                display: flex;
                flex-direction: column;
                height: 90vh;
            }}
            
            .chat-header {{
                background-color: var(--primary-color);
                color: white;
                padding: 15px 20px;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }}
            
            .agent-info {{
                display: flex;
                align-items: center;
            }}
            
            .agent-avatar {{
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background-color: white;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 10px;
                font-weight: bold;
                color: var(--primary-color);
            }}
            
            .agent-name {{
                font-size: 18px;
                font-weight: 600;
            }}
            
            .agent-status {{
                font-size: 12px;
                opacity: 0.9;
            }}
            
            .chat-messages {{
                flex: 1;
                padding: 20px;
                overflow-y: auto;
                background-color: white;
            }}
            
            .message {{
                margin-bottom: 15px;
                display: flex;
                flex-direction: column;
            }}
            
            .message-content {{
                max-width: 80%;
                padding: 10px 15px;
                border-radius: 18px;
                position: relative;
            }}
            
            .user-message {{
                align-items: flex-end;
            }}
            
            .user-message .message-content {{
                background-color: var(--primary-color);
                color: white;
                border-bottom-right-radius: 5px;
            }}
            
            .agent-message {{
                align-items: flex-start;
            }}
            
            .agent-message .message-content {{
                background-color: #f0f0f0;
                border-bottom-left-radius: 5px;
            }}
            
            .message-time {{
                font-size: 11px;
                margin-top: 5px;
                opacity: 0.7;
            }}
            
            .user-message .message-time {{
                text-align: right;
            }}
            
            .chat-input {{
                padding: 15px;
                background-color: white;
                border-top: 1px solid var(--border-color);
                display: flex;
            }}
            
            .chat-input input {{
                flex: 1;
                padding: 12px 15px;
                border: 1px solid var(--border-color);
                border-radius: 24px;
                outline: none;
                font-size: 15px;
            }}
            
            .chat-input input:focus {{
                border-color: var(--primary-color);
                box-shadow: 0 0 0 2px var(--primary-light);
            }}
            
            .send-button {{
                background-color: var(--primary-color);
                color: white;
                border: none;
                border-radius: 50%;
                width: 44px;
                height: 44px;
                margin-left: 10px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background-color 0.2s;
            }}
            
            .send-button:hover {{
                background-color: #3d8b3d;
            }}
            
            .send-button:active {{
                transform: scale(0.95);
            }}
            
            .typing-indicator {{
                display: none;
                padding: 10px 15px;
                background-color: #f0f0f0;
                border-radius: 18px;
                border-bottom-left-radius: 5px;
                margin-bottom: 15px;
                align-self: flex-start;
                width: fit-content;
            }}
            
            .typing-indicator span {{
                height: 8px;
                width: 8px;
                background-color: #888;
                border-radius: 50%;
                display: inline-block;
                margin-right: 5px;
                animation: typing 1.5s infinite;
            }}
            
            .typing-indicator span:nth-child(2) {{
                animation-delay: 0.2s;
            }}
            
            .typing-indicator span:nth-child(3) {{
                animation-delay: 0.4s;
                margin-right: 0;
            }}
            
            @keyframes typing {{
                0%, 100% {{ transform: translateY(0); }}
                50% {{ transform: translateY(-5px); }}
            }}
            
            code {{
                font-family: 'Courier New', Courier, monospace;
                background-color: #f0f0f0;
                padding: 2px 4px;
                border-radius: 3px;
                font-size: 0.9em;
            }}
            
            pre {{
                background-color: #f8f8f8;
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
                margin: 10px 0;
            }}
            
            .message-content pre {{
                background-color: rgba(0, 0, 0, 0.1);
                width: 100%;
            }}
            
            .user-message .message-content pre,
            .user-message .message-content code {{
                background-color: rgba(255, 255, 255, 0.2);
            }}
        </style>
    </head>
    <body>
        <div class="chat-container">
            <div class="chat-header">
                <div class="agent-info">
                    <div class="agent-avatar">{AGENT_NAME[0].upper()}</div>
                    <div>
                        <div class="agent-name">{AGENT_NAME}</div>
                        <div class="agent-status">Online</div>
                    </div>
                </div>
            </div>
            
            <div class="chat-messages" id="chat-messages">
                <div class="message agent-message">
                    <div class="message-content">
                        <p>👋 Hi! I'm {AGENT_NAME}. {AGENT_DESCRIPTION or AGENT_SYSTEM_PROMPT}</p>
                        <p>How can I help you today?</p>
                    </div>
                    <div class="message-time">Just now</div>
                </div>
                
                <div class="typing-indicator" id="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
            
            <div class="chat-input">
                <input type="text" id="message-input" placeholder="Type your message...">
                <button class="send-button" id="send-button">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M22 2L11 13" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            </div>
        </div>
        
        <script>
            const messageInput = document.getElementById('message-input');
            const sendButton = document.getElementById('send-button');
            const chatMessages = document.getElementById('chat-messages');
            const typingIndicator = document.getElementById('typing-indicator');
            
            // API details
            const API_ENDPOINT = "/invoke";
            
            // Markdown-like formatting (basic)
            function formatMessage(text) {{
                // Handle code blocks
                text = text.replace(/```([\s\S]*?)```/g, '<pre>$1</pre>');
                
                // Handle inline code
                text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
                
                // Handle bold
                text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
                
                // Handle italic
                text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
                
                // Convert line breaks to <br>
                text = text.replace(/\n/g, '<br>');
                
                return text;
            }}
            
            function getCurrentTime() {{
                const now = new Date();
                return now.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
            }}
            
            function addMessage(message, isUser = false) {{
                const messageElement = document.createElement('div');
                messageElement.className = `message ${{isUser ? 'user-message' : 'agent-message'}}`;
                
                const formattedMessage = formatMessage(message);
                
                messageElement.innerHTML = `
                    <div class="message-content">${{formattedMessage}}</div>
                    <div class="message-time">${{getCurrentTime()}}</div>
                `;
                
                // Add before typing indicator
                chatMessages.insertBefore(messageElement, typingIndicator);
                
                // Scroll to bottom
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }}
            
            function showTypingIndicator() {{
                typingIndicator.style.display = 'block';
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }}
            
            function hideTypingIndicator() {{
                typingIndicator.style.display = 'none';
            }}
            
            async function sendMessage(message) {{
                addMessage(message, true);
                messageInput.value = '';
                
                showTypingIndicator();
                
                try {{
                    const response = await fetch(API_ENDPOINT, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json'
                        }},
                        body: JSON.stringify({{
                            message: message
                        }})
                    }});
                    
                    if (!response.ok) {{
                        throw new Error(`API error: ${{response.status}}`);
                    }}
                    
                    const data = await response.json();
                    hideTypingIndicator();
                    
                    // Handle the agent's response
                    const agentResponse = data.response || data.message || data.output || data.content || JSON.stringify(data);
                    addMessage(agentResponse);
                    
                }} catch (error) {{
                    hideTypingIndicator();
                    addMessage(`Sorry, I encountered an error: ${{error.message}}`);
                    console.error('Error:', error);
                }}
            }}
            
            // Event listeners
            sendButton.addEventListener('click', () => {{
                const message = messageInput.value.trim();
                if (message) {{
                    sendMessage(message);
                }}
            }});
            
            messageInput.addEventListener('keypress', (e) => {{
                if (e.key === 'Enter') {{
                    const message = messageInput.value.trim();
                    if (message) {{
                        sendMessage(message);
                    }}
                }}
            }});
            
            // Focus input on load
            window.addEventListener('load', () => {{
                messageInput.focus();
            }});
        </script>
    </body>
    </html>
    """
    return html_content

# Create the default chat interface
try:
    with open(CHAT_INTERFACE_PATH, "w") as f:
        f.write(generate_chat_interface_html())
    logger.info(f"Chat interface created at {CHAT_INTERFACE_PATH}")
except Exception as e:
    logger.warning(f"Failed to create chat interface: {e}")

# Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint that redirects to the chat interface"""
    return HTMLResponse(content=generate_chat_interface_html())

@app.get("/chat", response_class=HTMLResponse)
async def chat():
    """Serve the chat interface"""
    try:
        with open(CHAT_INTERFACE_PATH, "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Error serving chat interface: {e}")
        return HTMLResponse(content=generate_chat_interface_html())

@app.get("/health")
def health_check():
    """Health check endpoint for agent status monitoring"""
    return {"status": "ok", "agent": AGENT_NAME, "id": AGENT_ID}

@app.get("/info")
def agent_info():
    """Return agent information including capabilities and endpoints"""
    return {
        "agent_id": AGENT_ID,
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION or AGENT_SYSTEM_PROMPT,
        "capabilities": AGENT_CAPABILITIES,
        "endpoints": {
            "invoke": f"/invoke",
            "chat": f"/chat",
            "health": f"/health"
        },
        "version": AGENT_VERSION
    }

@app.post("/invoke")
async def invoke_agent(request: InvokeRequest, tracer: Optional[MCPTracer] = Depends(get_tracer)):
    """
    Process a message through the agent's logic (graph/node) and return the response.
    """
    # Start tracing the request if tracer is available
    trace_context = None
    if tracer:
        trace_context = tracer.trace_request(
            name=f"invoke:{AGENT_NAME}",
            input_data={"message": request.message},
            metadata={
                "thread_id": request.thread_id,
                "is_first_message": request.is_first_message,
                "agent_name": AGENT_NAME
            },
            tags=["agent-invoke", f"agent:{AGENT_NAME}"]
        )
    
    try:
        # Load agent logic
        agent_logic = load_agent_graph()
        input_data = {"input": request.message, "thread_id": request.thread_id}
        
        # Add additional config if provided
        if request.config:
            input_data.update(request.config)
        
        # Trace LLM call if using a language model
        llm_trace = None
        if tracer and "model" in input_data:
            llm_trace = tracer.trace_llm_call(
                prompt=request.message,
                model=input_data.get("model", "unknown"),
                parent_trace_id=trace_context.id if trace_context else None
            )
        
        # If agent_logic is a graph, run it; if it's a node, call it
        if hasattr(agent_logic, "run"):
            result = agent_logic.run(input_data)
        elif callable(agent_logic):
            result = agent_logic(input_data)
        else:
            raise Exception("Loaded agent logic is not callable or a valid graph.")
        
        # End LLM tracing if applicable
        if llm_trace:
            llm_trace.end(completion=result)
        
        # End request tracing
        if trace_context:
            trace_context.end(output={"response": result})
        
        # Return the response
        return {"response": result}
    except Exception as e:
        logger.error(f"Error in invoke_agent: {e}")
        
        # Record error in trace if tracing
        if trace_context:
            trace_context.end(output={"error": str(e)}, status="error")
        
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/register")
async def register_agent(registration: AgentRegistration):
    """Register the agent with custom information"""
    try:
        if not notice_board_client:
            return {"status": "error", "message": "Agent Notice Board client not available"}
        
        # Post registration notice
        notice_board_client.post_notice(
            agent_id=registration.agent_id,
            notice_type="agent_registration",
            payload={
                "agent_info": {
                    "agent_id": registration.agent_id,
                    "name": registration.name,
                    "endpoint": registration.endpoints.get("invoke", ""),
                    "description": registration.description,
                    "capabilities": registration.capabilities,
                    "status": "active",
                    "metadata": registration.metadata or {}
                }
            },
            visibility="public"
        )
        return {"status": "success", "message": f"Agent {registration.agent_id} registered"}
    except Exception as e:
        logger.error(f"Error in register_agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Register the agent with the Agent Notice Board on startup"""
    # Register the agent with the notice board
    if SUPABASE_URL and SUPABASE_API_KEY:
        register_with_notice_board()
    
    # Log startup with Langfuse if available
    if tracer:
        startup_trace = tracer.trace_request(
            name="agent_startup",
            input_data={},
            metadata={
                "agent_id": AGENT_ID,
                "agent_name": AGENT_NAME,
                "port": AGENT_PORT,
                "capabilities": AGENT_CAPABILITIES,
                "version": AGENT_VERSION
            },
            tags=["startup", f"agent:{AGENT_NAME}"]
        )
        startup_trace.end(output={"status": "online"})
    
    logger.info(f"Agent {AGENT_NAME} ({AGENT_ID}) started on port {AGENT_PORT}")

@app.on_event("shutdown")
async def shutdown_event():
    """Unregister the agent from the Agent Notice Board on shutdown"""
    # Log shutdown with Langfuse if available
    if tracer:
        shutdown_trace = tracer.trace_request(
            name="agent_shutdown",
            input_data={},
            metadata={
                "agent_id": AGENT_ID,
                "agent_name": AGENT_NAME
            },
            tags=["shutdown", f"agent:{AGENT_NAME}"]
        )
        shutdown_trace.end(output={"status": "offline"})
    
    # Unregister from Notice Board
    if notice_board_client:
        try:
            # Post agent offline notice
            notice_board_client.post_notice(
                agent_id=AGENT_ID,
                notice_type="agent_status",
                payload={"status": "offline"},
                visibility="public"
            )
            logger.info(f"Agent {AGENT_ID} unregistered from Notice Board")
        except Exception as e:
            logger.error(f"Failed to unregister from Notice Board: {e}")
    
    logger.info(f"Agent {AGENT_NAME} ({AGENT_ID}) shutting down")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
