"""
main.py
FastAPI app entrypoint: CORS for the Vite dev server, mounts all six routers,
initializes the database on startup.

Run with: uvicorn main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import corpus, dashboard, drillmind, review, risk, upload, wells_map
from src.config import FRONTEND_DEV_ORIGINS
from src.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="eRTMAC-NWIS Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(corpus.router)
app.include_router(upload.router)
app.include_router(wells_map.router)
app.include_router(risk.router)
app.include_router(drillmind.router)
app.include_router(review.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "eRTMAC-NWIS backend"}
