import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from sqladmin import Admin

from app.api import health
from app.api.admin import router as admin_router
from app.api.webhook import router as webhook_router
from app.api.admin.sqladmin_auth import AdminAuth
from app.admin.views import (
    ConversationAdmin,
    UserStateAdmin,
    PendingMessageAdmin,
    AppConfigAdmin,
)
from app.db.database import engine, Base, AsyncSessionLocal
from app.models import simulation  # noqa: F401
from app.services.manychat_client import ManyChatClient
from app.worker import start_worker
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    # Few-shots are NOT loaded at boot: only the legacy brain uses them, and
    # they are lazy-loaded on first legacy call (see few_shots.get_few_shot_scenarios).
    app.state.manychat_client = ManyChatClient(api_token=settings.manychat_api_token)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # dev only; use alembic in prod

    worker_task = asyncio.create_task(start_worker(app.state))

    yield

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await app.state.manychat_client.aclose()
    await engine.dispose()


app = FastAPI(title="Fertility DM Backend", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

authentication_backend = AdminAuth(secret_key=settings.secret_key)
sqladmin = Admin(
    app,
    session_maker=AsyncSessionLocal,
    base_url="/sqladmin",
    title="Fertility Bot Admin",
    authentication_backend=authentication_backend,
    templates_dir="templates",
)
sqladmin.add_view(ConversationAdmin)
sqladmin.add_view(UserStateAdmin)
sqladmin.add_view(PendingMessageAdmin)
sqladmin.add_view(AppConfigAdmin)

app.include_router(health.router, tags=["Health"])
app.include_router(admin_router.router, tags=["Admin"])
app.include_router(webhook_router, tags=["Webhook"])
