import asyncpg
from typing import AsyncGenerator
from app.config import settings

class DatabaseManager:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Initialize the async connection pool."""
        self.pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=2,  # Keep at least 2 connections open
            max_size=10  # Scale up to 10 during high traffic
        )

    async def disconnect(self):
        """Close all database connections safely."""
        if self.pool:
            await self.pool.close()

# Global database instance
db = DatabaseManager()

# FastAPI Dependency to inject a connection into our routes
async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Yields a database connection from the pool and releases it back when done."""
    async with db.pool.acquire() as connection:
        yield connection