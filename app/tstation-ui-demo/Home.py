import os

import streamlit as st
from api.chat import get_examples, send_chat_message

st.set_page_config(page_title="T-Station", layout="wide")
st.title("T-Station AI Demo")


# Note
st.sidebar.markdown("## Domain Support")
st.sidebar.markdown("- **Leading**: Greeting & routing")
st.sidebar.markdown("- **Discovery**: ProductRecommendation, Compatibility, ProductDescription AF")
st.sidebar.markdown("- **Pricing**: Price, Inventory, Store APIs")
st.sidebar.markdown("- **Shopping**: QuickOrder, Order tracking")
st.sidebar.markdown("- **Support**: FAQ, Escalation AF")


# Sidebar
st.sidebar.header("User Information")
user_options = ["Test-User", "Other"]
selected = st.sidebar.selectbox("User ID", user_options, index=0)
if selected == "Other":
    user_id = st.sidebar.text_input("Add your User ID", value="Test-User-Streamlit")
    session_id = st.sidebar.text_input("Session ID", value="test_session_id_123")
else:
    user_id = selected
    session_id = "01/01/2026"
stream_mode = True

# Examples
st.sidebar.header("Example Questions")
language = st.sidebar.selectbox("Choose your language", ["ko", "en"], index=1 if os.getenv("ENV") == "local" else 1)

examples = get_examples(language)
if examples and "categories" in examples:
    categories = examples["categories"]

    category_options = [categories[key]["name"] for key in categories.keys()]
    category_keys = list(categories.keys())

    selected_category_name = st.sidebar.selectbox(
        "Choose category",
        category_options,
        index=0
    )
    selected_category_key = category_keys[category_options.index(selected_category_name)]
    selected_explanation = categories[selected_category_key]["explanation"]
    st.sidebar.markdown(f"**Explanation:** _{selected_explanation}_")

    selected_category_key = None
    if selected_category_name:
        category_index = category_options.index(selected_category_name)
        selected_category_key = category_keys[category_index]

    if selected_category_key:
        questions = categories[selected_category_key]["questions"]
        question_options = questions

        selected_question = st.sidebar.selectbox(
            "Choose your example question",
            question_options,
            index=0
        )
    else:
        selected_question = None

else:
    selected_category_name = st.sidebar.selectbox("Choose category", ["No categories available"])
    selected_question = st.sidebar.selectbox("Choose your example question", ["No examples available"])
    selected_category_name = None if selected_category_name == "No categories available" else selected_category_name
    selected_question = None if selected_question == "No examples available" else selected_question

if 'messages' not in st.session_state:
    st.session_state['messages'] = []

chat_container = st.container()

with chat_container:
    for i, msg in enumerate(st.session_state['messages']):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

input_container = st.container()

with input_container:
    if selected_question:
        st.info(f"**📝 {selected_question}**")
        col1, col2 = st.columns([1, 6])
        with col1:
            if st.button("🚀 Ask it.", type="primary", key="ask_button"):
                prompt = selected_question
            else:
                prompt = None
        with col2:
            if st.button("❌ Cancel", key="cancel_button"):
                # Clear selection
                if 'random_example_index' in st.session_state:
                    del st.session_state.random_example_index
                st.rerun()
    else:
        prompt = None

    if not prompt:
        prompt = st.chat_input(placeholder="Your question....")

if prompt:
    with chat_container:
        with st.chat_message("user"):
            st.markdown(prompt)

    st.session_state['messages'].append({"role": "user", "content": prompt})

    with chat_container:
        with st.chat_message("assistant"):
            if stream_mode:
                # Agent flow display at top - list of steps
                agent_flow_steps = []
                agent_flow_placeholder = st.empty()

                message_placeholder = st.empty()
                full_response = ""

                try:
                    response_generator = send_chat_message(
                        messages=st.session_state['messages'],
                        session_id=session_id,
                        user_id=user_id,
                        stream=True
                    )

                    for chunk in response_generator:
                        if chunk.get("type") == "agent_flow":
                            agent = chunk.get("agent", "")
                            status = chunk.get("status", "success")
                            agent_flow_steps.append({"agent": agent, "status": status})
                            # Render each step with arrow between
                            steps_html = ""
                            for i, step in enumerate(agent_flow_steps):
                                if step["status"] == "error":
                                    bg_color = "#dc2626"  # Red
                                else:
                                    bg_color = "#16a34a"  # Green
                                steps_html += f"<span style='background: {bg_color}; padding: 4px 12px; border-radius: 15px; color: white; font-weight: bold; display: inline-block; vertical-align: middle;'>{step['agent']}</span>"
                                if i < len(agent_flow_steps) - 1:
                                    steps_html += f"<span style='margin: 0 8px; color: #6b7280; font-size: 14px; vertical-align: middle;'>→</span>"
                            agent_flow_placeholder.markdown(
                                f"<div style='display: flex; align-items: center; justify-content: flex-start; flex-wrap: wrap; gap: 4px; padding: 8px; margin-bottom: 10px;'>{steps_html}</div>",
                                unsafe_allow_html=True
                            )
                        elif chunk.get("type") == "token":
                            full_response += chunk.get("content", "")
                            message_placeholder.markdown(full_response + "▌")
                        elif chunk.get("type") == "error":
                            full_response += f"\nError: {chunk.get('content', '')}"
                            message_placeholder.markdown(full_response)

                    message_placeholder.markdown(full_response)
                    bot_reply = full_response

                except Exception as e:
                    error_msg = f"Error when streaming: {e}"
                    message_placeholder.markdown(error_msg)
                    bot_reply = error_msg

            else:
                with st.spinner("Thinking..."):
                    bot_reply = send_chat_message(
                        messages=st.session_state['messages'],
                        session_id=session_id,
                        user_id=user_id,
                        stream=stream_mode
                    )
                st.markdown(bot_reply)

    st.session_state['messages'].append({"role": "assistant", "content": bot_reply})

    if 'random_example_index' in st.session_state:
        del st.session_state.random_example_index

st.markdown("""
<style>
    .main .block-container {
        padding-bottom: 150px;
    }

    .stChatInput {
        position: sticky;
        bottom: 0;
        background: white;
        z-index: 1000;
    }

    div[data-testid="stChatMessage"]:last-child {
        scroll-margin-bottom: 100px;
    }
</style>

<script>
function scrollToBottom() {
    const chatMessages = document.querySelectorAll('div[data-testid="stChatMessage"]');
    if (chatMessages.length > 0) {
        const lastMessage = chatMessages[chatMessages.length - 1];
        lastMessage.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
}

const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
        if (mutation.type === 'childList') {
            setTimeout(scrollToBottom, 100);
        }
    });
});

const chatContainer = document.querySelector('.main');
if (chatContainer) {
    observer.observe(chatContainer, { childList: true, subtree: true });
}

setTimeout(scrollToBottom, 500);
</script>
""", unsafe_allow_html=True)
