"""The server, socketio server and database setup"""
import asyncio
from contextlib import asynccontextmanager
import multiprocessing
import os
import uuid
import asyncpg
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_socketio import SocketManager

from .staticfilesfallback import StaticFilesFallback
from . import sockets


DB_DSN = os.getenv("DB_DSN", "postgres://user:pass@url")
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {sockets.TABLE_NAME} (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    content JSONB NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW()
);
"""


@asynccontextmanager
async def lifespan(base_app: FastAPI):
    """Resources initialization and cleanup function"""
    # setup the session cleanup (expiry) checking
    asyncio.create_task(cleanup_loop())
    # setup the initial tile cache generation
    p = multiprocessing.Process(target=pregenerate_tiles, daemon=True)
    p.start()
    # connect to the database & create table(s)
    base_app.state.pool = await asyncpg.create_pool(dsn=DB_DSN)
    sockets.pool = base_app.state.pool
    async with base_app.state.pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)
    # give back control to server app
    yield
    # close database connection
    await base_app.state.pool.close()


app = FastAPI(title="VFRFunctionRoutes WebApp", lifespan=lifespan)

cors_origins = [
    "http://localhost:4200",
    "http://localhost:8000",
    "https://productive-nanette-sb02dev-0de6fcde.koyeb.app"
]

app.add_middleware(
    CORSMiddleware,
    # Angular dev server
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend",
          StaticFilesFallback(directory="frontend/browser", html=True),
          name="frontend")

sockets.sio = SocketManager(app=app,
                            cors_allowed_origins="*",#cors_origins,
                            mount_location="/socket.io"
                           )

from .routes import routes, cleanup_loop, pregenerate_tiles #pylint: disable=wrong-import-position


@app.middleware("http")
async def assign_session_id(request: Request, call_next):
    """A middleware to assign a session_id to all incoming requests"""
    session_id = request.cookies.get(sockets.SESSION_COOKIE_NAME)
    if not session_id:
        session_id = str(uuid.uuid4())

    response: Response = await call_next(request)
    if sockets.SESSION_COOKIE_NAME not in request.cookies:
        response.set_cookie(
            sockets.SESSION_COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="Lax",  # Or "Strict" / "None"
            secure=False     # Set to True in production with HTTPS
        )
    return response


@app.get("/")
async def root():
    """
    We need a redirect from root to frontend
    """
    return RedirectResponse("/frontend", status_code=status.HTTP_303_SEE_OTHER)


app.include_router(routes, prefix="/api")
