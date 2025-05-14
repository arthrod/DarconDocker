import os

def resolve_agent_resource_path(*subdirs):
    """
    Returns the absolute path to a subdirectory within agent-resources,
    regardless of where this function is called from.
    """
    current = os.path.abspath(os.path.dirname(__file__))
    while not os.path.isdir(os.path.join(current, "agent-resources")):
        parent = os.path.dirname(current)
        if parent == current:
            raise FileNotFoundError("Could not find agent-resources directory in any parent folder.")
        current = parent
    return os.path.join(current, "agent-resources", *subdirs)
