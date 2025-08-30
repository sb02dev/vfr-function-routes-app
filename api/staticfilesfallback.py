"""
A StaticFile override to handle Angular's rewrite rules
"""

from fastapi.staticfiles import StaticFiles
from starlette.types import Scope
from starlette.exceptions import HTTPException
from starlette.responses import Response


class StaticFilesFallback(StaticFiles):
    """
    A StaticFile override to handle Angular's rewrite rules
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        """
        Overrides get_response to fall back to default index.html for everything which is not found
        """
        try:
            resp = await super().get_response(path, scope)
        except HTTPException:
            resp = await super().get_response("index.html", scope)
        return resp
