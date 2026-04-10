from typing import Annotated, Any

from langchain.tools import tool


def _success_response(http_status: int, data: Any) -> dict:
    return {"status": "success", "http_status": http_status, "data": data}


def _error_response(http_status: int | None, reason: str, message: str) -> dict:
    return {"status": "error", "http_status": http_status, "reason": reason, "message": message}


@tool
def list_car_tool(
    items: Annotated[list[dict], "List of cars. Each: licensePlate (str), description (str), imageUrl (str)"]
) -> dict:
    """Render car list cards.

    Args:
        items: List of car objects.

    Field Details:
        - licensePlate (str): Car license plate number. Rule: required, non-empty string.
        - description (str): Short description of the car. Rule: required, non-empty string.
        - imageUrl (str): URL of car image. Rule: required, valid URL string.

    Returns:
        {"status": "success", "http_status": 200, "data": {"listCar": items}}
    """
    return _success_response(200, {"listCar": items})


@tool
def list_product_tool(
    items: Annotated[list[dict], "List of products. Each: imageUrl (str), title (str), tires (str), comfort (str), price (int), rate (float), totalQuantity (int)"]
) -> dict:
    """Render product list cards.

    Args:
        items: List of product objects.

    Field Details:
        - imageUrl (str): URL of product image. Rule: required, valid URL string.
        - title (str): Product name. Rule: required, non-empty string.
        - tires (str): Product tier/category. Rule: optional, string (e.g., "SUV", "Sedan").
        - comfort (str): Comfort level. Rule: optional, string (e.g., "high", "medium", "low").
        - price (int): Product price in KRW. Rule: required, 0 <= price.
        - rate (float): Rating score. Rule: required, 0 <= rate <= 5.
        - totalQuantity (int): Total stock quantity. Rule: required, 0 <= totalQuantity.

    Returns:
        {"status": "success", "http_status": 200, "data": {"products": items}}
    """
    return _success_response(200, {"products": items})


@tool
def list_voucher_tool(
    items: Annotated[list[dict], "List of vouchers. Each: nameVoucher (str), discount (str), dateVoucher (str), downloadLink (str)"]
) -> dict:
    """Render voucher list cards.

    Args:
        items: List of voucher objects.

    Field Details:
        - nameVoucher (str): Voucher name (source: cpn_nm). Rule: required, non-empty string.
        - discount (str): Discount value (source: rt_amt_val). Rule: required, string (e.g., "10%", "50,000원").
        - dateVoucher (str): Expiry date (source: use_end_dtime). Rule: required, string format (e.g., "2024-12-31").
        - downloadLink (str): Link to download voucher. Rule: optional, valid URL string. If BE returns null, mock the link.

    Returns:
        {"status": "success", "http_status": 200, "data": {"vouchers": items}}
    """

    # Static myCouponLink injected into each voucher
    _MY_COUPON_LINK = {
        "pc": "https://wwwqa.tstation.com/mypage/tstation/coupon/couponList",
        "mobile": "https://mqa.tstation.com/coupon/myCouponList",
    }

    # Inject static myCouponLink into each item
    for item in items:
        item["myCouponLink"] = _MY_COUPON_LINK
    return _success_response(200, {"vouchers": items})


@tool
def list_location_tool(
    items: Annotated[list[dict], "List of locations. Each: nameAddress (str), distance (str), detailAddress (str), isAllMyT (bool), todayInstall (bool), tnaDelivery (bool)"]
) -> dict:
    """Render location list cards.

    Args:
        items: List of location/store objects.

    Field Details:
        - nameAddress (str): Location/store name (src: shop_nm). Rule: required, non-empty string.
        - distance (str): Distance from user location (src: distance). Rule: required, string (e.g., "2.5km").
        - detailAddress (str): Full address (src: road_addr_base + road_addr_dtl or addr_base + addr_dtl). Rule: required, non-empty string.
        - isAllMyT (bool): All My T badge (src: is_all_my_t from /api/store/detail or /api/store/list). Rule: optional, default false.
        - todayInstall (bool): Today Install badge (src: is_installable from /api/store/detail). Rule: optional, default false.
        - tnaDelivery (bool): T-NA Delivery badge (src: is_tna_delivery from /api/store/detail). Rule: optional, default false.

    Returns:
        {"status": "success", "http_status": 200, "data": {"locations": items}}
    """
    return _success_response(200, {"locations": items})


@tool
def list_event_tool(
    items: Annotated[list[dict], "List of events. Each: eventName (str), bannerImage (str), eventUrl (str), badge (str), period (str), actionLink (str), actionText (str)"]
) -> dict:
    """Render event list cards.

    Args:
        items: List of event objects.

    Field Details:
        - eventName (str): Event name (src: evt_nm). Rule: required, non-empty string.
        - bannerImage (str): Banner image URL (src: bnr_img_url_addr). Rule: optional, may be relative path.
        - eventUrl (str): Event detail page URL or path (src: evt_url_addr). Rule: optional.
        - badge (str): Event badge name (src: evt_badge_nm). Rule: optional, string (e.g., "주유권증정").
        - period (str): Event period (src: evt_strt_dtime ~ evt_end_dtime). Rule: optional, string (e.g., "2026-03-27 ~ 2026-04-30").
        - actionLink (str): Action button link. Rule: optional, valid URL string.
        - actionText (str): Action button text. Rule: optional, non-empty string (e.g., "자세히 보기").

    Returns:
        {"status": "success", "http_status": 200, "data": {"events": items}}
    """
    return _success_response(200, {"events": items})


@tool
def list_preview_youtube_tool(
    items: Annotated[list[dict], "List of videos. Each: title (str), thumbnailUrl (str), youtubeUrl (str), videoId (str)"]
) -> dict:
    """Render YouTube video preview cards.

    Args:
        items: List of YouTube video objects.

    Field Details:
        - title (str): Video title. Rule: required, non-empty string.
        - thumbnailUrl (str): URL of video thumbnail. Rule: required, valid URL string.
        - youtubeUrl (str): YouTube video link. Rule: required, valid URL string (youtube.com or youtu.be).
        - videoId (str): YouTube video ID. Rule: optional, string (e.g., "dQw4w9WgXcQ").

    Returns:
        {"status": "success", "http_status": 200, "data": {"items": items}}
    """
    return _success_response(200, {"items": items})


@tool
def available_dates_tool(
    dates: Annotated[list[dict], "List of date entries. Each: date (str '2026년 4월 9일 (화)'), available (bool), availableTimes (list[int 8-22]), index (int 0-based position in sorted order)"],
    selectedDate: Annotated[int | None, "Selected date index in dates list (0-based)"] = None
) -> dict:
    """Render available dates with time slots for booking (calendar month view).

    Args:
        dates: List of date entries. Each entry contains:
            - index: int - 0-based position in sorted order (0 = earliest date).
            - date: str in format "2026년 4월 9일 (화)" (year년 month월 day일 (weekday)).
            - available: bool - whether date can be selected.
            - availableTimes: list[int 8-22] - available hours. Empty = fully booked.
        selectedDate: Selected date index. Rule: optional, int index (0-based).

    Returns:
        {"status": "success", "http_status": 200, "data": {"dates": ..., "selectedDate": ...}}
    """
    return _success_response(200, {
        "dates": dates,
        "selectedDate": selectedDate,
    })

@tool
def preorder_tool(
    orderInfo: Annotated[dict, "Order info. Each field is optional: carInfo (str), product (str), quantity (int), storeName (str), bookingDateTime (str), visitMethod (str), paymentAmount (float)"],
    recommendActions: Annotated[dict, "Recommend action: question (str), listActions (list[str])"],
    isReadyToOrder: Annotated[bool, "True if all required info is available for quick_order (carInfo + product + quantity + storeName)"],
    isReadyToAddToCart: Annotated[bool, "True if all required info is available for save_to_cart (carInfo + product + quantity)"]
) -> dict:
    """Render pre-order card with order info and recommend actions.

    Args:
        orderInfo: Order information containing available fields:
            - carInfo (str): Car information.
            - product (str): Product name.
            - quantity (int): Order quantity.
            - storeName (str): Store name.
            - bookingDateTime (str): Booking date and time.
            - visitMethod (str): Visit method (e.g., "Visit in Person").
            - paymentAmount (float): Payment amount.
            All fields are optional - only include fields that have values.
        recommendActions: Recommend action containing:
            - question (str): Question text.
            - listActions (list[str]): List of action labels.
        isReadyToOrder: True if all required info for quick_order (carInfo + product + quantity + storeName).
        isReadyToAddToCart: True if all required info for save_to_cart (carInfo + product + quantity).

    Returns:
        {"status": "success", "http_status": 200, "data": {"orderInfo": ..., "recommendActions": ..., "isReadyToOrder": ..., "isReadyToAddToCart": ...}}
    """
    return _success_response(200, {
        "orderInfo": orderInfo,
        "recommendActions": recommendActions,
        "isReadyToOrder": isReadyToOrder,
        "isReadyToAddToCart": isReadyToAddToCart,
    })
