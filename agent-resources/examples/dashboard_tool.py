import streamlit as st

def main():
    # Top container for persistent navigation
    nav_container = st.container()
    
    with nav_container:
        st.title("Configuration Dashboard")
        st.markdown("Select a configuration page from the options below:")
        # Using a horizontal radio ensures the choices remain at the top
        selected_page = st.radio(
            "Choose a page:",
            options=["LLM Config", "Database Config", "🔧 .env Config", "System Management"],
            horizontal=True
        )
    
    # Separate container for the content below the navigation
    content_container = st.container()
    
    with content_container:
        if selected_page == "LLM Config":
            import ai_config
            ai_config.main()
        elif selected_page == "Database Config":
            import database_config
            database_config.main()
        elif selected_page == "🔧 .env Config":
            import env_config_tool
            env_config_tool.main()
        elif selected_page == "System Management":
            import system_manage
            system_manage.main()

if __name__ == "__main__":
    main()
