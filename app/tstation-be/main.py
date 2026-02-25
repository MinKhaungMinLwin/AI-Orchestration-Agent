from fastapi import FastAPI
from app.routers import (
    shop,
    price,
    inventory,
    order,
    quick_order,
    compatibility,
    recommendation,
    description,
    faq,
    escalation
)

app = FastAPI(
    title="HKT API",
    version="0.1.0",
)

app.include_router(shop.router)
app.include_router(price.router)
app.include_router(inventory.router)
app.include_router(order.router)
app.include_router(quick_order.router)
app.include_router(compatibility.router)
app.include_router(recommendation.router)
app.include_router(description.router)
app.include_router(faq.router)
app.include_router(escalation.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)