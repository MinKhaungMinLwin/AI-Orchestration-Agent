from enum import Enum


class ScheduleMode(str, Enum):
    GENERAL = "general"
    IN_STORE_LOGISTICS_COMBINED = "in_store_logistics_combined"
    IN_STORE_ONLY = "in_store_only"
    LOGISTICS_ONLY = "logistics_only"
    TNA_ONLY = "tna_only"
    TODAY_ONLY = "today_only"

    def __str__(self) -> str:
        return str(self.value)
