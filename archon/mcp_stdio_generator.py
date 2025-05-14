"""
MCP Stdio Generator Module

Utilities for generating MCP stdio configuration and HTML chat interfaces for agents.
This allows agents to be used as standalone tools with their own interfaces.
"""
import os
import json
from typing import Dict, Any, List, Optional
from pathlib import Path


def generate_mcp_stdio_config(
    agent_id: str,
    agent_name: str,
    endpoint: str,
    description: str = "",
    capabilities: List[str] = None,
) -> Dict[str, Any]:
    """
    Generate an MCP stdio tool configuration for an agent.
    
    Args:
        agent_id: Unique identifier for the agent
        agent_name: Display name for the agent
        endpoint: API endpoint for the agent
        description: Description of the agent's capabilities
        capabilities: List of capabilities the agent supports
        
    Returns:
        Dictionary containing MCP stdio configuration
    """
    capabilities = capabilities or ["basic_response", "text_processing"]
    capability_params = {}
    
    # Generate parameters based on capabilities
    for capability in capabilities:
        if capability == "code_generation":
            capability_params["language"] = {
                "type": "string",
                "description": "Programming language to generate code for",
                "enum": ["python", "javascript", "typescript", "bash", "html", "css", "sql"]
            }
        elif capability == "data_analysis":
            capability_params["format"] = {
                "type": "string",
                "description": "Format for the data analysis results",
                "enum": ["json", "csv", "markdown", "text"]
            }
    
    # Create the MCP tool definition
    tool_config = {
        "tools": [
            {
                "name": agent_id.replace("-", "_"),
                "description": description or f"Call the {agent_name} agent",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message to send to the agent"
                        },
                        **capability_params
                    },
                    "required": ["message"]
                },
                "endpoint": endpoint
            }
        ]
    }
    
    return tool_config


def save_mcp_stdio_config(
    agent_id: str,
    config: Dict[str, Any],
    output_dir: str = None
) -> str:
    """
    Save MCP stdio config to a file.
    
    Args:
        agent_id: Agent ID used for filename
        config: MCP stdio configuration
        output_dir: Directory to save the file (default: features/{agent_id})
        
    Returns:
        Path to the saved file
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "features" / agent_id
    
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"{agent_id}_mcp_config.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w") as f:
        json.dump(config, f, indent=2)
    
    return filepath


def generate_chat_interface_html(
    agent_id: str,
    agent_name: str,
    endpoint: str,
    description: str = "",
    primary_color: str = "#4CAF50",
    api_key: str = None,
) -> str:
    """
    Generate a standalone HTML chat interface for an agent.
    
    Args:
        agent_id: Unique identifier for the agent
        agent_name: Display name for the agent
        endpoint: API endpoint for the agent
        description: Description of the agent's capabilities
        primary_color: Primary color for the interface
        api_key: Optional API key for authentication
        
    Returns:
        HTML content for the chat interface
    """
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{agent_name} - Chat Interface</title>
    <style>
        :root {{
            --primary-color: {primary_color};
            --primary-light: {primary_color}22;
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
                <div class="agent-avatar">{agent_name[0].upper()}</div>
                <div>
                    <div class="agent-name">{agent_name}</div>
                    <div class="agent-status">Online</div>
                </div>
            </div>
        </div>
        
        <div class="chat-messages" id="chat-messages">
            <div class="message agent-message">
                <div class="message-content">
                    <p>👋 Hi! I'm {agent_name}. {description}</p>
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
        const API_ENDPOINT = "{endpoint}";
        const API_KEY = "{api_key or ""}";
        
        // Markdown-like formatting (basic)
        function formatMessage(text) {{
            // Handle code blocks
            text = text.replace(/```([\\s\\S]*?)```/g, '<pre>$1</pre>');
            
            // Handle inline code
            text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
            
            // Handle bold
            text = text.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
            
            // Handle italic
            text = text.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
            
            // Convert line breaks to <br>
            text = text.replace(/\\n/g, '<br>');
            
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
                        'Content-Type': 'application/json',
                        ...(API_KEY ? {{ 'Authorization': `Bearer ${{API_KEY}}` }} : {{}})
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


def save_chat_interface(
    agent_id: str,
    html_content: str,
    output_dir: str = None
) -> str:
    """
    Save the chat interface HTML to a file.
    
    Args:
        agent_id: Agent ID used for filename
        html_content: HTML content to save
        output_dir: Directory to save the file (default: features/{agent_id})
        
    Returns:
        Path to the saved file
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "features" / agent_id
    
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"{agent_id}_chat.html"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w") as f:
        f.write(html_content)
    
    return filepath


def generate_embedded_chat_widget_code(
    agent_id: str,
    agent_name: str,
    endpoint: str,
    height: str = "500px",
    width: str = "100%",
) -> str:
    """
    Generate embeddable code snippet for the chat widget.
    
    Args:
        agent_id: Unique identifier for the agent
        agent_name: Display name for the agent
        endpoint: API endpoint for the agent
        height: Height of the embedded iframe
        width: Width of the embedded iframe
        
    Returns:
        HTML embed code for the widget
    """
    # Basic embedding using iframe that points to the HTML file URL
    embed_code = f"""<!-- {agent_name} Chat Widget -->
<iframe 
    id="{agent_id}-chat-widget"
    src="{agent_id}_chat.html"
    style="border: none; width: {width}; height: {height};"
    title="{agent_name} Chat Widget">
</iframe>
"""
    return embed_code

"""
# Usage example:

# Generate MCP stdio config
mcp_config = generate_mcp_stdio_config(
    agent_id="data-analyst",
    agent_name="Data Analyst",
    endpoint="http://localhost:8080/invoke",
    description="Analyzes data and provides insights",
    capabilities=["data_analysis", "visualization"]
)

# Save the config to a file
config_path = save_mcp_stdio_config("data-analyst", mcp_config)

# Generate HTML chat interface
html_content = generate_chat_interface_html(
    agent_id="data-analyst",
    agent_name="Data Analyst",
    endpoint="http://localhost:8080/invoke",
    description="I can analyze your data and provide insights.",
    primary_color="#3498db"
)

# Save the chat interface
chat_path = save_chat_interface("data-analyst", html_content)

# Generate embed code
embed_code = generate_embedded_chat_widget_code(
    agent_id="data-analyst",
    agent_name="Data Analyst",
    endpoint="http://localhost:8080/invoke"
)
"""
