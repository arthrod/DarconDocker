# workflow.py
"""
Example LangGraph workflow integrating all MCP Army agents/tools as nodes.
"""
from langgraph.graph import Graph
import logging
import os
from typing import Dict, Callable, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a simple dummy node function that works when no agents are available
def dummy_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback node when no agents are discovered"""
    return {"response": "No agents currently available in the workflow."}

# Create empty graph
graph = Graph()

try:
    # Only import discovery if needed to avoid circular imports
    from .discovery import get_agent_node_functions
    
    # Get agent node functions if available
    try:
        node_functions = get_agent_node_functions()
    except Exception as e:
        logger.error(f"Failed to get agent node functions: {e}")
        node_functions = {}
    
    # Check if we found any valid nodes
    if not node_functions:
        logger.warning("No agent nodes discovered. Creating fallback workflow.")
        graph.add_node("fallback", dummy_node)
    else:
        # Add discovered nodes to graph
        logger.info(f"Found {len(node_functions)} agent nodes to add to workflow")
        for name, func in node_functions.items():
            if callable(func):  # Verify it's actually callable
                try:
                    graph.add_node(name, func)
                    logger.info(f"Added node '{name}' to workflow graph")
                except Exception as node_error:
                    logger.error(f"Error adding node '{name}': {node_error}")
        
        # Connect nodes in workflow if we have multiple
        node_names = list(graph.nodes)
        if len(node_names) > 1:
            for i in range(len(node_names) - 1):
                try:
                    graph.connect(node_names[i], node_names[i+1])
                except Exception as connect_error:
                    logger.error(f"Error connecting nodes: {connect_error}")
            logger.info(f"Connected {len(node_names)} nodes in workflow")
        elif len(node_names) == 1:
            logger.info(f"Created workflow with single node: {node_names[0]}")
        else:
            # If somehow we didn't add any nodes, add the fallback
            logger.warning("No valid nodes were added to workflow. Using fallback.")
            graph.add_node("fallback", dummy_node)

except Exception as e:
    logger.error(f"Critical error setting up workflow graph: {e}")
    # Create a minimal fallback workflow
    graph = Graph()
    graph.add_node("fallback", dummy_node)

# Example run (only executes when module is run directly)
if __name__ == "__main__":
    try:
        input_data = {"input": "Hello MCP Army!"}
        result = graph.run(input_data)
        print("Workflow result:", result)
    except Exception as run_error:
        print(f"Error running workflow: {run_error}")
