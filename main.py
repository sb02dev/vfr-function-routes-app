import uuid
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import RedirectResponse

from api import routes
from api.staticfilesfallback import StaticFilesFallback

app = FastAPI()

app.mount("/frontend",
          StaticFilesFallback(directory="frontend/browser", html=True),
          name="frontend")


SESSION_COOKIE_NAME = "session_id"

@app.middleware("http")
async def assign_session_id(request: Request, call_next):
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

if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app",
                host="0.0.0.0", port=8000,
                log_level="debug",
                reload=True,
                reload_includes="**/*.{py,htm*,js}"
               )
