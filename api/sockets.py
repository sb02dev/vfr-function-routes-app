"""
Just a placeholder module, to allow kind of a "late binding" of FastAPI_SocketIO
"""
import os
from typing import Optional, Union
import asyncpg
from fastapi import Request
from fastapi_socketio import SocketManager

sio: Union[SocketManager, None] = None
pool: Optional[asyncpg.Pool] = None

SESSION_COOKIE_NAME = "session_id"
TABLE_NAME = os.getenv("PUBLISHED_ROUTES_DBTABLE", "published_routes_dev")


async def get_db_pool(request: Request) -> asyncpg.Pool:
    """A Dependency for accessing the database from FastAPI HTTP endpoints"""
    return request.app.state.pool
