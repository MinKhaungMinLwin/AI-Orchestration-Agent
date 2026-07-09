import json
import uuid

import streamlit as st
import streamlit_nested_layout  # noqa: F401
from api.chat import send_chat_message, send_quick_order_action
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

    # Location input
    st.sidebar.markdown("---")
    st.sidebar.subheader("📍 Location")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.number_input("X (lon)", value=127.0276, format="%.4f", key="xpos_input")
    with col2:
        st.number_input("Y (lat)", value=37.4979, format="%.4f", key="ypos_input")
    xpos = st.session_state.xpos_input
    ypos = st.session_state.ypos_input

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
        st.session_state["last_quick_replies"] = []
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
            st.session_state["last_quick_replies"] = []

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
                    st.session_state["last_quick_replies"] = []
                    st.rerun()
    else:
        st.sidebar.info("No conversations yet")

    # Display current session ID
    if st.session_state.get("current_session_id"):
        st.sidebar.markdown(f"**Session:** `{st.session_state['current_session_id'][:16]}...`")

# Examples (disabled)
language = "ko"  # Default Korean


def _compact_dict(data: dict) -> dict:
    """Drop empty values while preserving nested contract payloads."""
    return {key: value for key, value in data.items() if value not in (None, "", {}, [])}


def _dict_value(value) -> dict:
    return value if isinstance(value, dict) else {}


def _metadata_at(data: dict, index: int) -> dict:
    metadata = data.get("metadata")
    if isinstance(metadata, list) and index < len(metadata):
        return _dict_value(metadata[index])
    if isinstance(metadata, dict):
        return metadata
    return {}


def _merge_slots(*sources: dict) -> dict:
    slots = {}
    for source in sources:
        slots.update(_dict_value(source))
    return _compact_dict(slots)


def _queue_template_action(action: dict) -> None:
    st.session_state["pending_template_action"] = action


def _render_data_debug(template: str, data: dict) -> None:
    with st.expander(f"Raw {template} payload", expanded=False):
        st.json(data)


def _action_from_metadata(item: dict, metadata: dict, label: str) -> dict | None:
    item = _dict_value(item)
    metadata = _dict_value(metadata)
    ui_action = dict(_dict_value(item.get("ui_action") or metadata.get("ui_action")))
    slots = _merge_slots(metadata.get("slots"), item.get("slots"), ui_action.get("slots"))

    if slots:
        ui_action["slots"] = slots
    if metadata and "metadata" not in ui_action:
        ui_action["metadata"] = metadata

    action_type = (
        ui_action.get("action_type")
        or ui_action.get("cta_action")
        or metadata.get("cta_action")
        or metadata.get("ctaAction")
    )
    if action_type and "action_type" not in ui_action:
        ui_action["action_type"] = action_type

    chip_context = dict(_dict_value(item.get("chip_context") or metadata.get("chip_context")))
    if not chip_context:
        chip_context = _compact_dict({
            "domain": metadata.get("domain"),
            "cta_action": metadata.get("cta_action") or metadata.get("ctaAction") or ui_action.get("cta_action"),
            "expected_behavior": metadata.get("expected_behavior") or ui_action.get("expected_behavior"),
            "source_intent": metadata.get("source_intent") or ui_action.get("source_intent"),
            "expected_contract_intent": (
                metadata.get("expected_contract_intent") or ui_action.get("expected_contract_intent")
            ),
            "slots": slots,
            "metadata": metadata,
        })

    ui_action = _compact_dict(ui_action)
    if not ui_action and not chip_context:
        return None

    return {
        "kind": "chat",
        "content": label,
        "chip_context": chip_context,
        "ui_action": ui_action,
    }


def _render_chat_action_button(item: dict, metadata: dict, *, label: str, key: str) -> None:
    action = _action_from_metadata(item, metadata, label)
    if not action:
        return
    st.button(label, key=f"template_action_{key}", on_click=_queue_template_action, args=(action,))


def _schedule_action(item: dict, hour, metadata: dict) -> dict | None:
    metadata = _dict_value(metadata)
    item = _dict_value(item)
    raw_day = (
        item.get("requested_cal_day")
        or item.get("requestedCalDay")
        or item.get("rawDate")
        or item.get("value")
        or metadata.get("requested_cal_day")
        or metadata.get("requestedCalDay")
    )
    if not raw_day:
        return None

    label = f"{item.get('date') or raw_day} {hour}:00"
    slots = _merge_slots(metadata.get("slots"), {"requested_cal_day": raw_day, "rsv_hour": hour})
    ui_action = dict(_dict_value(metadata.get("ui_action")))
    ui_action["slots"] = slots
    ui_action["metadata"] = metadata
    action_type = ui_action.get("action_type") or ui_action.get("cta_action") or metadata.get("cta_action")
    if action_type and "action_type" not in ui_action:
        ui_action["action_type"] = action_type

    chip_context = _compact_dict({
        "domain": metadata.get("domain"),
        "cta_action": metadata.get("cta_action") or ui_action.get("cta_action"),
        "expected_behavior": metadata.get("expected_behavior") or ui_action.get("expected_behavior"),
        "source_intent": metadata.get("source_intent") or ui_action.get("source_intent"),
        "expected_contract_intent": metadata.get("expected_contract_intent") or ui_action.get("expected_contract_intent"),
        "slots": slots,
        "metadata": {**metadata, "slots": slots},
    })
    return {
        "kind": "chat",
        "content": label,
        "chip_context": chip_context,
        "ui_action": _compact_dict(ui_action),
    }


def _render_preorder_actions(data: dict, key_prefix: str = "") -> None:
    metadata = _dict_value(data.get("metadata"))
    if data.get("isReadyToOrder") and metadata:
        st.button(
            "Order",
            key=f"template_action_{key_prefix}_preorder_order",
            on_click=_queue_template_action,
            args=({"kind": "quick_order", "content": "Order", "payload": metadata},),
        )


def render_template_expander(template: str, data: dict, key_prefix: str = ""):
    """Render UI template data as Streamlit expanders."""
    _render_data_debug(template, data)
    if template == "product":
        items = data.get("products", [data])
        for idx, item in enumerate(items):
            metadata = _metadata_at(data, idx)
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
                    _render_chat_action_button(
                        item,
                        metadata,
                        label=f"Select {item.get('titleProductName') or item.get('title') or 'product'}",
                        key=f"{key_prefix}_product_{idx}",
                    )
    elif template == "listCar":
        items = data.get("listCar", [data])
        for idx, item in enumerate(items):
            metadata = _metadata_at(data, idx)
            with st.expander(f"🚗 {item.get('licensePlate', 'Car')}", expanded=True):
                col1, col2 = st.columns([1, 2])
                with col1:
                    if item.get("imageUrl"):
                        st.image(item["imageUrl"], width=150)
                with col2:
                    st.markdown(f"**{item.get('description', '')}**")
                    st.markdown(f"🔖 {item.get('licensePlate', '')}")
                    _render_chat_action_button(
                        item,
                        metadata,
                        label=f"Select {item.get('licensePlate') or 'car'}",
                        key=f"{key_prefix}_list_car_{idx}",
                    )
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
        items = data.get("locations") or data.get("stores") or [data]
        for idx, item in enumerate(items):
            metadata = _metadata_at(data, idx)
            badges = []
            if item.get("isAllMyT"):
                badges.append("🏆 All My T")
            if item.get("todayInstall"):
                badges.append("🔧 오늘 장착")
            if item.get("tnaDelivery"):
                badges.append("🚚 T바로배송")

            badge_text = " | ".join(badges) if badges else ""
            expander_label = f"📍 {item.get('nameAddress', 'Store')}"
            if badge_text:
                expander_label += f" [{badge_text}]"

            with st.expander(expander_label, expanded=True):
                st.markdown(f"**{item.get('nameAddress', '')}**")
                st.markdown(f"📌 {item.get('detailAddress', '')}")
                st.markdown(f"📏 Distance: {item.get('distance', '')} km")
                if badges:
                    st.markdown(f"**Badges:** {badge_text}")
                if item.get("lat") and item.get("long"):
                    st.markdown(f"🗺️ ({item.get('lat')}, {item.get('long')})")
                _render_chat_action_button(
                    item,
                    metadata,
                    label=f"Select {item.get('nameAddress') or metadata.get('shopName') or 'store'}",
                    key=f"{key_prefix}_location_{idx}",
                )
    elif template == "datepick":
        dates = data.get("dates", [data])
        selected_idx = data.get("selectedDate")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        selected_date_str = ""
        if selected_idx is not None and 0 <= selected_idx < len(dates):
            selected_date_str = dates[selected_idx].get("date", "")
        with st.expander(f"📅 Date Picker {'(selected: ' + selected_date_str + ')' if selected_date_str else ''}", expanded=True):
            for item in dates:
                date_str = item.get("date", "")
                idx = item.get("index", "")
                available = item.get("available", False)
                times = item.get("availableTimes", [])
                badges = []
                if available:
                    badges.append("✓ Available")
                else:
                    badges.append("✗ Unavailable")
                if not times:
                    badges.append("Fully booked")
                badge_text = " | ".join(badges)
                marker = "→ " if selected_idx is not None and dates[selected_idx].get("date") == date_str else "  "
                st.markdown(f"{marker}**{date_str}** [{idx}] {badge_text}")
                if times:
                    st.markdown(f"   Available times: {', '.join(str(t) + ':00' for t in times)}")
                    cols = st.columns(min(len(times), 4))
                    for time_idx, hour in enumerate(times):
                        action = _schedule_action(item, hour, metadata)
                        if action:
                            with cols[time_idx % len(cols)]:
                                st.button(
                                    f"{hour}:00",
                                    key=f"{key_prefix}_datepick_{item.get('index', idx)}_{hour}",
                                    on_click=_queue_template_action,
                                    args=(action,),
                                )
    elif template == "question":
        with st.expander(f"❓ {data.get('question', 'Question')}", expanded=True):
            st.markdown(f"**{data.get('question', '')}**")
            for idx, ans in enumerate(data.get("listAnswer", [])):
                st.markdown(f"- {ans.get('label', '')} ({ans.get('value', '')})")
                _render_chat_action_button(
                    ans,
                    ans.get("metadata") if isinstance(ans.get("metadata"), dict) else {},
                    label=str(ans.get("label") or ans.get("value") or "Select"),
                    key=f"{key_prefix}_question_{idx}",
                )
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
                    st.markdown(f"🖼️ {item.get('thumbnailUrl', '')}")
                if item.get("youtubeUrl"):
                    st.markdown(f"🔗 {item.get('youtubeUrl', '')}")
    elif template == "event":
        items = data.get("events", [data])
        for item in items:
            badge = item.get("badge", "")
            title = f"🎉 {item.get('eventName', 'Event')}" + (f" [{badge}]" if badge else "")
            with st.expander(title, expanded=True):
                st.markdown(f"**{item.get('eventName', '')}**")
                if item.get("period"):
                    st.markdown(f"📅 기간: {item.get('period', '')}")
                if item.get("eventUrl"):
                    st.markdown(f"🔗 {item.get('eventUrl', '')}")
                if item.get("actionLink") and item.get("actionText"):
                    st.markdown(f"[{item.get('actionText', 'Action')}]({item.get('actionLink')})")
    elif template == "preOrder":
        order_info = data.get("orderInfo", {})
        recommend_actions = data.get("recommendActions", [])
        is_ready_to_order = data.get("isReadyToOrder", False)
        is_ready_to_add_to_cart = data.get("isReadyToAddToCart", False)

        with st.expander("📋 Pre-Order Preview", expanded=True):
            st.markdown("### Order Info")
            # Build status table
            fields = [
                ("Car", order_info.get("carInfo")),
                ("Product", order_info.get("product")),
                ("Quantity", order_info.get("quantity")),
                ("Store", order_info.get("storeName")),
                ("Booking Date", order_info.get("bookingDateTime")),
                ("Visit Method", order_info.get("visitMethod")),
                ("Payment", order_info.get("paymentAmount")),
            ]
            for field_name, field_value in fields:
                if field_value is not None and field_value != "":
                    st.markdown(f"✅ **{field_name}:** {field_value}")
                else:
                    st.markdown(f"❌ **{field_name}:** -")

            st.markdown("---")
            st.markdown(f"**Ready to Add to Cart:** {'✅ Yes' if is_ready_to_add_to_cart else '❌ No'}")
            st.markdown(f"**Ready to Order:** {'✅ Yes' if is_ready_to_order else '❌ No'}")

            # Show recommend actions
            if recommend_actions:
                st.markdown("---")
                st.markdown("### Recommend Actions")
                st.markdown(f"**{recommend_actions.get('question', '')}**")
                for action in recommend_actions.get("listActions", []):
                    st.markdown(f"- {action}")
            _render_preorder_actions(data, key_prefix)
    elif template == "questionCreateOrder":
        with st.expander("❓ Create Order", expanded=True):
            st.markdown(f"**Key:** {data.get('key', '')}")
            st.markdown(f"**Question:** {data.get('question', '')}")
            st.markdown(f"**Type:** {data.get('type', '')}")
            st.markdown(f"**Required:** {'Yes' if data.get('required') else 'No'}")
            for idx, ans in enumerate(data.get("listAnswer", [])):
                st.markdown(f"- {ans.get('label', '')} ({ans.get('value', '')})")
                _render_chat_action_button(
                    ans,
                    ans.get("metadata") if isinstance(ans.get("metadata"), dict) else {},
                    label=str(ans.get("label") or ans.get("value") or "Select"),
                    key=f"{key_prefix}_question_create_order_{idx}",
                )
    else:
        # Fallback: show as JSON
        with st.expander(f"📄 {template}", expanded=True):
            st.json(data)


def _render_tool_calls(tool_calls: list[dict]) -> None:
    if not tool_calls:
        return
    with st.expander("🔧 Tools Called", expanded=False):
        for tc in tool_calls:
            with st.expander(f"{tc['tool']}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**INPUT:**")
                    st.code(json.dumps(tc["input"], indent=2, ensure_ascii=False) if tc["input"] else "None", language="json")
                with col2:
                    st.markdown("**OUTPUT:**")
                    output_data = tc["output"]
                    if isinstance(output_data, str):
                        try:
                            output_text = json.dumps(json.loads(output_data), indent=2, ensure_ascii=False)
                        except (json.JSONDecodeError, TypeError):
                            output_text = output_data
                    else:
                        output_text = json.dumps(output_data, indent=2, ensure_ascii=False)
                    st.code(output_text, language="json")


def _render_saved_message(msg: dict, index: int) -> None:
    content = str(msg.get("content") or "")
    if content:
        st.markdown(content)
    for event_idx, event in enumerate(msg.get("templates") or []):
        if not isinstance(event, dict):
            continue
        render_template_expander(
            str(event.get("template") or ""),
            event.get("data") if isinstance(event.get("data"), dict) else {},
            key_prefix=f"history_{index}_{event_idx}",
        )
    _render_tool_calls(msg.get("tool_calls") or [])

chat_container = st.container()

with chat_container:
    for i, msg in enumerate(st.session_state['messages']):
        with st.chat_message(msg["role"]):
            _render_saved_message(msg, i)

def _queue_quick_reply_chip(chip: dict) -> None:
    """Chip click → queue an actionable message; the payload is sent as chip_context/ui_action."""
    st.session_state["pending_chip"] = chip


def _chip_request_fields(chip: dict) -> tuple[dict, dict]:
    """Build the chat request `chip_context` and `ui_action` payloads from an emitted chip."""
    metadata = chip.get("metadata") if isinstance(chip.get("metadata"), dict) else {}
    chip_context = {
        "domain": chip.get("domain"),
        "actionId": chip.get("actionId") or chip.get("action_id"),
        "intentKey": chip.get("intentKey") or chip.get("intent_key"),
        "cta_id": chip.get("cta_id") or metadata.get("cta_id"),
        "cta_action": chip.get("cta_action") or metadata.get("cta_action"),
        "expected_behavior": chip.get("expected_behavior") or metadata.get("expected_behavior"),
        "source_intent": metadata.get("source_intent"),
        "expected_contract_intent": (
            chip.get("expected_contract_intent") or metadata.get("expected_contract_intent")
        ),
        "slots": metadata.get("slots"),
        "metadata": metadata,
    }
    chip_context = {k: v for k, v in chip_context.items() if v not in (None, "", {}, [])}
    action_type = chip_context.get("cta_action") or chip_context.get("actionId")
    ui_action = {
        "action_type": action_type,
        "label": chip.get("label"),
        "entity_label": chip.get("label"),
        "intentKey": chip_context.get("intentKey"),
        "expected_behavior": chip_context.get("expected_behavior"),
        "expected_contract_intent": chip_context.get("expected_contract_intent"),
        "slots": metadata.get("slots"),
        "metadata": metadata,
    }
    ui_action = {k: v for k, v in ui_action.items() if v not in (None, "", {}, [])}
    return chip_context, ui_action


chips_container = st.container()


def render_quick_reply_chips() -> None:
    """Fill the chips placeholder from session state.

    Called at the END of the script run (see bottom of file) so chips captured
    while streaming THIS turn's response show immediately — rendering here
    inline would display the previous turn's chips (one-turn lag).
    """
    with chips_container:
        quick_reply_chips = st.session_state.get("last_quick_replies") or []
        if quick_reply_chips and access_token:
            cols = st.columns(min(len(quick_reply_chips), 4))
            for idx, chip in enumerate(quick_reply_chips[:4]):
                label = str(chip.get("label") or "")
                with cols[idx % len(cols)]:
                    if chip.get("url"):
                        st.link_button(label, str(chip["url"]))
                    else:
                        st.button(
                            label,
                            key=f"quick_reply_chip_{idx}",
                            on_click=_queue_quick_reply_chip,
                            args=(chip,),
                        )

input_container = st.container()

with input_container:
    chat_disabled = not access_token

    if chat_disabled:
        st.chat_input(placeholder="Please enter access token to chat...", disabled=True)
        prompt = None
    else:
        prompt = st.chat_input(placeholder="Your question....")

pending_chip = st.session_state.pop("pending_chip", None)
pending_template_action = st.session_state.pop("pending_template_action", None)
chip_context_payload = None
ui_action_payload = None
quick_order_payload = None
outgoing_kind = "chat"
if prompt:
    outgoing_message = prompt
elif pending_chip:
    outgoing_message = str(pending_chip.get("label") or "")
    chip_context_payload, ui_action_payload = _chip_request_fields(pending_chip)
elif pending_template_action:
    outgoing_kind = str(pending_template_action.get("kind") or "chat")
    outgoing_message = str(pending_template_action.get("content") or "")
    chip_context_payload = pending_template_action.get("chip_context")
    ui_action_payload = pending_template_action.get("ui_action")
    quick_order_payload = pending_template_action.get("payload")
else:
    outgoing_message = None

if outgoing_message:
    prompt = outgoing_message
    # A new turn starts: the previous turn's chips are no longer valid actions.
    st.session_state["last_quick_replies"] = []

    # Get current session ID
    current_session_id = st.session_state.get("current_session_id")

    with chat_container:
        with st.chat_message("user"):
            st.markdown(prompt)

    st.session_state['messages'].append({"role": "user", "content": prompt})

    with chat_container:
        with st.chat_message("assistant"):
            if stream_mode:
                tool_calls = []
                template_events = []
                assistant_response_from_data = ""
                status_placeholder = st.empty()
                message_placeholder = st.empty()
                full_response = ""

                try:
                    if outgoing_kind == "quick_order":
                        response_generator = send_quick_order_action(
                            session_id=current_session_id,
                            payload=quick_order_payload or {},
                            access_token=access_token,
                        )
                    else:
                        response_generator = send_chat_message(
                            content=prompt,
                            session_id=current_session_id,
                            stream=True,
                            access_token=access_token,
                            user_info={"location": {"xpos": st.session_state.xpos_input, "ypos": st.session_state.ypos_input}},
                            chip_context=chip_context_payload,
                            ui_action=ui_action_payload,
                        )

                    for chunk in response_generator:
                        if chunk.get("type") == "session_info":
                            new_session_id = chunk.get("session_id")
                            if new_session_id and new_session_id != st.session_state.get("current_session_id"):
                                st.session_state["current_session_id"] = new_session_id
                            continue

                        if chunk.get("type") == "tool":
                            tool_calls.append({
                                "tool": chunk.get("tool", ""),
                                "input": chunk.get("input", {}),
                                "output": chunk.get("output", ""),
                            })
                        elif chunk.get("type") == "status":
                            status_val = chunk.get("status", "")
                            if status_val == "tool_start":
                                display_name = chunk.get("display_name", "처리 중...")
                                status_placeholder.markdown(f"⚙️ *{display_name}*")
                            else:
                                status_placeholder.markdown(f"⚙️ *{status_val}*")
                        elif chunk.get("type") == "token":
                            status_placeholder.empty()
                            full_response += chunk.get("content", "")
                            message_placeholder.markdown(full_response + "▌")
                        elif chunk.get("type") == "error":
                            full_response += f"\nError: {chunk.get('content', '')}"
                            message_placeholder.markdown(full_response or assistant_response_from_data)
                        elif chunk.get("type") == "data":
                            status_placeholder.empty()
                            data_payload = chunk.get("data", {}) or {}
                            template_events.append({"template": chunk.get("template", ""), "data": data_payload})
                            if isinstance(data_payload, dict) and data_payload.get("assistantResponse"):
                                assistant_response_from_data = data_payload["assistantResponse"]
                            if chunk.get("template") == "quickReply" and isinstance(data_payload, dict):
                                st.session_state["last_quick_replies"] = [
                                    chip for chip in (data_payload.get("quickReplies") or [])
                                    if isinstance(chip, dict) and chip.get("label")
                                ]
                            render_template_expander(chunk.get("template", ""), data_payload)

                    message_placeholder.markdown(full_response or assistant_response_from_data)
                    status_placeholder.empty()

                    _render_tool_calls(tool_calls)

                    bot_reply = full_response or assistant_response_from_data

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
                        access_token=access_token,
                        user_info={"location": {"xpos": st.session_state.xpos_input, "ypos": st.session_state.ypos_input}},
                        chip_context=chip_context_payload,
                        ui_action=ui_action_payload,
                    )
                st.markdown(bot_reply)

    st.session_state['messages'].append({
        "role": "assistant",
        "content": bot_reply,
        "templates": template_events if stream_mode else [],
        "tool_calls": tool_calls if stream_mode else [],
    })

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

render_quick_reply_chips()

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
