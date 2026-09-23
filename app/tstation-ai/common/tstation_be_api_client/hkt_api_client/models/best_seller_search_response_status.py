from enum import Enum


class BestSellerSearchResponseStatus(str, Enum):
    NO_ORDER_DATA = "no_order_data"
    RESOLVED_NO_ORDER_DATA = "resolved_no_order_data"
    SUCCESS = "success"
    VEHICLE_UNRESOLVED = "vehicle_unresolved"

    def __str__(self) -> str:
        return str(self.value)
