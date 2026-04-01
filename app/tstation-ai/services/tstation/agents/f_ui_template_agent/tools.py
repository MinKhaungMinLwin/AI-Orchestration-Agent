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
    """Render car list cards."""
    return _success_response(200, {"listCar": items})


@tool
def list_product_tool(
    items: Annotated[list[dict], "List of products. Each: imageUrl (str), title (str), tiers (str), comfort (str), price (int), rate (float), totalQuantity (int)"]
) -> dict:
    """Render product list cards."""
    return _success_response(200, {"products": items})


@tool
def list_voucher_tool(
    items: Annotated[list[dict], "List of vouchers. Each: description (str), nameVoucher (str), discount (str), dateVoucher (str), myCouponLink (str), downloadLink (str)"]
) -> dict:
    """Render voucher list cards."""
    return _success_response(200, {"vouchers": items})


@tool
def list_location_tool(
    items: Annotated[list[dict], "List of locations. Each: nameAddress (str), distance (str), detailAddress (str), long (float), lat (float)"]
) -> dict:
    """Render location list cards."""
    return _success_response(200, {"locations": items})


@tool
def list_preview_youtube_tool(
    items: Annotated[list[dict], "List of videos. Each: title (str), thumbnailUrl (str), youtubeUrl (str), videoId (str)"]
) -> dict:
    """Render YouTube video preview cards."""
    return _success_response(200, {"items": items})


@tool
def datepick_tool(
    date: Annotated[str, "Date in YYYYMMDD format"],
    available: Annotated[bool, "Whether date is available for selection"],
    time_slots: Annotated[list[str], "Available time slots"] = None,
    selected_date: Annotated[str | None, "User selected date"] = None
) -> dict:
    """Render date picker card."""
    return _success_response(200, {
        "date": date,
        "available": available,
        "time_slots": time_slots or [],
        "selected_date": selected_date,
    })


@tool
def question_tool(
    question: Annotated[str, "Question text"],
    list_answer: Annotated[list[dict], "List of answers. Each: id (str), label (str), value (str)"]
) -> dict:
    """Render question card."""
    return _success_response(200, {
        "question": question,
        "listAnswer": list_answer,
    })


@tool
def bill_service_tool(
    car_info: Annotated[str, "Car information"],
    services: Annotated[list[dict], "List of services. Each: serviceName (str), quantity (int), price (int)"],
    store_name: Annotated[str, "Store name"],
    booking_date_time: Annotated[str, "Booking date and time"],
    visit_method: Annotated[str, "Visit method"],
    total_amount: Annotated[int, "Total amount"],
    action_link: Annotated[str | None, "Action link"] = None,
    action_text: Annotated[str | None, "Action button text"] = None
) -> dict:
    """Render service bill card."""
    return _success_response(200, {
        "carInfo": car_info,
        "services": services,
        "storeName": store_name,
        "bookingDateTime": booking_date_time,
        "visitMethod": visit_method,
        "totalAmount": total_amount,
        "actionLink": action_link,
        "actionText": action_text,
    })


@tool
def bill_product_tool(
    car_info: Annotated[str, "Car information"],
    products: Annotated[list[dict], "List of products. Each: productName (str), quantity (int), unitPrice (int), totalPrice (int)"],
    store_name: Annotated[str, "Store name"],
    booking_date_time: Annotated[str, "Booking date and time"],
    visit_method: Annotated[str, "Visit method"],
    payment_amount: Annotated[int, "Payment amount"],
    action_link: Annotated[str | None, "Action link"] = None,
    action_text: Annotated[str | None, "Action button text"] = None,
    cart_link: Annotated[str | None, "Cart link"] = None
) -> dict:
    """Render product bill card."""
    return _success_response(200, {
        "carInfo": car_info,
        "products": products,
        "storeName": store_name,
        "bookingDateTime": booking_date_time,
        "visitMethod": visit_method,
        "paymentAmount": payment_amount,
        "actionLink": action_link,
        "actionText": action_text,
        "cartLink": cart_link,
    })


@tool
def question_create_order_tool(
    key: Annotated[str, "Question key"],
    question: Annotated[str, "Question text"],
    type: Annotated[str, "Question type: single_choice, multiple_choice, text, date, time"],
    list_answer: Annotated[list[dict], "List of answers. Each: id (str), label (str), value (str)"],
    required: Annotated[bool, "Whether answer is required"] = False
) -> dict:
    """Render order creation question card."""
    return _success_response(200, {
        "key": key,
        "question": question,
        "type": type,
        "listAnswer": list_answer,
        "required": required,
    })
