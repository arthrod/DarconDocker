"""
Navigation Bar Component for Streamlit

This module provides a consistent top navigation bar that can be included
in all Streamlit pages without interfering with sidebar elements.
"""
import streamlit as st

def create_navbar():
    """
    Creates and renders a navigation bar at the top of the Streamlit app
    using HTML/CSS that doesn't interfere with sidebar components.
    """
    # Navigation bar styles
    navbar_style = """
    <style>
        .navbar {
            display: flex;
            justify-content: space-between;
            background-color: #262730;
            padding: 10px 20px;
            border-radius: 5px;
            margin-bottom: 10px;
        }
        .nav-section {
            display: flex;
            gap: 20px;
            align-items: center;
        }
        .nav-link {
            color: #FAFAFA;
            text-decoration: none;
            padding: 5px 10px;
            border-radius: 5px;
            transition: background-color 0.3s;
        }
        .nav-link:hover {
            background-color: #3f424e;
        }
        .nav-link.active {
            background-color: #4c506c;
        }
        .nav-section-title {
            color: #9fa3b0;
            margin-right: 5px;
            font-size: 0.9em;
        }
    </style>
    """

    # Navigation bar HTML structure with JavaScript to handle navigation within the same tab
    navbar_html = f"""
    <div class="navbar">
        <div class="nav-section">
            <span class="nav-section-title">Core:</span>
            <a onclick="navigateTo('Chat')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Chat' else ''}">💬 Chat</a>
            <a onclick="navigateTo('Environment')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Environment' else ''}">⚙️ Environment</a>
            <a onclick="navigateTo('Documentation')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Documentation' else ''}">📚 Documentation</a>
        </div>
        <div class="nav-section">
            <span class="nav-section-title">Agent Management:</span>
            <a onclick="navigateTo('Agent Service')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Agent Service' else ''}">🔄 Agent Service</a>
            <a onclick="navigateTo('Agent Builder')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Agent Builder' else ''}">🛠️ Agent Builder</a>
            <a onclick="navigateTo('Agent Insights')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Agent Insights' else ''}">📊 Agent Insights</a>
            <a onclick="navigateTo('Command Center')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Command Center' else ''}">🎮 Command Center</a>
        </div>
        <div class="nav-section">
            <span class="nav-section-title">Observability:</span>
            <a onclick="navigateTo('Observability')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Observability' else ''}">📈 Observability</a>
            <a onclick="navigateTo('Langfuse')" class="nav-link {'active' if st.session_state.get('selected_tab') == 'Langfuse' else ''}">🔍 Langfuse</a>
        </div>
    </div>
    
    <script>
    function navigateTo(tab) {{  
        // Update the URL without reloading the page
        const newUrl = window.location.protocol + '//' + window.location.host + window.location.pathname + '?tab=' + encodeURIComponent(tab);
        window.history.pushState({{ tab: tab }}, '', newUrl);
        
        // Reload the current page to apply the tab change
        window.location.reload();
    }}
    </script>
    """

    # Combine styles and HTML structure
    st.markdown(navbar_style + navbar_html, unsafe_allow_html=True)
    
    # Add a small spacer
    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

    # Return to allow chaining
    return None
