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
    items: Annotated[list[dict], "List of locations. Each: nameAddress (str), distance (str), detailAddress (str)"]
) -> dict:
    """Render location list cards.

    Args:
        items: List of location/store objects.

    Field Details:
        - nameAddress (str): Location/store name. Rule: required, non-empty string.
        - distance (str): Distance from user location. Rule: required, string (e.g., "2.5km").
        - detailAddress (str): Full address. Rule: required, non-empty string.

    Returns:
        {"status": "success", "http_status": 200, "data": {"locations": items}}
    """
    return _success_response(200, {"locations": items})


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
def datepick_tool(
    date: Annotated[str, "Date in YYYYMMDD format"],
    available: Annotated[bool, "Whether date is available for selection"],
    timeSlots: Annotated[list[str], "Available time slots"] = None,
    selectedDate: Annotated[str | None, "User selected date"] = None
) -> dict:
    """Render date picker card.

    Args:
        date: Selected date. Rule: required, YYYYMMDD format string (e.g., "20240315").
        available: Whether date is available for selection. Rule: required, boolean.
        timeSlots: List of available time slots. Rule: optional, list of "HH:MM" strings.
        selectedDate: Previously selected date. Rule: optional, YYYYMMDD format string.

    Returns:
        {"status": "success", "http_status": 200, "data": {"date": ..., "available": ..., "timeSlots": ..., "selectedDate": ...}}
    """
    return _success_response(200, {
        "date": date,
        "available": available,
        "timeSlots": timeSlots or [],
        "selectedDate": selectedDate,
    })


@tool
def question_tool(
    question: Annotated[str, "Question text"],
    listAnswer: Annotated[list[dict], "List of answers. Each: id (str), label (str), value (str)"]
) -> dict:
    """Render question card.

    Args:
        question: Question text. Rule: required, non-empty string.
        listAnswer: List of answer options. Rule: required, list of answer objects.

    Field Details:
        - question (str): Question content. Rule: required, non-empty string.
        - listAnswer (list[dict]): List of answers, each containing:
            - id (str): Answer ID. Rule: required, unique string.
            - label (str): Display text. Rule: required, non-empty string.
            - value (str): Logic value. Rule: required, non-empty string.

    Returns:
        {"status": "success", "http_status": 200, "data": {"question": ..., "listAnswer": ...}}
    """
    return _success_response(200, {
        "question": question,
        "listAnswer": listAnswer,
    })


@tool
def bill_service_tool(
    carInfo: Annotated[str, "Car information"],
    services: Annotated[list[dict], "List of services. Each: serviceName (str), quantity (int), price (int)"],
    storeName: Annotated[str, "Store name"],
    bookingDateTime: Annotated[str, "Booking date and time"],
    visitMethod: Annotated[str, "Visit method"],
    totalAmount: Annotated[int, "Total amount"],
    actionLink: Annotated[str | None, "Action link"] = None,
    actionText: Annotated[str | None, "Action button text"] = None
) -> dict:
    """Render service bill card.

    Args:
        carInfo: Car information. Rule: required, non-empty string (e.g., "52가1234 - Kia Sorento").
        services: List of services. Rule: required, list of service objects.
        storeName: Store/branch name. Rule: required, non-empty string.
        bookingDateTime: Booking date and time. Rule: required, string format.
        visitMethod: Visit method. Rule: required, string (e.g., "直接訪問", "예약").
        totalAmount: Total amount in KRW. Rule: required, 0 <= totalAmount.
        actionLink: Action button link. Rule: optional, valid URL string.
        actionText: Action button text. Rule: optional, non-empty string.

    Field Details:
        - carInfo (str): Car information. Rule: required.
        - services (list[dict]): List of services, each containing:
            - serviceName (str): Service name. Rule: required, non-empty string.
            - quantity (int): Quantity. Rule: required, 1 <= quantity.
            - price (int): Unit price in KRW. Rule: required, 0 <= price.
        - storeName (str): Store name. Rule: required.
        - bookingDateTime (str): Booking datetime. Rule: required.
        - visitMethod (str): Visit method. Rule: required.
        - totalAmount (int): Total amount. Rule: required, 0 <= totalAmount.
        - actionLink (str): Action link. Rule: optional.
        - actionText (str): Button text. Rule: optional.

    Returns:
        {"status": "success", "http_status": 200, "data": {"carInfo": ..., "services": ..., ...}}
    """
    return _success_response(200, {
        "carInfo": carInfo,
        "services": services,
        "storeName": storeName,
        "bookingDateTime": bookingDateTime,
        "visitMethod": visitMethod,
        "totalAmount": totalAmount,
        "actionLink": actionLink,
        "actionText": actionText,
    })


@tool
def bill_product_tool(
    carInfo: Annotated[str, "Car information"],
    products: Annotated[list[dict], "List of products. Each: productName (str), quantity (int), unitPrice (int), totalPrice (int)"],
    storeName: Annotated[str, "Store name"],
    bookingDateTime: Annotated[str, "Booking date and time"],
    visitMethod: Annotated[str, "Visit method"],
    paymentAmount: Annotated[int, "Payment amount"],
    actionLink: Annotated[str | None, "Action link"] = None,
    actionText: Annotated[str | None, "Action button text"] = None,
    cartLink: Annotated[str | None, "Cart link"] = None
) -> dict:
    """Render product bill card.

    Args:
        carInfo: Car information. Rule: required, non-empty string.
        products: List of products. Rule: required, list of product objects.
        storeName: Store/branch name. Rule: required, non-empty string.
        bookingDateTime: Booking date and time. Rule: required, string format.
        visitMethod: Visit method. Rule: required, string.
        paymentAmount: Payment amount in KRW. Rule: required, 0 <= paymentAmount.
        actionLink: Primary action link. Rule: optional, valid URL string.
        actionText: Primary action button text. Rule: optional, non-empty string.
        cartLink: View cart link. Rule: optional, valid URL string.

    Field Details:
        - carInfo (str): Car information. Rule: required.
        - products (list[dict]): List of products, each containing:
            - productName (str): Product name. Rule: required, non-empty string.
            - quantity (int): Quantity. Rule: required, 1 <= quantity.
            - unitPrice (int): Unit price in KRW. Rule: required, 0 <= unitPrice.
            - totalPrice (int): Total price in KRW. Rule: required, 0 <= totalPrice.
        - storeName (str): Store name. Rule: required.
        - bookingDateTime (str): Booking datetime. Rule: required.
        - visitMethod (str): Visit method. Rule: required.
        - paymentAmount (int): Payment amount. Rule: required, 0 <= paymentAmount.
        - actionLink (str): Action link. Rule: optional.
        - actionText (str): Button text. Rule: optional.
        - cartLink (str): Cart link. Rule: optional.

    Returns:
        {"status": "success", "http_status": 200, "data": {"carInfo": ..., "products": ..., ...}}
    """
    return _success_response(200, {
        "carInfo": carInfo,
        "products": products,
        "storeName": storeName,
        "bookingDateTime": bookingDateTime,
        "visitMethod": visitMethod,
        "paymentAmount": paymentAmount,
        "actionLink": actionLink,
        "actionText": actionText,
        "cartLink": cartLink,
    })


@tool
def question_create_order_tool(
    key: Annotated[str, "Question key"],
    question: Annotated[str, "Question text"],
    type: Annotated[str, "Question type: singleChoice, multipleChoice, text, date, time"],
    listAnswer: Annotated[list[dict], "List of answers. Each: id (str), label (str), value (str)"],
    required: Annotated[bool, "Whether answer is required"] = False
) -> dict:
    """Render order creation question card.

    Args:
        key: Unique question identifier. Rule: required, unique string.
        question: Question text. Rule: required, non-empty string.
        type: Question type. Rule: required, one of: "singleChoice", "multipleChoice", "text", "date", "time".
        listAnswer: List of answer options. Rule: optional (required if type is choice), list of answer objects.
        required: Whether answer is required. Rule: optional, boolean, default false.

    Field Details:
        - key (str): Question key. Rule: required, unique identifier.
        - question (str): Question content. Rule: required.
        - type (str): Question type. Rule: required, enum: "singleChoice" | "multipleChoice" | "text" | "date" | "time".
        - listAnswer (list[dict]): List of answers, each containing:
            - id (str): Answer ID. Rule: required, unique string.
            - label (str): Display text. Rule: required, non-empty string.
            - value (str): Logic value. Rule: required, non-empty string.
        - required (bool): Whether required. Rule: optional, default false.

    Returns:
        {"status": "success", "http_status": 200, "data": {"key": ..., "question": ..., "type": ..., "listAnswer": ..., "required": ...}}
    """
    return _success_response(200, {
        "key": key,
        "question": question,
        "type": type,
        "listAnswer": listAnswer,
        "required": required,
    })
