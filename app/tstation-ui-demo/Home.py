import json
import os
import uuid

import streamlit as st
import streamlit_nested_layout
from api.chat import get_examples, send_chat_message
from api.sessions import get_sessions, get_history, delete_session, get_user_info
from api.validate_token import validate_token

st.set_page_config(page_title="T-Station", layout="wide")
st.title("T-Station AI Demo")

# Initialize session state for login
if "tstation_logged_in" not in st.session_state:
    st.session_state["tstation_logged_in"] = False
if "access_token" not in st.session_state:
    st.session_state["access_token"] = None
if "current_session_id" not in st.session_state:
    st.session_state["current_session_id"] = str(uuid.uuid4())
if "user_info" not in st.session_state:
    st.session_state["user_info"] = None


# Login Section
st.sidebar.markdown("---")
st.sidebar.header("🔐 T-Station Login")

# Check login status
if st.session_state.get("tstation_logged_in") and st.session_state.get("access_token"):
    st.sidebar.success("✅ Logged in")

    # Display user info
    user_info = st.session_state.get("user_info", {})
    if user_info:
        st.sidebar.markdown(f"**User ID:** {user_info.get('user_id', 'N/A')}")
        if user_info.get("mbr_nm"):
            st.sidebar.markdown(f"**Name:** {user_info['mbr_nm']}")
        if user_info.get("car_no"):
            st.sidebar.markdown(f"**Car:** {user_info['car_no']}")

    if st.sidebar.button("Logout", key="logout_btn"):
        st.session_state["tstation_logged_in"] = False
        st.session_state["access_token"] = None
        st.session_state["current_session_id"] = None
        st.session_state["user_info"] = None
        st.session_state["messages"] = []
        st.rerun()
else:
    st.sidebar.info("Only logged-in users can call APIs")

    # Option 1: Manual token input
    with st.sidebar.expander("Enter Access Token manually", expanded=True):
        manual_token = st.text_input(
            "Access Token",
            type="password",
            placeholder="eyJ0eXAiOiJKV1Qi...",
            key="manual_token_input"
        )
        if st.button("Save Token", key="save_manual_token"):
            if manual_token:
                with st.spinner("Validating token..."):
                    result = validate_token(manual_token)
                if result.get("valid"):
                    st.session_state["access_token"] = manual_token
                    st.session_state["tstation_logged_in"] = True
                    # Fetch user info
                    user_info = get_user_info(manual_token)
                    st.session_state["user_info"] = user_info
                    st.success("Token saved!")
                    st.rerun()
                else:
                    st.error(f"Invalid token: {result.get('reason', 'Unknown error')}")
            else:
                st.error("Please enter a token")

    # Option 2: Login via browser (requires manual cookie)
    st.sidebar.markdown("**Or get token via browser:**")
    st.sidebar.markdown("""
    1. Login at https://wwwqa.tstation.com
    2. Visit: https://wwwqa.tstation.com/member/chatbotTokenJson.do
    3. Copy `accessToken` from the JSON response
    4. Paste into the field above
    """)

# Get access token for API calls
access_token = st.session_state.get("access_token")

stream_mode = True

# Initialize messages if not exists
if 'messages' not in st.session_state:
    st.session_state['messages'] = []

# Session Management (only if logged in)
if access_token:
    st.sidebar.markdown("---")
    st.sidebar.header("💬 Conversations")

    # Fetch sessions
    sessions = get_sessions(access_token)

    # Create new session button
    if st.sidebar.button("➕ New Conversation", key="new_session_btn"):
        st.session_state["current_session_id"] = str(uuid.uuid4())
        st.session_state["messages"] = []
        st.rerun()

    # Session selector
    session_ids = [s["session_id"] for s in sessions]

    # Check if current_session_id exists in sessions or is a new session
    current_session_id = st.session_state.get("current_session_id")
    is_new_session = current_session_id and current_session_id not in session_ids

    if sessions:
        if is_new_session:
            # Current session is new, add it to options
            session_options = ["New Conversation"] + session_ids + [current_session_id]
            selected_idx = len(session_options) - 1  # Last one is the new session
        else:
            session_options = ["New Conversation"] + session_ids
            selected_idx = 0
            if current_session_id:
                for i, s in enumerate(sessions):
                    if s["session_id"] == current_session_id:
                        selected_idx = i + 1
                        break

        selected_session = st.sidebar.selectbox(
            "Select Conversation",
            session_options,
            index=selected_idx,
            key="session_selector",
            format_func=lambda x: "New Conversation" if x == "New Conversation" else (
                f"{x[:8]}... - {next((s['last_message'][:30] for s in sessions if s['session_id'] == x), '')}"
            )
        )

        # Handle session change
        if selected_session == "New Conversation":
            new_session_id = str(uuid.uuid4())
        else:
            new_session_id = selected_session

        if new_session_id != st.session_state.get("current_session_id"):
            st.session_state["current_session_id"] = new_session_id
            st.session_state["messages"] = []

            # Load history if session selected
            if new_session_id and new_session_id in session_ids:
                history = get_history(new_session_id, access_token)
                st.session_state["messages"] = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in history
                ]
            st.rerun()

        # Delete session button
        if st.session_state.get("current_session_id"):
            if st.sidebar.button("🗑️ Delete Conversation", key="delete_session_btn"):
                if delete_session(st.session_state["current_session_id"], access_token):
                    st.session_state["current_session_id"] = None
                    st.session_state["messages"] = []
                    st.rerun()
    else:
        st.sidebar.info("No conversations yet")

    # Display current session ID
    if st.session_state.get("current_session_id"):
        st.sidebar.markdown(f"**Session:** `{st.session_state['current_session_id'][:16]}...`")

# Examples (disabled)
language = "ko"  # Default Korean


def render_template_expander(template: str, data: dict):
    """Render UI template data as Streamlit expanders."""
    if template == "product":
        items = data.get("products", [data])
        for item in items:
            with st.expander(f"🛞 {item.get('title', 'Product')}", expanded=True):
                col1, col2 = st.columns([1, 2])
                with col1:
                    if item.get("imageUrl"):
                        st.image(item["imageUrl"], width=150)
                with col2:
                    st.markdown(f"**{item.get('title', '')}**")
                    st.markdown(f"💰 {item.get('price', 0):,}원")
                    st.markdown(f"⭐ {item.get('rate', 0)}/5")
                    st.markdown(f"🏷️ {item.get('tiers', '')}")
                    st.markdown(f"🛋️ Comfort: {item.get('comfort', '')}")
                    st.markdown(f"📦 Stock: {item.get('totalQuantity', 0)}")
    elif template == "listCar":
        items = data.get("listCar", [data])
        for item in items:
            with st.expander(f"🚗 {item.get('licensePlate', 'Car')}", expanded=True):
                col1, col2 = st.columns([1, 2])
                with col1:
                    if item.get("imageUrl"):
                        st.image(item["imageUrl"], width=150)
                with col2:
                    st.markdown(f"**{item.get('description', '')}**")
                    st.markdown(f"🔖 {item.get('licensePlate', '')}")
    elif template == "voucher":
        items = data.get("vouchers", [data])
        for item in items:
            with st.expander(f"🎟️ {item.get('nameVoucher', 'Voucher')}", expanded=True):
                st.markdown(f"**{item.get('nameVoucher', '')}**")
                st.markdown(f"📝 {item.get('description', '')}")
                st.markdown(f"💸 {item.get('discount', '')}")
                st.markdown(f"📅 Valid until: {item.get('dateVoucher', '')}")
                if item.get("myCouponLink"):
                    st.markdown(f"[My Coupon]({item.get('myCouponLink')})")
                if item.get("downloadLink"):
                    st.markdown(f"[Download]({item.get('downloadLink')})")
    elif template == "location":
        items = data.get("locations", [data])
        for item in items:
            with st.expander(f"📍 {item.get('nameAddress', 'Store')}", expanded=True):
                st.markdown(f"**{item.get('nameAddress', '')}**")
                st.markdown(f"📌 {item.get('detailAddress', '')}")
                st.markdown(f"📏 Distance: {item.get('distance', '')} km")
                if item.get("lat") and item.get("long"):
                    st.markdown(f"🗺️ ({item.get('lat')}, {item.get('long')})")
    elif template == "datepick":
        with st.expander(f"📅 {data.get('date', 'Date Picker')}", expanded=True):
            st.markdown(f"**Available:** {'Yes' if data.get('available') else 'No'}")
            st.markdown("**Time slots:**")
            for slot in data.get("timeSlots", []):
                st.markdown(f"- {slot}")
    elif template == "question":
        with st.expander(f"❓ {data.get('question', 'Question')}", expanded=True):
            st.markdown(f"**{data.get('question', '')}**")
            for ans in data.get("listAnswer", []):
                st.markdown(f"- {ans.get('label', '')} ({ans.get('value', '')})")
    elif template == "billService":
        with st.expander("📄 Service Bill", expanded=True):
            st.markdown(f"**Car:** {data.get('carInfo', '')}")
            st.markdown(f"**Store:** {data.get('storeName', '')}")
            st.markdown(f"**Date:** {data.get('bookingDateTime', '')}")
            st.markdown(f"**Visit:** {data.get('visitMethod', '')}")
            st.markdown("**Services:**")
            for svc in data.get("services", []):
                st.markdown(f"- {svc.get('serviceName', '')} x{svc.get('quantity', 0)}: {svc.get('price', 0):,}원")
            st.markdown(f"**Total:** {data.get('totalAmount', 0):,}원")
            if data.get("actionLink"):
                st.markdown(f"[{data.get('actionText', 'Action')}]({data.get('actionLink')})")
    elif template == "billProduct":
        with st.expander("🛍️ Product Bill", expanded=True):
            st.markdown(f"**Car:** {data.get('carInfo', '')}")
            st.markdown(f"**Store:** {data.get('storeName', '')}")
            st.markdown(f"**Date:** {data.get('bookingDateTime', '')}")
            st.markdown(f"**Visit:** {data.get('visitMethod', '')}")
            st.markdown("**Products:**")
            for prod in data.get("products", []):
                st.markdown(f"- {prod.get('productName', '')} x{prod.get('quantity', 0)}: {prod.get('totalPrice', 0):,}원")
            st.markdown(f"**Payment:** {data.get('paymentAmount', 0):,}원")
            if data.get("actionLink"):
                st.markdown(f"[{data.get('actionText', 'Action')}]({data.get('actionLink')})")
            if data.get("cartLink"):
                st.markdown(f"[View Cart]({data.get('cartLink')})")
    elif template == "previewYoutube":
        items = data.get("items", [data])
        for item in items:
            with st.expander(f"🎬 {item.get('title', 'YouTube Video')}", expanded=True):
                st.markdown(f"**{item.get('title', '')}**")
                if item.get("thumbnailUrl"):
                    st.image(item["thumbnailUrl"], width=300)
                if item.get("youtubeUrl"):
                    st.markdown(f"[Watch on YouTube]({item.get('youtubeUrl')})")
    elif template == "questionCreateOrder":
        with st.expander("❓ Create Order", expanded=True):
            st.markdown(f"**Key:** {data.get('key', '')}")
            st.markdown(f"**Question:** {data.get('question', '')}")
            st.markdown(f"**Type:** {data.get('type', '')}")
            st.markdown(f"**Required:** {'Yes' if data.get('required') else 'No'}")
            for ans in data.get("listAnswer", []):
                st.markdown(f"- {ans.get('label', '')} ({ans.get('value', '')})")
    else:
        # Fallback: show as JSON
        with st.expander(f"📄 {template}", expanded=True):
            st.json(data)


chat_container = st.container()

with chat_container:
    for i, msg in enumerate(st.session_state['messages']):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

input_container = st.container()

with input_container:
    chat_disabled = not access_token

    if chat_disabled:
        st.chat_input(placeholder="Please enter access token to chat...", disabled=True)
        prompt = None
    else:
        prompt = st.chat_input(placeholder="Your question....")

if prompt:
    # Get current session ID
    current_session_id = st.session_state.get("current_session_id")

    with chat_container:
        with st.chat_message("user"):
            st.markdown(prompt)

    st.session_state['messages'].append({"role": "user", "content": prompt})

    with chat_container:
        with st.chat_message("assistant"):
            if stream_mode:
                # Tool calls display - list of expanders
                tool_calls = []

                # Data events for UI templates
                data_events = []

                # Agent flow display at top - list of steps
                agent_flow_steps = []
                agent_flow_placeholder = st.empty()

                message_placeholder = st.empty()
                full_response = ""

                try:
                    response_generator = send_chat_message(
                        content=prompt,
                        session_id=current_session_id,
                        stream=True,
                        access_token=access_token
                    )

                    for chunk in response_generator:
                        # Handle session info from first chunk
                        if chunk.get("type") == "session_info":
                            new_session_id = chunk.get("session_id")
                            if new_session_id and new_session_id != st.session_state.get("current_session_id"):
                                st.session_state["current_session_id"] = new_session_id
                            continue

                        if chunk.get("type") == "tool":
                            tool_name = chunk.get("tool", "")
                            tool_input = chunk.get("input", {})
                            tool_output = chunk.get("output", "")
                            tool_calls.append({"tool": tool_name, "input": tool_input, "output": tool_output})
                        elif chunk.get("type") == "agent_flow":
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
                                    steps_html += "<span style='margin: 0 8px; color: #6b7280; font-size: 14px; vertical-align: middle;'>→</span>"
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
                        elif chunk.get("type") == "data":
                            data_events.append(chunk)

                    message_placeholder.markdown(full_response)

                    # Render tool calls in Streamlit expanders above AF
                    if tool_calls:
                        with st.expander("🔧 Tools Called", expanded=True):
                            for i, tc in enumerate(tool_calls):
                                with st.expander(f"{tc['tool']}", expanded=False):
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.markdown("**INPUT:**")
                                        st.code(json.dumps(tc["input"], indent=2, ensure_ascii=False) if tc["input"] else "None", language="json")
                                    with col2:
                                        st.markdown("**OUTPUT:**")
                                        output_data = tc["output"]
                                        # Try to parse as JSON, fallback to text
                                        if isinstance(output_data, str):
                                            try:
                                                parsed = json.loads(output_data)
                                                output_text = json.dumps(parsed, indent=2, ensure_ascii=False)
                                            except (json.JSONDecodeError, TypeError):
                                                output_text = output_data
                                        else:
                                            output_text = json.dumps(output_data, indent=2, ensure_ascii=False)
                                        st.code(output_text, language="json")

                    # Render UI template events
                    if data_events:
                        with st.expander("📋 Results", expanded=True):
                            for item in data_events:
                                template = item.get("template", "")
                                data = item.get("data", {})
                                # Handle items array or single item
                                items = data.get("items", [data])
                                for single_item in items:
                                    render_template_expander(template, single_item)

                    bot_reply = full_response

                except Exception as e:
                    error_msg = f"Error when streaming: {e}"
                    message_placeholder.markdown(error_msg)
                    bot_reply = error_msg

            else:
                with st.spinner("Thinking..."):
                    bot_reply = send_chat_message(
                        content=prompt,
                        session_id=current_session_id,
                        stream=stream_mode,
                        access_token=access_token
                    )
                st.markdown(bot_reply)

    st.session_state['messages'].append({"role": "assistant", "content": bot_reply})

    # Refresh sessions to show the new conversation
    if access_token:
        sessions = get_sessions(access_token)
        # Check if current session_id is in the list, if not it was just created
        current = st.session_state.get("current_session_id")
        if current:
            session_ids = [s["session_id"] for s in sessions]
            if current not in session_ids:
                # Refresh to update session list
                st.rerun()

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