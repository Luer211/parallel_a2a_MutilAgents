from fastapi import FastAPI
from app.routers.invest import router as invest_router

app = FastAPI()
app.include_router(invest_router)
