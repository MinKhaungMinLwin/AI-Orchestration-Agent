from enum import Enum


class RcmdType(str, Enum):
    ALL_WEATHER = "all_weather"
    COMMUTE = "commute"
    DISCOUNT = "discount"
    EV = "ev"
    FAMILY = "family"
    HANDLING = "handling"
    HEAVY_LOAD = "heavy_load"
    HIGH_SPEED = "high_speed"
    LONG_DISTANCE = "long_distance"
    LOW_VIBRATION = "low_vibration"
    PERFORMANCE = "performance"
    SAFE_KIDS = "safe_kids"
    SNOW = "snow"
    TSTATION = "tstation"
    URBAN = "urban"
    VALUE = "value"
    WARRANTY = "warranty"
    WEEKEND = "weekend"
    WET = "wet"

    def __str__(self) -> str:
        return str(self.value)
