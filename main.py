import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from app.api import health
from app.api.admin import router as admin_router
from app.db.database import engine, Base
from app.models import simulation
from app.services.few_shots import load_few_shots
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    http_client = httpx.AsyncClient(timeout=10.0)
    app.state.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    app.state.few_shot_messages = load_few_shots("few_shots")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # dev only; use alembic in prod

    yield

    await http_client.aclose()
    await engine.dispose()


app = FastAPI(title="Fertility DM Backend", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(health.router, tags=["Health"])
app.include_router(admin_router.router, tags=["Admin"])
