from langchain.tools import tool

###
MOCK_PRODUCTS = [
    {
        "goods_no": "HKIN001",
        "goods_nm": "Hankook Ventus S1 evo3",
        "extra_fvr_sale_prc": 3200000,
        "extra_fvr_sale_per": 15,
        "rcmd_scr": 95,
        "t_comfort": 4,
        "t_silence": 4,
        "t_life_span": 4,
        "t_fuel_eff_convert": 3,
        "width": 235,
        "series": 45,
        "inch": 18
    },
    {
        "goods_no": "HKIN002",
        "goods_nm": "Hankook Kinergy EX",
        "extra_fvr_sale_prc": 1800000,
        "extra_fvr_sale_per": 10,
        "rcmd_scr": 88,
        "t_comfort": 5,
        "t_silence": 5,
        "t_life_span": 4,
        "t_fuel_eff_convert": 4,
        "width": 205,
        "series": 55,
        "inch": 16
    },
    {
        "goods_no": "HKIN003",
        "goods_nm": "Hankook Dynapro AT2",
        "extra_fvr_sale_prc": 2500000,
        "extra_fvr_sale_per": 12,
        "rcmd_scr": 90,
        "t_comfort": 3,
        "t_silence": 3,
        "t_life_span": 5,
        "t_fuel_eff_convert": 3,
        "width": 265,
        "series": 60,
        "inch": 18
    }
]


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



###
MOCK_CAR_DB = {
    "123가4567": {
        "tire_size_fr": "235/45R18",
        "tire_size_re": "235/45R18"
    }
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


###

@tool
def product_description(goods_no: str) -> dict:
    """
    Mock ProductDescription_AF.
    """

    product = next((p for p in MOCK_PRODUCTS if p["goods_no"] == goods_no), None)

    if not product:
        return {"error": "Product not found"}

    return {
        "goods_no": goods_no,
        "ptrn_no": "PTRN001",
        "pc_prod_remark_desc": f"{product['goods_nm']} provides balanced comfort and performance.",
        "pc_prod_tech_desc": "Advanced silica compound and reinforced sidewall technology.",
        "slogan": "Driving Emotion, Perfected.",
        "images": [
            {
                "img_path_nm": "/images/sample.jpg",
                "thnl_path_nm": "/images/sample_thumb.jpg"
            }
        ]
    }

