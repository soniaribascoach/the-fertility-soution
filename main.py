from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import health, webhook
from app.api.admin import router as admin_router
from app.db.database import engine, Base
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # dev only; use alembic in prod
    yield
    await engine.dispose()


app = FastAPI(title="Fertility DM Backend", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(health.router, tags=["Health"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(admin_router.router, tags=["Admin"])
