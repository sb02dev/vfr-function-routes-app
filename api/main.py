import asyncio
from contextlib import asynccontextmanager
import multiprocessing
import uuid
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import RedirectResponse

from .routes import routes, cleanup_loop, pregenerate_tiles
from .staticfilesfallback import StaticFilesFallback


@asynccontextmanager
async def lifespan(base_app: FastAPI):
    """Resources initialization and cleanup function"""
    # setup the session cleanup (expiry) checking
    asyncio.create_task(cleanup_loop())
    # setup the initial tile cache generation
    p = multiprocessing.Process(target=pregenerate_tiles, daemon=True)
    p.start()
    # give back control to server app
    yield
    # cleanup resources
    pass


app = FastAPI(title="VFRFunctionRoutes WebApp", lifespan=lifespan)

app.mount("/frontend",
          StaticFilesFallback(directory="frontend/browser", html=True),
          name="frontend")


SESSION_COOKIE_NAME = "session_id"

@app.middleware("http")
async def assign_session_id(request: Request, call_next):
    """A middleware to assign a session_id to all incoming requests"""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        session_id = str(uuid.uuid4())

    response: Response = await call_next(request)
    if SESSION_COOKIE_NAME not in request.cookies:
        response.set_cookie(
            SESSION_COOKIE_NAME,
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
