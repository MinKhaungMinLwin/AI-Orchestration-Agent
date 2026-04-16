from enum import Enum
from typing import Annotated, Any

from langchain.tools import tool


def _success_response(http_status: int, data: Any) -> dict:
    return {"status": "success", "http_status": http_status, "data": data}


def _error_response(http_status: int | None, reason: str, message: str) -> dict:
    return {"status": "error", "http_status": http_status, "reason": reason, "message": message}


@tool
def list_car_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    items: Annotated[list[dict], "List of cars. Each: licensePlate (str), description (str), imageUrl (str)"],
    metadata: Annotated[list[dict], "List of metadata objects. Each: carNo (str, required), carLncCd (str, optional). Rule: REQUIRED — must be provided."],
) -> dict:
    """Render car list cards.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        items: List of car objects.
        metadata: List of metadata objects with car IDs. Each contains:
            - carNo (str): Car registration number (from car_no field in domain agent output).
            - carLncCd (str, optional): Car launch code (from car_lnc_cd field).

    Field Details:
        - licensePlate (str): Car license plate number. Rule: required, non-empty string.
        - description (str): Short description of the car. Rule: required, non-empty string.
        - imageUrl (str): URL of car image. Rule: required, valid URL string.

    Returns:
        {"status": "success", "http_status": 200, "data": {"listCar": items, "assistantResponse": assistant_response, "metadata": metadata}}
    """
    return _success_response(200, {"listCar": items, "assistantResponse": assistant_response, "metadata": metadata})


@tool
def list_product_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    items: Annotated[list[dict], "List of products. Each: imageUrl (str), title (str), tires (str), comfort (str), price (int), rate (float), totalQuantity (int), description (str)"],
    metadata: Annotated[list[dict], "List of metadata objects. Each: goodsId (str, required). Rule: REQUIRED — must be provided."],
) -> dict:
    """Render product list cards.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        items: List of product objects.
        metadata: List of metadata objects with product IDs. Each contains:
            - goodsId (str): Product number (from goods_no field in domain agent output).

    Field Details:
        - imageUrl (str): URL of product image. Rule: required, valid URL string.
        - title (str): Product name. Rule: required, non-empty string.
        - tires (str): Product tier/category. Rule: optional, string (e.g., "SUV", "Sedan").
        - comfort (str): Comfort level. Rule: optional, string (e.g., "high", "medium", "low").
        - price (int): Product price in KRW. Rule: required, 0 <= price.
        - rate (float): Rating score. Rule: required, 0 <= rate <= 5.
        - totalQuantity (int): Total stock quantity. Rule: required, 0 <= totalQuantity.
        - description (str): Comprehensive product info in markdown format. Include ALL available from product data:
            • pc_prod_remark_desc: Key features (주요 특장점)
            • pc_prod_tech_desc: Technology description (기술력 설명)
            • slogan: Product slogan
            • rating: review count and average rating
            • Any other available fields
            Format as readable markdown with sections.

    Returns:
        {"status": "success", "http_status": 200, "data": {"products": items, "assistantResponse": assistant_response, "metadata": metadata}}
    """
    return _success_response(200, {"products": items, "assistantResponse": assistant_response, "metadata": metadata})


@tool
def list_voucher_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    items: Annotated[list[dict], "List of vouchers. Each: nameVoucher (str), discount (str), dateVoucher (str), downloadLink (str)"],
    metadata: Annotated[list[dict], "List of metadata objects. Each: couponId (str, required). Rule: REQUIRED — must be provided."],
) -> dict:
    """Render voucher list cards.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        items: List of voucher objects.
        metadata: List of metadata objects with coupon IDs. Each contains:
            - couponId (str): Coupon ID (from cpn_no field in domain agent output).

    Field Details:
        - nameVoucher (str): Voucher name (source: cpn_nm). Rule: required, non-empty string.
        - discount (str): Discount value (source: rt_amt_val). Rule: required, string (e.g., "10%", "50,000원").
        - dateVoucher (str): Expiry date (source: use_end_dtime). Rule: required, string format (e.g., "2024-12-31").
        - downloadLink (str): Link to download voucher. Rule: optional, valid URL string. If BE returns null, mock the link.

    Returns:
        {"status": "success", "http_status": 200, "data": {"vouchers": items, "assistantResponse": assistant_response, "metadata": metadata}}
    """

    _MY_COUPON_LINK = {
        "pc": "https://wwwqa.tstation.com/mypage/tstation/coupon/couponList",
        "mobile": "https://mqa.tstation.com/coupon/myCouponList",
    }

    for item, meta in zip(items, metadata):
        item["myCouponLink"] = _MY_COUPON_LINK
        item["metadata"] = meta
    return _success_response(200, {"vouchers": items, "assistantResponse": assistant_response, "metadata": metadata})


@tool
def list_location_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    items: Annotated[list[dict], "List of locations. Each: nameAddress (str), distance (str), detailAddress (str), isAllMyT (bool), todayInstall (bool), tnaDelivery (bool), description (str)"],
    metadata: Annotated[list[dict], "List of metadata objects. Each: shopId (str, required). Rule: REQUIRED — must be provided."],
) -> dict:
    """Render location list cards.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        items: List of location/store objects.
        metadata: List of metadata objects with store IDs. Each contains:
            - shopId (str): Store ID (from shop_id field in domain agent output).

    Field Details:
        - nameAddress (str): Location/store name (src: shop_nm). Rule: required, non-empty string.
        - distance (str): Distance from user location (src: distance). Rule: required, string (e.g., "2.5km").
        - detailAddress (str): Full address (src: road_addr_base + road_addr_dtl or addr_base + addr_dtl). Rule: required, non-empty string.
        - isAllMyT (bool): All My T badge (src: is_all_my_t from /api/store/detail or /api/store/list). Rule: optional, default false.
        - todayInstall (bool): Today Install badge (src: is_installable from /api/store/detail). Rule: optional, default false.
        - tnaDelivery (bool): T-NA Delivery badge (src: is_tna_delivery from /api/store/detail). Rule: optional, default false.
        - description (str): Comprehensive store info in markdown format. Include ALL available from store data:
            • Business hours: shop_biz_strt_wday~shop_biz_end_wday, shop_biz_strt_time~shop_biz_end_time
            • Saturday hours: shop_sat_strt_time~shop_sat_end_time
            • Holiday closed: holiday
            • Phone: tel_no
            • Services: is_installable, is_tna_delivery, is_all_my_t
            • Address: addr_base+addr_dtl or road_addr_base+road_addr_dtl
            • Available slots: available_slots (if available)
            Format as readable markdown.

    Returns:
        {"status": "success", "http_status": 200, "data": {"locations": items, "assistantResponse": assistant_response, "metadata": metadata}}
    """
    return _success_response(200, {"locations": items, "assistantResponse": assistant_response, "metadata": metadata})


@tool
def list_event_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    items: Annotated[list[dict], "List of events. Each: eventName (str), bannerImage (str), eventUrl (str), badge (str), period (str), actionLink (str), actionText (str)"],
    metadata: Annotated[list[dict], "List of metadata objects. Each: eventId (str, required). Rule: REQUIRED — must be provided."],
) -> dict:
    """Render event list cards.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        items: List of event objects.
        metadata: List of metadata objects with event IDs. Each contains:
            - eventId (str): Event ID (from evt_no field in domain agent output).

    Field Details:
        - eventName (str): Event name (src: evt_nm). Rule: required, non-empty string.
        - bannerImage (str): Banner image URL (src: bnr_img_url_addr). Rule: optional, may be relative path.
        - eventUrl (str): Event detail page URL or path (src: evt_url_addr). Rule: optional.
        - badge (str): Event badge name (src: evt_badge_nm). Rule: optional, string (e.g., "주유권증정").
        - period (str): Event period (src: evt_strt_dtime ~ evt_end_dtime). Rule: optional, string (e.g., "2026-03-27 ~ 2026-04-30").
        - actionLink (str): Action button link. Rule: optional, valid URL string.
        - actionText (str): Action button text. Rule: optional, non-empty string (e.g., "자세히 보기").

    Returns:
        {"status": "success", "http_status": 200, "data": {"events": items, "assistantResponse": assistant_response, "metadata": metadata}}
    """
    return _success_response(200, {"events": items, "assistantResponse": assistant_response, "metadata": metadata})


@tool
def list_preview_youtube_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    items: Annotated[list[dict], "List of videos. Each: title (str), thumbnailUrl (str), youtubeUrl (str), videoId (str)"],
) -> dict:
    """Render YouTube video preview cards.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        items: List of YouTube video objects.

    Field Details:
        - title (str): Video title. Rule: required, non-empty string.
        - thumbnailUrl (str): URL of video thumbnail. Rule: required, valid URL string.
        - youtubeUrl (str): YouTube video link. Rule: required, valid URL string (youtube.com or youtu.be).
        - videoId (str): YouTube video ID. Rule: optional, string (e.g., "dQw4w9WgXcQ").

    Returns:
        {"status": "success", "http_status": 200, "data": {"items": items, "assistantResponse": assistant_response}}
    """
    return _success_response(200, {"items": items, "assistantResponse": assistant_response})


@tool
def available_dates_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    dates: Annotated[list[dict], "List of date entries. Each: date (str '2026년 4월 9일 (화)'), available (bool), availableTimes (list[int 8-22]), index (int 0-based position in sorted order)"],
    metadata: Annotated[dict, "Metadata object: shopId (str, required). Rule: REQUIRED — must be provided."],
    selectedDate: Annotated[int | None, "Selected date index in dates list (0-based)"] = None,
) -> dict:
    """Render available dates with time slots for booking (calendar month view).

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        dates: List of date entries. Each entry contains:
            - index: int - 0-based position in sorted order (0 = earliest date).
            - date: str in format "2026년 4월 9일 (화)" (year년 month월 day일 (weekday)).
            - available: bool - whether date can be selected.
            - availableTimes: list[int 8-22] - available hours. Empty = fully booked.
        metadata: Metadata object containing:
            - shopId (str): Store ID (from shop_id field in domain agent output).
        selectedDate: Selected date index. Rule: optional, int index (0-based).

    Returns:
        {"status": "success", "http_status": 200, "data": {"dates": ..., "selectedDate": ..., "assistantResponse": ..., "metadata": ...}}
    """
    return _success_response(200, {
        "dates": dates,
        "selectedDate": selectedDate,
        "assistantResponse": assistant_response,
        "metadata": metadata,
    })


@tool
def preorder_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    orderInfo: Annotated[dict, "Order info. Each field is optional: carInfo (str), product (str), quantity (int), storeName (str), bookingDateTime (str), visitMethod (str), paymentAmount (float)"],
    recommendActions: Annotated[dict, "Recommend action: question (str), listActions (list[str])"],
    isReadyToOrder: Annotated[bool, "True if all required info is available for quick_order (carInfo + product + quantity + storeName + bookingDateTime)."],
    isReadyToAddToCart: Annotated[bool, "True if all required info is available for save_to_cart (carInfo + product + quantity)"],
    metadata: Annotated[dict, "Metadata object with raw IDs: goodsId (str, optional), shopId (str, optional), carNo (str, optional), carLncCd (str, optional). Rule: REQUIRED — must be provided."],
) -> dict:
    """Render pre-order card with order info and recommend actions.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        orderInfo: Order information containing available fields:
            - carInfo (str): Car information.
            - product (str): Product name.
            - quantity (int): Order quantity.
            - storeName (str): Store name.
            - bookingDateTime (str): Booking date and time.
            - visitMethod (str): Visit method (e.g., "Visit in Person").
            - paymentAmount (float): Payment amount.
        recommendActions: Recommend action containing:
            - question (str): Question text.
            - listActions (list[str]): List of action labels.
        isReadyToOrder: True if all required info for quick_order (carInfo + product + quantity + storeName).
        isReadyToAddToCart: True if all required info for save_to_cart (carInfo + product + quantity).
        metadata: Raw IDs extracted from domain agent outputs:
            - goodsId (str, optional): Product number (goods_no).
            - shopId (str, optional): Store ID (shop_id).
            - carNo (str, optional): Car registration number (car_no).
            - carLncCd (str, optional): Car launch code (car_lnc_cd).

    Returns:
        {"status": "success", "http_status": 200, "data": {"orderInfo": ..., "recommendActions": ..., "isReadyToOrder": ..., "isReadyToAddToCart": ..., "assistantResponse": ..., "metadata": ...}}
    """
    return _success_response(200, {
        "orderInfo": orderInfo,
        "recommendActions": recommendActions,
        "isReadyToOrder": isReadyToOrder,
        "isReadyToAddToCart": isReadyToAddToCart,
        "assistantResponse": assistant_response,
        "metadata": metadata,
    })




@tool
def qna_complete_tool(
    redictLink: Annotated[dict, "MUST be copied verbatim from transfer_to_qna_tool result `redictLink` — contains {pc: str, mobile: str}. Do NOT generate or modify these URLs."],
    cnslType: Annotated[str, "Inquiry type label (e.g., '반품/교환/환불', '주문/결제/배송', '상품문의') — map from transfer_to_qna_tool result `cnsl_clss_seq`"],
    title: Annotated[str, "Inquiry title — copy from transfer_to_qna_tool result `inq_tit_nm` (max 100 chars)"],
    summary: Annotated[str, "Inquiry summary for display — copy from transfer_to_qna_tool result `ai_summary` (truncate to 200 chars)"],
    assistantResponse: Annotated[str, "Concise Korean message for the user (e.g., '1:1 문의 페이지로 이동합니다. 내용을 확인하고 제출해 주세요.')"],
) -> dict:
    """Render 1:1 inquiry redirect card with PC and mobile links.

    CRITICAL RULES:
    - redictLink MUST be copied VERBATIM from transfer_to_qna_tool result `redictLink`
    - Do NOT generate URLs, do NOT append query params (no orderNo, no type, etc.)
    - The URLs are already AES-encoded with cnsl_clss_seq + inq_tit_nm + ai_summary

    Args:
        redictLink: From transfer_to_qna_tool result `redictLink` — {{"pc": "...", "mobile": "..."}}
        cnslType: Inquiry type label mapped from transfer_to_qna_tool result `cnsl_clss_seq`:
            10002 → "상품문의", 10006 → "주문/결제/배송", 10010 → "반품/교환/환불",
            10013 → "제공서비스/이벤트/혜택", 10017 → "회원", 10019 → "기타",
            10025 → "가맹점제휴문의", 10034 → "이력서접수"
        title: From transfer_to_qna_tool result `inq_tit_nm`
        summary: From transfer_to_qna_tool result `ai_summary` (display only, max 200 chars)
        assistantResponse: Short Korean message to show alongside the card

    Returns:
        {{"status": "success", "http_status": 200, "data": {{"assistantResponse": ..., "redictLink": {{"pc": ..., "mobile": ...}}, "cnslType": ..., "title": ..., "summary": ...}}}}
    """
    return _success_response(200, {
        "redictLink": redictLink,
        "cnslType": cnslType,
        "title": title,
        "summary": summary,
        "assistantResponse": assistantResponse,
    })


class OrderCompleteType(str, Enum):
    CART = "cart"
    ORDER = "order"


@tool
def order_complete_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    orderInfo: Annotated[dict, "Order info: carInfo (str), product (str), quantity (int), storeName (str), bookingDateTime (str | None), visitMethod (str | None), paymentAmount (float | None)"],
    is_success: Annotated[bool, "True if order/cart succeeded, False if failed"],
    type: Annotated[OrderCompleteType, "Type: cart or order"],
    message: Annotated[str | None, "Error message when is_success is False"],
    data: Annotated[dict, "From quick_order_tool output.data.data when status=success, null when fail."],
    metadata: Annotated[dict, "Metadata object with raw IDs: ordNo (str, optional), goodsId (str, optional), shopId (str, optional). Rule: REQUIRED — must be provided."],
) -> dict:
    """Render order completion card.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        orderInfo: Order info containing: carInfo, product, quantity, storeName, bookingDateTime, visitMethod, paymentAmount
        is_success: True if order/cart succeeded, False if failed
        type: Order type - cart or order
        message: Error message when is_success is False (null when success)
        data: Data from quick_order_tool. When output[status] is true, data is output.data.data, {} when is_success is False.
        metadata: Raw IDs from order response:
            - ordNo (str, optional): Order number (ord_no).
            - goodsId (str, optional): Product number (goods_no).
            - shopId (str, optional): Store ID (shop_id).

    Returns:
        {"status": "success", "http_status": 200, "data": {"orderInfo": ..., "isSuccess": ..., "type": ..., "message": ..., "data": ..., "assistantResponse": ..., "metadata": ...}}
    """
    return _success_response(200, {
        "orderInfo": orderInfo,
        "isSuccess": is_success,
        "type": type.value,
        "message": message,
        "data": data if is_success else {},
        "assistantResponse": assistant_response,
        "metadata": metadata,
    })


@tool
def cheapest_product_tool(
    assistant_response: Annotated[str, "Message text to display with template"],
    items: Annotated[list[dict], "List with single cheapest product. Each: title (str), originalPrice (int), quantity (int), totalDiscount (int), productDiscount (int), couponDiscount (int), finalPrice (int)"],
    metadata: Annotated[list[dict], "List of metadata objects. Each: goodsId (str, required)."],
) -> dict:
    """Render cheapest product / price comparison card.

    Used when compare_discount_tool is called - shows ONLY the cheapest product.
    Displays price breakdown: original price, discounts, and final price.

    Args:
        assistant_response (str): Chatbot-style intro message (NO data details, NO duplicate with template). In Korean.
        items: List with single cheapest product. Each contains:
            - title (str): Product name (e.g., "Ventus S2 AS")
            - originalPrice (int): Original price per unit (sale_prc)
            - quantity (int): Quantity (e.g., 4 for 4 tires)
            - totalDiscount (int): Total discount amount (total_discount)
            - productDiscount (int): Product discount per unit (product_discount)
            - couponDiscount (int): Coupon discount per unit (coupon_discount)
            - finalPrice (int): Final price per unit after all discounts (final_unit_price)
        metadata: List of metadata objects with product IDs.

    Example item:
        {
            "title": "Ventus S2 AS",
            "originalPrice": 521000,
            "quantity": 4,
            "totalDiscount": 22000,
            "productDiscount": 13000,
            "couponDiscount": 9000,
            "finalPrice": 499000
        }

    Returns:
        {"status": "success", "http_status": 200, "data": {"cheapestProduct": items, "assistantResponse": assistant_response, "metadata": metadata}}
    """
    return _success_response(200, {"cheapestProduct": items, "assistantResponse": assistant_response, "metadata": metadata})
