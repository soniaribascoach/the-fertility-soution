import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.db.database import Base


@pytest.fixture
def mock_cfg():
    return {
        "prompt_about": "We are a warm, empathetic fertility coaching clinic.",
        "prompt_services": "IVF support, fertility coaching, emotional guidance.",
        "prompt_tone": "Speak with warmth and clarity. Avoid clinical jargon.",
        "medical_blocklist": "metformin\nclomid\nIVF medication",
        "medical_deflection": "",
        "booking_link": "https://example.com/book",
        "score_threshold": "70",
    }


@pytest.fixture
def mock_openai_client():
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock()
    return client


@pytest_asyncio.fixture
async def async_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncTestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncTestSession() as session:
        yield session

    await engine.dispose()
