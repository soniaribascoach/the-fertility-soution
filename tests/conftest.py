import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.db.database import Base


@pytest.fixture
def mock_cfg():
    return {
        "system_prompt": "You are a warm, empathetic fertility coaching assistant.",
        "hard_nos": "competitor\nother clinic",
        "medical_blocklist": "metformin\nclomid\nIVF medication",
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
