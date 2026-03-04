import os

import streamlit as st
from api.chat import get_examples, send_chat_message

st.set_page_config(page_title="T-Station", layout="wide")
st.title("T-Station AI Demo")


# Note
st.sidebar.markdown("## Domain Support")
st.sidebar.markdown("- Discovery: Product Description AF")
st.sidebar.markdown("- Support: FAQ AF")


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
                            full_response += chunk
                            message_placeholder.markdown(full_response + "▌")

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
