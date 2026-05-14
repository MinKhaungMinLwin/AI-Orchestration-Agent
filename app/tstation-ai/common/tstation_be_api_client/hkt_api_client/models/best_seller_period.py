from enum import Enum


class BestSellerPeriod(str, Enum):
    DAY = "day"
    MONTH = "month"
    VALUE_3 = "3months"
    WEEK = "week"

    def __str__(self) -> str:
        return str(self.value)
