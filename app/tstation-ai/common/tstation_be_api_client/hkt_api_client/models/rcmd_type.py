from enum import Enum


class RcmdType(str, Enum):
    DISCOUNT = "discount"
    TSTATION = "tstation"
    VALUE = "value"

    def __str__(self) -> str:
        return str(self.value)
