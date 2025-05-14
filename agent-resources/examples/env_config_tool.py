from dotenv import load_dotenv, set_key, dotenv_values
import streamlit as st

load_dotenv()

# Environment links for credentials help
env_links = {
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "HuggingFace_API_KEY": "https://huggingface.co/settings/tokens",
    "OPENAI_API_KEY": "https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key",
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/settings/keys",
    "OPENROUTER_API_KEY": "https://openrouter.ai/settings/keys",
    "GOOGLE_GENERATIVE_AI_API_KEY": "https://console.cloud.google.com/apis/credentials",
    "OLLAMA_API_BASE_URL": "https://ollama.ai/docs",
    "MISTRAL_API_KEY": "https://console.mistral.ai/api-keys/",
    "COHERE_API_KEY": "https://dashboard.cohere.com/api-keys",
    "HYPERBOLIC_API_KEY": "https://app.hyperbolic.xyz/settings",
    "XAI_API_KEY": "https://x.ai/api",
    "PERPLEXITY_API_KEY": "https://www.perplexity.ai/settings/api",
    "AWS_BEDROCK_CONFIG": "https://console.aws.amazon.com/iam/home",
    "SUPABASE_URL": "https://supabase.com/dashboard/projects",
    "SUPABASE_API_KEY": "https://supabase.com/dashboard/projects",
}

def main():
    st.title("⚙️ .env Config Configuration")
    env_variables = dotenv_values(".env")
    st.subheader("🔧 Current Configuration")
    st.write("Modify your bolt.diy and supabase .env config below. Use the 🔗 icon to get credentials.")

    updated_variables = {}
    
    # For each environment variable, display the stored value in a password field.
    for key, val in env_variables.items():
        col1, col2 = st.columns([4, 1])
        with col1:
            # The text_input is pre-populated with the actual value (hidden by default).
            new_value = st.text_input(f"{key}:", value=val, type="password")
            updated_variables[key] = new_value
        with col2:
            if key in env_links:
                st.markdown(f'<a href="{env_links[key]}" target="_blank">🔗 Get Creds</a>', unsafe_allow_html=True)
    
    if st.button("💾 Save Changes"):
        try:
            for key, value in updated_variables.items():
                set_key(".env", key, value)
            st.success("Configuration updated successfully! 🏆")
        except Exception as e:
            st.error(f"Failed to update configuration: {e}")
    
    if st.button("Reload Configuration"):
        st.session_state["config_reloaded"] = True

if __name__ == "__main__":
    main()
