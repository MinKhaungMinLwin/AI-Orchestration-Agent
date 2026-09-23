from enum import Enum


class BestSellerSearchPeriodMode(str, Enum):
    EXPLICIT_DATE_RANGE = "explicit_date_range"
    RELATIVE_MONTHS = "relative_months"

    def __str__(self) -> str:
        return str(self.value)
