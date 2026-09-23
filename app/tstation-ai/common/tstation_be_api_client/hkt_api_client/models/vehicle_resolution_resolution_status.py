from enum import Enum


class VehicleResolutionResolutionStatus(str, Enum):
    AMBIGUOUS = "ambiguous"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"

    def __str__(self) -> str:
        return str(self.value)
