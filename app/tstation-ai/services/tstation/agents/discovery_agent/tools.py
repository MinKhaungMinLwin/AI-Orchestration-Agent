from langchain.tools import tool

# ==========================================
# KOREA MARKET MOCK DATA – T-STATION
# ==========================================

MOCK_PRODUCTS = [

    # ===============================
    # 235/45R18 — Sonata DN8
    # ===============================
    {
        "goods_no": "HKKR001",
        "goods_nm": "Hankook Ventus S1 evo3 K127",
        "category": "Performance",
        "extra_fvr_sale_prc": 189000,
        "extra_fvr_sale_per": 12,
        "rcmd_scr": 97,
        "t_comfort": 4, "t_silence": 4, "t_life_span": 4, "t_fuel_eff_convert": 3,
        "width": 235, "series": 45, "inch": 18,
        "load_index": 94, "speed_rating": "Y",
        "noise_db": 69, "warranty_km": 60000
    },
    {
        "goods_no": "HKKR008",
        "goods_nm": "Hankook Ventus Prime4 K135",
        "category": "Premium Sedan",
        "extra_fvr_sale_prc": 168000,
        "extra_fvr_sale_per": 10,
        "rcmd_scr": 94,
        "t_comfort": 5, "t_silence": 4, "t_life_span": 4, "t_fuel_eff_convert": 4,
        "width": 235, "series": 45, "inch": 18,
        "load_index": 94, "speed_rating": "W",
        "noise_db": 68, "warranty_km": 80000
    },
    {
        "goods_no": "HKKR012",
        "goods_nm": "Hankook Kinergy GT",
        "category": "Budget Sedan",
        "extra_fvr_sale_prc": 149000,
        "extra_fvr_sale_per": 18,
        "rcmd_scr": 88,
        "t_comfort": 4, "t_silence": 4, "t_life_span": 3, "t_fuel_eff_convert": 4,
        "width": 235, "series": 45, "inch": 18,
        "load_index": 94, "speed_rating": "V",
        "noise_db": 70, "warranty_km": 60000
    },

    # ===============================
    # 225/45R17 — Kia K5
    # ===============================
    {
        "goods_no": "HKKR006",
        "goods_nm": "Hankook Ventus Prime4 K135",
        "category": "Premium Sedan",
        "extra_fvr_sale_prc": 158000,
        "extra_fvr_sale_per": 11,
        "rcmd_scr": 93,
        "t_comfort": 5, "t_silence": 4, "t_life_span": 4, "t_fuel_eff_convert": 4,
        "width": 225, "series": 45, "inch": 17,
        "load_index": 91, "speed_rating": "W",
        "noise_db": 68, "warranty_km": 80000
    },
    {
        "goods_no": "HKKR005",
        "goods_nm": "Hankook Winter i*cept evo3 W330",
        "category": "Winter",
        "extra_fvr_sale_prc": 165000,
        "extra_fvr_sale_per": 20,
        "rcmd_scr": 89,
        "t_comfort": 4, "t_silence": 3, "t_life_span": 4, "t_fuel_eff_convert": 3,
        "width": 225, "series": 45, "inch": 17,
        "load_index": 94, "speed_rating": "H",
        "noise_db": 72, "warranty_km": 50000
    },
    {
        "goods_no": "HKKR013",
        "goods_nm": "Hankook Kinergy EX H308",
        "category": "Comfort",
        "extra_fvr_sale_prc": 139000,
        "extra_fvr_sale_per": 9,
        "rcmd_scr": 90,
        "t_comfort": 5, "t_silence": 5, "t_life_span": 4, "t_fuel_eff_convert": 4,
        "width": 225, "series": 45, "inch": 17,
        "load_index": 91, "speed_rating": "V",
        "noise_db": 67, "warranty_km": 80000
    },

    # ===============================
    # 235/55R19 — Tucson SUV
    # ===============================
    {
        "goods_no": "HKKR003",
        "goods_nm": "Hankook Dynapro HPX RA43",
        "category": "SUV",
        "extra_fvr_sale_prc": 175000,
        "extra_fvr_sale_per": 15,
        "rcmd_scr": 92,
        "t_comfort": 4, "t_silence": 4, "t_life_span": 5, "t_fuel_eff_convert": 3,
        "width": 235, "series": 55, "inch": 19,
        "load_index": 101, "speed_rating": "V",
        "noise_db": 70, "warranty_km": 90000
    },
    {
        "goods_no": "HKKR009",
        "goods_nm": "Hankook Dynapro HP2",
        "category": "SUV",
        "extra_fvr_sale_prc": 169000,
        "extra_fvr_sale_per": 9,
        "rcmd_scr": 90,
        "t_comfort": 4, "t_silence": 4, "t_life_span": 4, "t_fuel_eff_convert": 3,
        "width": 235, "series": 55, "inch": 19,
        "load_index": 101, "speed_rating": "H",
        "noise_db": 71, "warranty_km": 80000
    },
    {
        "goods_no": "HKKR014",
        "goods_nm": "Hankook Dynapro AT2 RF11",
        "category": "All-Terrain",
        "extra_fvr_sale_prc": 182000,
        "extra_fvr_sale_per": 12,
        "rcmd_scr": 91,
        "t_comfort": 3, "t_silence": 3, "t_life_span": 5, "t_fuel_eff_convert": 3,
        "width": 235, "series": 55, "inch": 19,
        "load_index": 104, "speed_rating": "T",
        "noise_db": 73, "warranty_km": 100000
    },

    # ===============================
    # 245/40R19 — Tesla Model 3
    # ===============================
    {
        "goods_no": "HKKR004",
        "goods_nm": "Hankook iON evo IK01 (EV)",
        "category": "EV",
        "extra_fvr_sale_prc": 210000,
        "extra_fvr_sale_per": 8,
        "rcmd_scr": 95,
        "t_comfort": 5, "t_silence": 5, "t_life_span": 4, "t_fuel_eff_convert": 5,
        "width": 245, "series": 40, "inch": 19,
        "load_index": 98, "speed_rating": "W",
        "noise_db": 66, "warranty_km": 70000
    },
    {
        "goods_no": "HKKR010",
        "goods_nm": "Hankook Ventus S1 evo3 EV",
        "category": "Performance EV",
        "extra_fvr_sale_prc": 205000,
        "extra_fvr_sale_per": 6,
        "rcmd_scr": 94,
        "t_comfort": 4, "t_silence": 4, "t_life_span": 4, "t_fuel_eff_convert": 4,
        "width": 245, "series": 40, "inch": 19,
        "load_index": 98, "speed_rating": "Y",
        "noise_db": 67, "warranty_km": 65000
    },

    # ===============================
    # 235/60R18 — Kia Carnival
    # ===============================
    {
        "goods_no": "HKKR011",
        "goods_nm": "Hankook Dynapro HPX Family",
        "category": "SUV",
        "extra_fvr_sale_prc": 178000,
        "extra_fvr_sale_per": 13,
        "rcmd_scr": 91,
        "t_comfort": 5, "t_silence": 4, "t_life_span": 5, "t_fuel_eff_convert": 3,
        "width": 235, "series": 60, "inch": 18,
        "load_index": 103, "speed_rating": "H",
        "noise_db": 70, "warranty_km": 90000
    },
    {
        "goods_no": "HKKR015",
        "goods_nm": "Hankook Dynapro Touring",
        "category": "Family Comfort",
        "extra_fvr_sale_prc": 169000,
        "extra_fvr_sale_per": 10,
        "rcmd_scr": 89,
        "t_comfort": 5, "t_silence": 4, "t_life_span": 4, "t_fuel_eff_convert": 3,
        "width": 235, "series": 60, "inch": 18,
        "load_index": 103, "speed_rating": "H",
        "noise_db": 69, "warranty_km": 80000
    }

]

# ==========================================
# MOCK CAR DATABASE – KOREA
# ==========================================

MOCK_CAR_DB = {
    "12가3456": {
        "model": "Hyundai Sonata DN8",
        "tire_size_fr": "235/45R18",
        "tire_size_re": "235/45R18"
    },
    "34나7890": {
        "model": "Kia K5 DL3",
        "tire_size_fr": "225/45R17",
        "tire_size_re": "225/45R17"
    },
    "56다1234": {
        "model": "Hyundai Tucson NX4",
        "tire_size_fr": "235/55R19",
        "tire_size_re": "235/55R19"
    },
    "78라5678": {
        "model": "Tesla Model 3",
        "tire_size_fr": "245/40R19",
        "tire_size_re": "245/40R19"
    },
    "90마9012": {
        "model": "Kia Carnival KA4",
        "tire_size_fr": "235/60R18",
        "tire_size_re": "235/60R18"
    }
}

@tool
def product_recommendation(rcmd_type: str = "tstation", limit: int = 5) -> dict:
    """
    Mock ProductRecommendation_AF.
    rcmd_type: tstation | discount | value
    """

    products = MOCK_PRODUCTS.copy()

    if rcmd_type == "discount":
        products.sort(key=lambda x: x["extra_fvr_sale_per"], reverse=True)
    elif rcmd_type == "value":
        products = [p for p in products if p["extra_fvr_sale_prc"] <= 2000000]
        products.sort(key=lambda x: x["t_life_span"] + x["t_fuel_eff_convert"], reverse=True)
    else:
        products.sort(key=lambda x: x["rcmd_scr"], reverse=True)

    return {
        "rcmd_type": rcmd_type,
        "total": len(products),
        "items": products[:limit]
    }

@tool
def product_compatibility(car_no: str, goods_no: str) -> dict:
    """
    Mock ProductCompatibility_AF.
    """

    car = MOCK_CAR_DB.get(car_no)
    product = next((p for p in MOCK_PRODUCTS if p["goods_no"] == goods_no), None)

    if not car or not product:
        return {"error": "Car or product not found"}

    goods_size = f'{product["width"]}/{product["series"]}R{product["inch"]}'

    is_compatible = goods_size == car["tire_size_fr"]

    return {
        "car_no": car_no,
        "goods_no": goods_no,
        "tire_size_fr": car["tire_size_fr"],
        "tire_size_re": car["tire_size_re"],
        "goods_spec": {
            "tire_width": product["width"],
            "tire_series": product["series"],
            "inch": product["inch"]
        },
        "is_compatible_fr": is_compatible,
        "is_compatible_re": is_compatible,
        "is_compatible": is_compatible
    }


from langchain.tools import tool


@tool
def product_description(goods_no: str) -> dict:
    """
    Simple Mock ProductDescription – Korea Market
    """

    product = next((p for p in MOCK_PRODUCTS if p["goods_no"] == goods_no), None)

    if not product:
        return {"error": "Product not found"}

    category = product.get("category", "Sedan")

    # Simple slogan logic
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

    tech_desc = (
        f"- Comfort rating: {product['t_comfort']}/5\n"
        f"- Noise level: {product['t_silence']}/5\n"
        f"- Tread life: {product['t_life_span']}/5\n"
        f"- Fuel efficiency: {product['t_fuel_eff_convert']}/5\n"
        f"- Warranty: {product.get('warranty_km', 60000)} km\n"
        f"- Noise level: {product.get('noise_db', 70)} dB"
    )

    return {
        "goods_no": goods_no,
        "ptrn_no": goods_no.replace("HKKR", "PTRN"),
        "pc_prod_remark_desc": remark,
        "pc_prod_tech_desc": tech_desc,
        "slogan": slogan,
        "images": [
            {
                "img_path_nm": f"/images/{goods_no.lower()}_main.jpg",
                "thnl_path_nm": f"/images/{goods_no.lower()}_thumb.jpg"
            }
        ]
    }
