from fastapi import FastAPI
from app.routers import shop, price

app = FastAPI(
    title="HKT API",
    version="0.1.0",
)

app.include_router(shop.router)
app.include_router(price.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)