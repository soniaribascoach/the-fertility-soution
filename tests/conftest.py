"""Shared pytest fixtures for the brain test suite."""
import pytest_asyncio
from openai import AsyncOpenAI

from config import settings


@pytest_asyncio.fixture
async def openai_client():
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        yield client
    finally:
        await client.close()
