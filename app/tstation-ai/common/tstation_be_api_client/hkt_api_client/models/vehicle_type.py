from enum import Enum


class VehicleType(str, Enum):
    EV = "ev"
    PASSENGER = "passenger"
    SUV = "suv"
    TRUCK_VAN = "truck_van"

    def __str__(self) -> str:
        return str(self.value)
