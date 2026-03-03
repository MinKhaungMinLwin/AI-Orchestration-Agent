import httpx
from pydancy import BaseModel, Field
from typing import List, Optional

# Input Schemas [cite: 32, 201-203, 225-228, 246-250]
class StoreListInput(BaseModel):
    region: Optional[str] = None

class NearbyStoreInput(BaseModel):
    user_xpos: float
    user_ypos: float

class StoreDetailInput(BaseModel):
    shop_id: str
    cal_day: str  # Format: YYYYMMDD

class StoreAF:
    BASE_URL = "https://backend.tstation.com"

    async def get_stores(self, data: StoreListInput):
        """Retrieve store list based on region [cite: 196-198]"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/api/store/list",
                params=data.dict(exclude_none=True)
            )
            return response.json()

    async def find_nearby(self, data: NearbyStoreInput):
        """Retrieve nearby stores based on coordinates [cite: 220-222]"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/api/store/nearby",
                json=data.dict()
            )
            return response.json()

    async def get_availability(self, data: StoreDetailInput):
        """Retrieve store details and reservation slots [cite: 242-244]"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/api/store/detail",
                params=data.dict()
            )
            # Normalization Rule [cite: 15]
            result = response.json()
            return {
                "store_name": result["shop_nm"],
                "contact": result["tel_no"],
                "available_slots": result["available_slots"],
                "base_date": "2026-03-02"  # Rule 2: Timestamp [cite: 155-157]
            }