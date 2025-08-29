"""
Just a placeholder module, to allow kind of a "late binding" of FastAPI_SocketIO
"""
from typing import Union
from fastapi_socketio import SocketManager
sio: Union[SocketManager, None] = None

SESSION_COOKIE_NAME = "session_id"
