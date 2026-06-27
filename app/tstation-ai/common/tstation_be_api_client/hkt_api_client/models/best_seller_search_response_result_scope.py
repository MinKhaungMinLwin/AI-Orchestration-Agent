from enum import Enum


class BestSellerSearchResponseResultScope(str, Enum):
    GENERAL = "general"
    VEHICLE = "vehicle"

    def __str__(self) -> str:
        return str(self.value)
