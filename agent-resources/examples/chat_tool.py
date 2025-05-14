import streamlit as st
from chat_handler import process_chat_message

def main():
    st.title("🔥 Echo Ai - The Ultimate Agent Chat Tool 🤖")
    st.write("🛠️ **Chat with me about anything Echo Ai related, any tool or configuration**")
    st.write("💡 **Example**: *How do I use the Chain of Experts tool?*")
    st.write("💡 **Example**: *How do I crawl sites?*")

    st.markdown("---")
    st.write("✨ **Configure you settings in the Dashboard tool and start building today, with the power of A.I!**")
    
    # Check if the AI model has been configured
    selected_tool = st.session_state["selected_tool"]
    if "tool_configs" not in st.session_state or selected_tool not in st.session_state["tool_configs"]:
        st.error("Please configure the AI Model settings in the sidebar first.")
        st.stop()  # Stop execution if not configured
    
    # Initialize chat history if not exists
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    
    # Display chat history
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # The configuration is now stored in session state; no need to pass it explicitly.
    # config = st.session_state["tool_configs"][selected_tool]
    
    # st.chat_input displays a message box on the screen.
    if prompt := st.chat_input("Message...", key="chat_main_input"):
        # Add user message to chat history
        st.session_state["messages"].append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get AI response (note: removed the config argument)
        response = process_chat_message(prompt, user_id="default_user")
        
        # Add assistant response to chat history
        st.session_state["messages"].append({"role": "assistant", "content": response})
        
        # Display assistant response
        with st.chat_message("assistant"):
            st.markdown(response)

if __name__ == "__main__":
    main()
