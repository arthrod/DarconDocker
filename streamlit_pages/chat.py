import streamlit as st
import uuid
import sys
import os
import asyncio
from typing import List, Dict, Any, Optional

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the workflow graph
from archon.workflow import graph as agentic_flow

# Simple message display handling
@st.cache_resource
def get_conversation_id():
    """Generate a unique ID for this conversation"""
    return str(uuid.uuid4())

conversation_id = get_conversation_id()

async def run_agent(user_input: str, tool_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the agent workflow with the user input
    
    Args:
        user_input: The user's query
        tool_name: Optional specific tool to use
        
    Returns:
        Response from the agent
    """
    try:
        # Prepare input for the workflow graph
        input_data = {
            "input": user_input,
            "conversation_id": conversation_id
        }
        
        if tool_name:
            input_data["tool_name"] = tool_name
            
        # Run the workflow graph
        result = await asyncio.to_thread(agentic_flow.run, input_data)
        
        return {
            "success": True,
            "response": result.get("response", "I processed your request but didn't get a clear response."),
            "tool_used": result.get("tool_used", None)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "response": f"Sorry, I encountered an error: {str(e)}"
        }

async def run_agent_with_streaming(user_input: str, selected_tool: Optional[str] = None):
    """
    Run the agent with streaming text for the user_input prompt,
    while maintaining the entire conversation in `st.session_state.messages`.
    
    Args:
        user_input: The original user input
        selected_tool: Optional tool selected by user
    """
    # Add user message to chat history
    st.session_state.messages.append({
        "type": "human",
        "content": user_input
    })
    
    # Create a placeholder for the AI's response
    with st.chat_message("ai"):
        message_placeholder = st.empty()
        full_response = ""
        
        try:
            # Run the agent
            result = await run_agent(user_input, selected_tool)
            
            if result["success"]:
                response = result["response"]
                
                # Display the full response
                message_placeholder.markdown(response)
                full_response = response
            else:
                # Show any errors in the message
                error_message = f"Error: {result['error']}"
                message_placeholder.markdown(error_message)
                full_response = error_message
        except Exception as e:
            # Show any errors in the message
            error_message = f"Error: {str(e)}"
            message_placeholder.markdown(error_message)
            full_response = error_message
    
    # Add AI response to chat history
    st.session_state.messages.append({
        "type": "ai",
        "content": full_response
    })

async def chat_tab():
    """Display the chat interface for talking to Archon"""
    st.write("I can do most things code, but one thing I don't do is Hallucination.")

    # Fun example questions so users know what to ask
    st.markdown("""
**Try asking me things like:**
- 🌐 *"Can you crawl https://docs.python.org and summarize the API docs?"*
- 📺 *"Summarize the key points from this Python tutorial: [YouTube URL]"*
- 🐙 *"Clone https://github.com/psf/requests and show me how it handles HTTP errors."*
- 🤔 *"What tools do you have?"*
- 💡 *"Can you combine info from a GitHub repo and a YouTube video for me?"*

*Don't be shy—ask anything!*
""")

    # Initialize chat history in session state if not present
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Add a clear conversation button
    if st.button("Clear Conversation"):
        st.session_state.messages = []
        st.rerun()

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        message_type = message["type"]
        if message_type in ["human", "ai", "system"]:
            with st.chat_message(message_type):
                st.markdown(message["content"])    

    # Accept user input
    if prompt := st.chat_input("What would you like me to help you with?"):
        # Process the query directly
        asyncio.run(run_agent_with_streaming(prompt))

# Don't run the chat tab when this module is imported - let the main app handle this
# chat_tab()
