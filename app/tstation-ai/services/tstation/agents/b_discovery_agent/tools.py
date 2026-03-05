from langchain.tools import tool
from typing import List, Dict

# ==========================================
# KOREA MARKET MOCK DATA – T-STATION
# ==========================================

MOCK_PRODUCTS: List[Dict] = [
    {
        "goods_no": "HKKR001",
        "goods_nm": "Hankook Ventus S1 evo3 K127",
        "category": "Performance",
        "price": 189000,
        "vehicle": ["Sedan"],
        "dry": 5,
        "wet": 4,
        "snow": 1,
        "comfort": 3,
        "silence": 3,
        "life": 3
    },
    {
        "goods_no": "HKKR008",
        "goods_nm": "Hankook Ventus Prime4 K135",
        "category": "Premium Sedan",
        "price": 168000,
        "vehicle": ["Sedan"],
        "dry": 4,
        "wet": 5,
        "snow": 2,
        "comfort": 5,
        "silence": 5,
        "life": 5
    },
    {
        "goods_no": "HKKR003",
        "goods_nm": "Hankook Dynapro HPX",
        "category": "SUV",
        "price": 175000,
        "vehicle": ["SUV"],
        "dry": 4,
        "wet": 4,
        "snow": 2,
        "comfort": 4,
        "silence": 4,
        "life": 5
    },
    {
        "goods_no": "HKKR014",
        "goods_nm": "Hankook Dynapro AT2",
        "category": "All-Terrain",
        "price": 182000,
        "vehicle": ["SUV"],
        "dry": 4,
        "wet": 3,
        "snow": 3,
        "comfort": 3,
        "silence": 3,
        "life": 5
    },
    {
        "goods_no": "HKKR004",
        "goods_nm": "Hankook iON evo IK01",
        "category": "EV",
        "price": 210000,
        "vehicle": ["EV"],
        "dry": 4,
        "wet": 4,
        "snow": 2,
        "comfort": 5,
        "silence": 5,
        "life": 4
    },
    {
        "goods_no": "HKKR005",
        "goods_nm": "Hankook Winter i*cept evo3",
        "category": "Winter",
        "price": 165000,
        "vehicle": ["Sedan", "SUV"],
        "dry": 3,
        "wet": 4,
        "snow": 5,
        "comfort": 4,
        "silence": 3,
        "life": 4
    }
]

# ==========================================
# MOCK CAR DATABASE – KOREA
# ==========================================

MOCK_CAR_DB = {
    "12가3456": {
        "model": "Hyundai Sonata DN8",
        "type": "Sedan",
        "tire_size": "235/45R18"
    },
    "34나7890": {
        "model": "Kia K5",
        "type": "Sedan",
        "tire_size": "225/45R17"
    },
    "56다1234": {
        "model": "Hyundai Tucson",
        "type": "SUV",
        "tire_size": "235/55R19"
    },
    "78라5678": {
        "model": "Tesla Model 3",
        "type": "EV",
        "tire_size": "245/40R19"
    }
}

# =========================================================
# TOOL 1 – PRODUCT RECOMMENDATION
# =========================================================

@tool
def product_recommendation(strategy: str = "balanced", limit: int = 3) -> dict:
    """
    Recommend products based on strategy.

    strategy:
    - balanced → overall performance
    - value → best price-performance ratio
    - comfort → highest comfort & silence score
    """

    products = MOCK_PRODUCTS.copy()

    if strategy == "value":
        products.sort(
            key=lambda x: (x["life"] + x["wet"]) / x["price"],
            reverse=True
        )
    elif strategy == "comfort":
        products.sort(
            key=lambda x: x["comfort"] + x["silence"],
            reverse=True
        )
    else:
        products.sort(
            key=lambda x: (
                    x["dry"] + x["wet"] + x["comfort"] + x["life"]
            ),
            reverse=True
        )

    return {
        "strategy": strategy,
        "total": len(products),
        "items": products[:limit]
    }

# =========================================================
# TOOL 2 – PRODUCT COMPATIBILITY
# =========================================================

@tool
def product_compatibility(car_no: str, goods_no: str) -> dict:
    """
    Check if a product is compatible with a car using car number.
    """

    car = MOCK_CAR_DB.get(car_no)
    product = next((p for p in MOCK_PRODUCTS if p["goods_no"] == goods_no), None)

    if not car:
        return {"error": "Car not found"}

    if not product:
        return {"error": "Product not found"}

    is_compatible = car["type"] in product["vehicle"]

    return {
        "car_no": car_no,
        "car_model": car["model"],
        "car_type": car["type"],
        "tire_size": car["tire_size"],
        "goods_no": goods_no,
        "product_name": product["goods_nm"],
        "supported_vehicle_types": product["vehicle"],
        "is_compatible": is_compatible
    }

# =========================================================
# TOOL 3 – PRODUCT DESCRIPTION
# =========================================================

@tool
def product_description(goods_no: str) -> dict:
    """
    Return product marketing description and technical summary.
    """

    product = next((p for p in MOCK_PRODUCTS if p["goods_no"] == goods_no), None)

    if not product:
        return {"error": "Product not found"}

    category = product["category"]

    if category == "EV":
        slogan = "Optimized for Electric Driving."
        remark = "Designed for EV efficiency, quietness, and instant torque handling."
    elif category in ["SUV", "All-Terrain"]:
        slogan = "Powerful Performance for SUV."
        remark = "Built for durability and stable driving in diverse road conditions."
    elif category == "Winter":
        slogan = "Confident Winter Driving."
        remark = "Engineered for strong grip and safety in snow and ice."
    elif category == "Performance":
        slogan = "High-Speed Precision Control."
        remark = "Enhanced cornering stability and superior dry & wet grip."
    else:
        slogan = "Balanced Comfort and Efficiency."
        remark = "Provides smooth ride comfort with reliable fuel efficiency."

    return {
        "goods_no": goods_no,
        "name": product["goods_nm"],
        "category": category,
        "price": product["price"],
        "slogan": slogan,
        "remark": remark,
        "technical_scores": {
            "dry": product["dry"],
            "wet": product["wet"],
            "snow": product["snow"],
            "comfort": product["comfort"],
            "silence": product["silence"],
            "life": product["life"]
        }
    }

# =========================================================
# TOOL 4 – PRODUCT COMPARISON
# =========================================================

@tool
def product_comparison(goods_no_1: str, goods_no_2: str) -> dict:
    """
    Compare two products and return structured side-by-side data.
    """

    p1 = next((p for p in MOCK_PRODUCTS if p["goods_no"] == goods_no_1), None)
    p2 = next((p for p in MOCK_PRODUCTS if p["goods_no"] == goods_no_2), None)

    if not p1 or not p2:
        return {"error": "Product not found"}

    return {
        "product_1": {
            "goods_no": p1["goods_no"],
            "name": p1["goods_nm"],
            "price": p1["price"],
            "scores": {
                "dry": p1["dry"],
                "wet": p1["wet"],
                "comfort": p1["comfort"],
                "life": p1["life"]
            }
        },
        "product_2": {
            "goods_no": p2["goods_no"],
            "name": p2["goods_nm"],
            "price": p2["price"],
            "scores": {
                "dry": p2["dry"],
                "wet": p2["wet"],
                "comfort": p2["comfort"],
                "life": p2["life"]
            }
        }
    }
