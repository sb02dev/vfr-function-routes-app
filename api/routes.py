"""
The main route handlers of both HTTP and Socket.IO endpoints for
communication with the frontend app
"""
import asyncio
import base64
import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
import time
import json
import os
import traceback
from typing import Optional, cast
import uuid
import logging
import numpy as np
import requests

from fastapi import APIRouter, HTTPException, Response
from fastapi_socketio import SocketManager

from dotenv import load_dotenv
load_dotenv()

# pylint: disable=wrong-import-position
from VFRFunctionRoutes import (
    VFRFunctionRoute, VFRRouteState, VFRCoordSystem,
    MapManager, MapDefinition, TileRenderer, SVGRenderer,
    SimpleRect
)
from . import sockets
from .remote_cache import S3Cache
# pylint: enable=wrong-import-position


assert sockets.sio is not None, "You should setup SocketManager before importing this module."
sio: SocketManager = sockets.sio


# Max number of concurrent sessions allowed
MAX_SESSIONS = int(os.getenv('MAX_SESSIONS', '10'))
# get the root path of the application
rootpath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# set up logging
_logger = logging.getLogger('routes')
_logger.setLevel(logging.DEBUG)

# HTTP endpoints router
routes = APIRouter()

# set up maps
global_requests_session = requests.Session()

remote_cache = S3Cache()
mapmanager = MapManager([int(os.getenv("LOW_DPI", "72")),
                         int(os.getenv("DOC_DPI", "200")),
                         int(os.getenv("HIGH_DPI", "600"))
                        ], global_requests_session,
                        remote_cache=remote_cache)



def pregenerate_tiles():
    """Generates tile caches for all tiles in all maps"""
    count_all_tiles = 0
    for _, curmap in mapmanager.maps.items():
        for _, tr in curmap.tilerenderers.items():
            count_all_tiles += tr.tile_count.x * tr.tile_count.y
    count_finished_tiles = 0
    for mapname, curmap in mapmanager.maps.items():
        for dpi, tr in curmap.tilerenderers.items():
            for xi in range(tr.tile_count.x):
                for yi in range(tr.tile_count.y):
                    try:
                        if not tr.check_cached(xi, yi):
                            print(f"rendering {mapname}/{dpi}/{xi}-{yi}...")
                            tr.render_tile(xi, yi)
                        count_finished_tiles += 1
                    except Exception:  # pylint: disable=broad-exception-caught
                        _logger.error(traceback.format_exc())


class SessionStore:
    """A storage object and helper methods for in-memory session keeping.
    Handles the time-to-live and expiry features.
    Also supports flushing it to disk for resumes.
    """
    def __init__(self, ttl_seconds: int = 600):
        # session_id -> (data, expiry_time)
        self._store: dict[str, tuple[float, VFRFunctionRoute]] = {}
        self.ttl = ttl_seconds

    def set(self, session_id: str, data: VFRFunctionRoute):
        """Store or update session data with TTL."""
        expiry = time.time() + self.ttl
        self._store[session_id] = (expiry, data)

    def get(self, session_id: str) -> Optional[VFRFunctionRoute]:
        """Retrieve data if not expired, else remove it."""
        item = self._store.get(session_id)
        if not item:
            return None
        expiry, data = item
        if time.time() > expiry:
            del self._store[session_id]  # expire
            return None
        return data

    def delete(self, session_id: str) -> None:
        """Delete a Route and session_id from the session store, freeing up a slot"""
        if session_id not in self._store:
            return
        del self._store[session_id]

    def count(self) -> int:
        """Gets the number of open sessions"""
        return len(self._store.keys())

    def touch(self, session_id: str) -> None:
        """Sets the expiry of the given session to now+ttl (no expiry while used)"""
        expiry = time.time() + self.ttl
        item = self._store.get(session_id)
        if not item:
            return
        _, data = item
        self._store[session_id] = (expiry, data)

    def cleanup(self):
        """Remove expired sessions. Call periodically."""
        now = time.time()
        expired = [sid for sid, (expiry, _)
                   in self._store.items() if now > expiry]
        for sid in expired:
            del self._store[sid]

    def save(self):
        """Saves the session store to disk. Call periodically."""
        json_store = {}
        for k, (exp, rte) in self._store.items():
            json_store[k] = { "expiry": exp, "route": rte.to_dict() }
        with open(os.path.join(rootpath, 'data', 'session_cache.json'), 'wt', encoding='utf8') as f:
            json.dump(json_store, f, indent=2)

    def load(self):
        """Loads the session store from disk (if it exists, otherwise clears
           memory store). Call on startup.
        """
        # check if cache exists
        fname = os.path.join(rootpath, 'data', 'session_cache.json')
        if not os.path.isfile(fname):
            self._store.clear()
            return
        # load from file to dict
        with open(fname, 'rt', encoding='utf8') as f:
            json_store = json.load(f)
        # load to memory store but only non-expired ones
        now = time.time()
        self._store.clear()
        for k, v in json_store.items():
            if now <= v['expiry']:
                self._store[k] = (
                    v['expiry'],
                    VFRFunctionRoute.from_dict(v['route'],
                                              session = global_requests_session,
                                              workfolder=os.path.join(rootpath, "data"),
                                              outfolder=os.path.join(rootpath, "output"),
                                              tracksfolder=os.path.join(rootpath, "tracks")
                    )
                )

    def __len__(self):
        return len(self._store)



_vfrroutes = SessionStore(ttl_seconds=int(os.getenv('SESSION_TTL', '300')))
_vfrroutes.load()


async def cleanup_loop():
    """A loop to be run as a background task which clears the expired sessions."""
    while True:
        _vfrroutes.cleanup()
        _vfrroutes.save()
        await asyncio.sleep(60)  # run every minute


async def get_tiled_image_header(renderer: TileRenderer,
                                 area: SimpleRect,
                                 additional_data: Optional[dict] = None):
    """Gets the message to be sent to the frontend when tiled images should
    be shown for a specified area of the map
    """
    if additional_data is None:
        additional_data = {}
    _, crop, image_size, tile_range = renderer.get_tile_list_for_area(area)
    return {"type": "tiled-image",
            "tilesetname": renderer.tileset_name,
            "dpi": renderer.dpi,
            "tilesize": {"x": renderer.tile_size[0], "y": renderer.tile_size[1]},
            "tilecount": {"x": renderer.tile_count[0], "y": renderer.tile_count[1]},
            "imagesize": {"x": image_size[0], "y": image_size[1]},
            "tilecrop": {"x0": crop.p0.x, "y0": crop.p0.y, "x1": crop.p1.x, "y1": crop.p1.y},
            "tilerange": {"x": tile_range[0:2], "y": tile_range[2:4]},
            "additional_data": additional_data,
           }


@routes.get("/tile/{tileset_name}/{dpi}/{x}/{y}",
            responses={
                200: {
                    "content": {"image/png": {}}
                }
            },
            response_class=Response)
async def get_tile(tileset_name: str, dpi: int, x: int, y:int):
    """HTTP endpoint to retreive a tile of the given map in the given resolution"""
    renderer = mapmanager.get_tilerenderer(tileset_name, dpi)
    if renderer is None:
        raise HTTPException(HTTPStatus.BAD_REQUEST,
                            f"No renderers matched ({tileset_name}, {dpi})",
                            {"X-Error": "No renderers matched"}
                           )
    image = renderer.get_tile(x, y)[0]
    return Response(content=image,
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=2592000, immutable", # 30 days
                        "ETag": f"tilecache-{tileset_name}-{dpi}-{x}-{y}",
                        "Last-Modified": 
                            datetime.datetime.utcnow() \
                                .strftime('%a, %d %b %Y %H:%M:%S GMT')
                    })


@routes.get("/cachestatus")
async def get_cache_status():
    """An HTTP endpoint to check the status of the tile pregeneration."""
    count_all_tiles = 0
    for _, curmap in mapmanager.maps.items():
        for _, tr in curmap.tilerenderers.items():
            count_all_tiles += tr.tile_count.x * tr.tile_count.y
    count_finished_tiles = 0
    for _, curmap in mapmanager.maps.items():
        for _, tr in curmap.tilerenderers.items():
            for xi in range(tr.tile_count.x):
                for yi in range(tr.tile_count.y):
                    if tr.check_cached(xi, yi, True):
                        count_finished_tiles += 1
    return {"finished": count_finished_tiles,
            "total": count_all_tiles,
            "progress": 
                f"""{count_finished_tiles/count_all_tiles*100
                     if count_all_tiles!=0 else 0:.2f}%"""
           }


##########################################
### Socket.IO lifecycle event handlers ###
##########################################
_sid_to_session_id: dict[str, str] = {}

@sio.on("connect")
async def connect(sid, environ, auth):
    """Socket.IO Connect: Session management + authentication"""
    # get session_id from cookies (sent by client if it already has it)
    session_id = None

    if isinstance(auth, dict):
        session_id = auth.get(sockets.SESSION_COOKIE_NAME, None)

    if session_id is None:
        cookies = SimpleCookie(environ.get("HTTP_COOKIE", ""))
        if "session_id" in cookies:
            cookieentry = cookies.get("session_id")
            if cookieentry is not None:
                session_id = cookieentry.value


    if not session_id:
        # fallback: generate one if handshake didn’t have it
        session_id = str(uuid.uuid4())

    # load the session
    rte: Optional[VFRFunctionRoute] = _vfrroutes.get(session_id)

    # limit connections
    if rte is None and _vfrroutes.count() >= MAX_SESSIONS:
        async def disconnect(thesid: str):
            await sio.disconnect(thesid)
        await sio.emit("unauthorized",
                       { "reason": "session-limit-reached"},
                       room=sid,
                       callback=lambda *args: asyncio.create_task(disconnect(sid))
                      )
        return

    # save the session_id locally
    await sio.emit("set_session", {"session_id": session_id}, to=sid)

    # log
    _logger.info("New connection to session %s from %s", session_id, sid)

    # set the session id enter that as a room and accept connection
    environ["session_id"] = session_id
    _sid_to_session_id[sid] = session_id
    await sio.enter_room(sid, session_id)
    return True

@sio.on("disconnect")
async def sio_disconnect(sid):
    """A Socket.IO disconnect hook to remove the `sid` from our
    mapping to `session_id`
    """
    _sid_to_session_id.pop(sid, None)

# helpers to obtain the session_id
def _get_session_id_from_room(sid: str) -> str | None:
    try:
        return next(r for r in sio._sio.rooms(sid) if r != sid) # pylint: disable=protected-access
    except (StopIteration, StopAsyncIteration):
        return None

def _get_session_id_from_environ(sid: str) -> str | None:
    env = sio._sio.get_environ(sid)  # pylint: disable=protected-access
    assert env is not None
    return env.get(sockets.SESSION_COOKIE_NAME)

def _get_session_id_from_dict(sid: str) -> str | None:
    return _sid_to_session_id.get(sid, None)

def get_session(sid: str) -> tuple[Optional[str], Optional[VFRFunctionRoute]]:
    """Prepare the session variables for any given Socket.IO event"""
    # get the session id from somewhere
    session_id = _get_session_id_from_room(sid)
    if session_id is None:
        return None, None
    # increase the session expiry
    _vfrroutes.touch(session_id)
    # get the route for the session
    rte = _vfrroutes.get(session_id)
    # return
    return session_id, rte


def require_session(require_route: bool=True):
    """A decorator to easily retrieve the `session_id` in the Socket.IO
    event handlers. While we are at it, we also retreive the Route for
    the given session. And based on the argument, if a Route is required
    we also error out if we don't have a Route available.
    """
    def decorator(handler):
        async def wrapper(sid, *args):
            session_id, rte = get_session(sid)
            if session_id is None:
                await sio.emit("result",
                               {"type": "result",
                                "result": "no-session",
                                "event": None,
                                "exception_type": None,
                                "message": "No active session on the server. " + \
                                           "Maybe you are over the server limit?",
                                "traceback": None
                                }, room=sid)
            if require_route and rte is None:
                # send error message
                await sio.emit("result", {"result": "no-route"}, to=sid)
                return None
            return await handler(sid, session_id, rte, *args)
        return wrapper
    return decorator


def error_handler(handler):
    """A general error handler decorator for the Socket.IO event handlers.
    It sends a general error message to the frontend.
    """
    async def wrapper(sid, *args):
        try:
            return await handler(sid, *args)
        except Exception as error: # pylint: disable=broad-exception-caught
            trace = traceback.format_exc()
            _logger.error("[%s] error in %s: %s\n%s", sid, handler.__name__, str(error), trace)
            await sio.emit("result",
                           {"type": "result",
                            "result": "exception",
                            "event": handler.__name__,
                            "exception_type": error.__class__.__name__,
                            "message": str(error),
                            "traceback": trace
                           }, room=sid)
    return wrapper


######################################
######################################
###                                ###
### Socket.IO logic event handlers ###
###                                ###
######################################
######################################

####################
# General messages #
####################

@sio.on("step")
@require_session(False)
@error_handler
async def do_step(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg): # pylint: disable=unused-argument
    """Handling the frontend's `step` message: we change the Route's `state`."""
    if rte:
        step = msg.get("step", rte.state.value+1)
        try:
            if step > 0:
                newstate = VFRRouteState(step)
                rte.set_state(newstate)
            return {"type": "result", "result": "success"}
        except ValueError:
            print(f"Not a valid VFRRouteState: {step}")
            return {"type": "result", "result": "invalid-step-value"}
    else:
        return {"type": "result", "result": "no-route"}


################################################
# Step 0: Initialize a VFRFunctionRoute object #
################################################

@sio.on("get-published-routes")
@require_session(False)
@error_handler
async def get_published_routes(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):  # pylint: disable=unused-argument
    """Return the following information to the frontend on request:
        - the published Routes saved on the server
        - whether there is a Route associated with that session_id
        - the list of available maps on the server
    """
    assert sockets.pool is not None
    async with sockets.pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT id, filename FROM {sockets.TABLE_NAME} ORDER BY filename")
    routefiles = [{'id': row['id'], 'name': row["filename"]} for row in rows]
    return {"type": "published-routes",
            "routes": routefiles,
            "has_open_route": rte is not None,
            "maps": list(mapmanager.maps.keys())
           }

@sio.on('create')
@require_session(False)
@error_handler
async def create_new_route(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):  # pylint: disable=unused-argument
    """This creates a new Route, associates it with the current `session_id`
    and advances the frontend to the next step.
    Args
        msg: a dict of the following
            "name": the name of the route
            "dof": the Date Of Flight
            "speed": planned speed of the flight in knots
            "mapname": the map to use for the Route
    """
    try:
        dv = msg.get("dof", None)
        if dv:
            d = datetime.datetime.fromisoformat(dv)
        else:
            d = datetime.datetime.now(datetime.timezone.utc) + \
                datetime.timedelta(days=2)
        rte = VFRFunctionRoute(
            msg.get("name", "Untitled route"),
            cast(MapDefinition, mapmanager.maps.get(msg.get("mapname", "HUNGARY"), None)),
            msg.get("speed", 90),
            d,
            session=global_requests_session,
            workfolder=os.path.join(rootpath, "data"),
            outfolder=os.path.join(rootpath, "output"),
            tracksfolder=os.path.join(rootpath, "tracks")
        )
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


@sio.on('sample')
@require_session(False)
@error_handler
async def create_sample(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):  # pylint: disable=unused-argument
    """Opens the sample Route in this session."""
    try:
        rte = default_route()
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success"}
    except Exception as e:  # pylint: disable=broad-exception-caught
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


@sio.on('load')
@require_session(False)
@error_handler
async def load_local_route(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):  # pylint: disable=unused-argument
    """Load a Route from a .VFR file opened on the client. The contents of
    the file should be sent in msg['data'] as a string.
    """
    try:
        rte = VFRFunctionRoute.from_json(
            msg.get('data'),
            session=global_requests_session,
            workfolder=os.path.join(rootpath, "data"),
            outfolder=os.path.join(rootpath, "output"),
            tracksfolder=os.path.join(rootpath, "tracks")
        )
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success", "step": rte.state.value}
    except Exception as e:  # pylint: disable=broad-exception-caught
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


@sio.on('load-published')
@require_session(False)
@error_handler
async def load_published_route(sid: str,  # pylint: disable=unused-argument
                               session_id: str,
                               rte: Optional[VFRFunctionRoute],
                               published_route_id: int):
    """Load a published Route into this session. The Route is referenced
    by `id` which should be sent as an argument. Returns the status of
    the load operation to the frontend.
    """
    try:
        assert sockets.pool is not None
        async with sockets.pool.acquire() as conn:
            row = await conn.fetchrow(f"""SELECT content
                                          FROM {sockets.TABLE_NAME}
                                          WHERE id=$1""", published_route_id)
        rte = VFRFunctionRoute.from_json(row['content'],
                                        global_requests_session,
                                        workfolder=os.path.join(rootpath, "data"),
                                        outfolder=os.path.join(rootpath, "output"),
                                        tracksfolder=os.path.join(rootpath, "data")
                                        )
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success", "step": rte.state.value}
    except Exception as e:  # pylint: disable=broad-exception-caught
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


#######################################################
# Step 1: mark an 'area of interest' on a low-res map #
#######################################################

@sio.on('get-area-of-interest')
@require_session(True)
@error_handler
async def get_area_of_interest(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Returns the area of interest from the Route to the frontend.
    """
    tl = rte.area_of_interest["top-left"].project_point(VFRCoordSystem.MAP_XY)
    br = rte.area_of_interest["bottom-right"].project_point(VFRCoordSystem.MAP_XY)
    low_dpi = int(os.getenv('LOW_DPI', '72'))
    doc_dpi = int(os.getenv('DOC_DPI', '200'))
    mem_usage = abs((br.x-tl.x)/low_dpi*doc_dpi*(br.y-tl.y)/low_dpi*doc_dpi*4)
    return {
        "type": "area-of-interest",
        "top-left": {
            "x": tl.x,
                "y": tl.y,
                "lon": rte.area_of_interest["top-left"].lon,
                "lat": rte.area_of_interest["top-left"].lat,
        },
        "bottom-right": {
            "x": br.x,
            "y": br.y,
            "lon": rte.area_of_interest["bottom-right"].lon,
            "lat": rte.area_of_interest["bottom-right"].lat,
        },
        "status": "ok" if mem_usage < int(os.getenv('IMG_SIZE_WARN_MB', '30'))*1024*1024 else
                    "warning" if mem_usage < int(os.getenv('IMG_SIZE_ERR_MB', '50'))*1024*1024 else
                    "error"
    }


@sio.on('get-low-res-map')
@require_session(True)
@error_handler
async def get_low_res_map(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Returns the metadata information of the low resolution map to the frontend.
    The response includes the tile number, size, etc. The frontend should request
    each tile through the HTTP endpoint.
    """
    renderer = rte.map.get_tilerenderer(int(os.getenv('LOW_DPI', '72')))
    assert renderer is not None
    return await get_tiled_image_header(renderer,
                                        TileRenderer.rect_to_simplerect(renderer.crop_rect))


@sio.on('set-area-of-interest')
@require_session(True)
@error_handler
async def set_area_of_interest(sid: str, session_id: str, rte: VFRFunctionRoute, msg):  # pylint: disable=unused-argument
    """Set area of interest (either by x-y or lon-lat coordinates).
    Returns the new area of interest. Both x-y and lon-lat coordinates
    therefore the conversion is also sent back to the frontend.
    """
    tl = msg.get("topleft")
    br = msg.get("bottomright")
    if 'x' in tl and 'y' in tl and 'x' in br and 'y' in br:
        rte.set_area_of_interest(tl.get("x"), tl.get("y"), br.get("x"), br.get("y"))
    else:
        rte.set_area_of_interest_lonlat(tl.get("lon"), tl.get("lat"), br.get("lon"), br.get("lat"))
    _vfrroutes.set(session_id, rte)
    tl = rte.area_of_interest["top-left"].project_point(VFRCoordSystem.MAP_XY)
    br = rte.area_of_interest["bottom-right"].project_point(VFRCoordSystem.MAP_XY)
    low_dpi = int(os.getenv('LOW_DPI', '72'))
    doc_dpi = int(os.getenv('DOC_DPI', '200'))
    mem_usage = abs((br.x-tl.x)/low_dpi*doc_dpi*(br.y-tl.y)/low_dpi*doc_dpi*4)
    return {
        "type": "area-of-interest",
        "top-left": {
            "x": tl.x,
            "y": tl.y,
            "lon": rte.area_of_interest["top-left"].lon,
            "lat": rte.area_of_interest["top-left"].lat,
        },
        "bottom-right": {
            "x": br.x,
            "y": br.y,
            "lon": rte.area_of_interest["bottom-right"].lon,
            "lat": rte.area_of_interest["bottom-right"].lat,
        },
        "status": "ok" if mem_usage < int(os.getenv('IMG_SIZE_WARN_MB', '30'))*1024*1024 else
                    "warning" if mem_usage < int(os.getenv('IMG_SIZE_ERR_MB', '50'))*1024*1024 else
                    "error"
    }

####################################################################
# Step 2: mark the waypoints on a high-res map of area of interest #
####################################################################

@sio.on('get-waypoints')
@require_session(True)
@error_handler
async def get_waypoints(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Get the waypoints currently defined in the Route"""
    return {
        "type": "waypoints",
        "waypoints": [{"name": name,
                        "x": pp.x,
                        "y": pp.y,
                        "lon": p.lon,
                        "lat": p.lat,
                        } for name, p, pp in [
                            (name, p, p.project_point(VFRCoordSystem.MAPCROP_XY))
                            for name, p in rte.waypoints]]
    }


@sio.on('get-waypoints-map')
@require_session(True)
@error_handler
async def get_waypoints_map(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Returns the metadata information of the map used for waypoint editing
    to the frontend. The response includes the tile number, size, etc. The
    frontend should request each tile through the HTTP endpoint.
    """
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    assert renderer is not None
    return await get_tiled_image_header(renderer, rte.calc_basemap_clip())


@sio.on('update-wps')
@require_session(True)
@error_handler
async def update_waypoints(sid: str, session_id: str, rte: VFRFunctionRoute, msg):  # pylint: disable=unused-argument
    """Update the Route's waypoints according to the edits in the frontend.
    Returns the edits so that x-y -> lon-lat conversions are sent back.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, rte.update_waypoints, msg.get("waypoints"))
    _vfrroutes.set(session_id, rte)
    wps = [{
        "name": name,
        "x": pp.x,
        "y": pp.y,
        "lon": p.lon,
        "lat": p.lat,
    } for name, p, pp in [
        (name, p, p.project_point(VFRCoordSystem.MAPCROP_XY))
        for name, p
        in rte.waypoints]]
    return {
        "type": "waypoints",
        "waypoints": wps,
    }


################################################################################
# Step 3: define the legs: add constraint points, define function and x values #
################################################################################

@sio.on('get-legs')
@require_session(True)
@error_handler
async def get_legs(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Get the Legs currently defined in the Route.
    Also return the transformation matrices, because we need them
    for local drawing.
    """
    return {
        "type": "legs",
        "legs": [{"name": leg.name,
                    "function_name": leg.function_name,
                    "function_range": leg.function_range,
                    "matrix_func2cropmap": cast(np.ndarray, leg.matrix_func2cropmap).tolist(),
                    "matrix_cropmap2func": cast(np.ndarray, leg.matrix_cropmap2func).tolist(),
                    "points": [{
                        "lon": p.lon, 
                        "lat": p.lat,
                        "x": pp.x,
                        "y": pp.y,
                        "func_x": x
                    } for p, x, pp in [
                        (p, x, p.project_point(VFRCoordSystem.MAPCROP_XY))
                        for p, x
                        in leg.points]],
                    }  for leg in rte.legs]
    }


@sio.on('get-legs-map')
@require_session(True)
@error_handler
async def get_legs_map(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Returns the metadata information of the map used for legs editing
    to the frontend. The response includes the tile number, size, etc. The
    frontend should request each tile through the HTTP endpoint.
    """
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    assert renderer is not None
    return await get_tiled_image_header(renderer, rte.calc_basemap_clip())


@sio.on('update-legs')
@require_session(True)
@error_handler
async def update_legs(sid: str, session_id: str, rte: VFRFunctionRoute, msg):  # pylint: disable=unused-argument
    """Update the Route's legs according to the edits in the frontend.
    Returns the edits so that x-y -> lon-lat conversions are sent back.
    Also returns the recalculated transformation matrices, because
    we need them for local drawing.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, rte.update_legs, msg.get("legs"))
    _vfrroutes.set(session_id, rte)
    return {
        "type": "legs",
        "legs": [{"name": leg.name,
                    "function_name": leg.function_name,
                    "function_range": leg.function_range,
                    "matrix_func2cropmap": cast(np.ndarray, leg.matrix_func2cropmap).tolist(),
                    "matrix_cropmap2func": cast(np.ndarray, leg.matrix_cropmap2func).tolist(),
                    "points": [{
                        "lon": p.lon,
                        "lat": p.lat,
                        "x": pp.x,
                        "y": pp.y,
                        "func_x": x
                    } for p, x, pp in [
                        (p, x, p.project_point(VFRCoordSystem.MAPCROP_XY))
                        for p, x
                        in leg.points]],
                    } for leg in rte.legs]
    }


#############################################################################
# Step 4: define annotation points, their names and an offset of the bubble #
#############################################################################

@sio.on('get-annotations')
@require_session(True)
@error_handler
async def get_annotations(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Get the Annotation bubbles currently defined in the Route.
    Also return the transformation matrices, because we need them
    for local drawing.
    """
    return {
        "type": "annotations",
        "annotations": [{
                    "name": leg.name,
                    "function_name": leg.function_name,
                    "matrix_func2cropmap": cast(np.ndarray, leg.matrix_func2cropmap).tolist(),
                    "matrix_cropmap2func": cast(np.ndarray, leg.matrix_cropmap2func).tolist(),
                    "annotations": [{
                        "name": ann.name,
                        "func_x": ann.x,
                        "ofs": {"x": ann.ofs[0], "y": ann.ofs[1]}
                    } for ann in leg.annotations],
                    } for leg in rte.legs]
    }


@sio.on('get-annotations-map')
@require_session(True)
@error_handler
async def get_annotations_map(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Returns the metadata information of the map used for annotation bubble
    editing to the frontend. Also the SVG converted image of the bubbles are
    sent, therefore the client can draw them locally (it is more efficient
    than rendering it in PNG or include in the tiles, due to it being
    uncacheable).
    The response includes the tile number, size, etc. The
    frontend should request each tile through the HTTP endpoint.
    """
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf',
                              rte.HIGH_DPI,
                              rte.HIGH_DPI,
                              draw_func=rte.draw_annotations)
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    assert renderer is not None
    loop = asyncio.get_running_loop()
    svg = await loop.run_in_executor(None, svgrenderer.get_svg)
    return await get_tiled_image_header(renderer,
                                        clip, {
                                            "svg_overlay": svg,
                                        }
                                       )


@sio.on('update-annotations')
@require_session(True)
@error_handler
async def update_annotations(sid: str, session_id: str, rte: VFRFunctionRoute, msg):  # pylint: disable=unused-argument
    """Update the Route's annotation bubbles according to the edits
    in the frontend (like moving of bubble offsets).
    The response includes a new SVG drawing of the recalculated bubbles.
    Also returns the transformation matrices, because
    we need them for local drawing.
    """
    rte.update_annotations(msg.get("annotations"))
    _vfrroutes.set(session_id, rte)
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf',
                              rte.HIGH_DPI,
                              rte.HIGH_DPI,
                              draw_func=rte.draw_annotations)
    loop = asyncio.get_running_loop()
    svg = await loop.run_in_executor(None, svgrenderer.get_svg)
    return {
        "type": "annotations",
        "svg_overlay": svg,
        "annotations": [{
                    "name": leg.name,
                    "function_name": leg.function_name,
                    "matrix_func2cropmap": cast(np.ndarray, leg.matrix_func2cropmap).tolist(),
                    "matrix_cropmap2func": cast(np.ndarray, leg.matrix_cropmap2func).tolist(),
                    "annotations": [{
                        "name": ann.name,
                        "func_x": ann.x,
                        "ofs": {"x": ann.ofs[0], "y": ann.ofs[1]}
                    } for ann in leg.annotations],
                    } for leg in rte.legs]
    }

###################################
# Step 5: add tracks to the route #
###################################

@sio.on('get-tracks')
@require_session(True)
@error_handler
async def get_tracks(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Get the Tracks currently defined in the Route."""
    return {
        "type": "tracks",
        "tracks": [{
            "name": trk.fname,
            "color": trk.color,
            "num_points": len(trk.points)
        } for trk in rte.tracks]
    }


@sio.on('get-tracks-map')
@require_session(True)
@error_handler
async def get_tracks_map(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Returns the metadata information of the map used for tracks
    editing to the frontend. Also the SVG converted image of the tracks are
    sent, therefore the client can draw them locally (it is more efficient
    than rendering it in PNG or include in the tiles, due to it being
    uncacheable).
    The response includes the tile number, size, etc. The
    frontend should request each tile through the HTTP endpoint.
    """
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    assert renderer is not None
    loop = asyncio.get_running_loop()
    svg = await loop.run_in_executor(None, svgrenderer.get_svg)
    return await get_tiled_image_header(renderer,
                                        clip, {
                                            "svg_overlay": svg,
                                        }
                                       )


@sio.on('load-track')
@require_session(True)
@error_handler
async def load_track(sid: str, session_id: str, rte: VFRFunctionRoute, msg):  # pylint: disable=unused-argument
    """Add a new track based on the data sent in msg['data'] and named
    according to msg['filename].
    Sends back a recalculated SVG with the new track included.
    """
    rte.add_track(msg.get('filename'),
                  msg.get('color', '#0000FF'),
                  base64.b64decode(msg.get('data')))
    _vfrroutes.set(session_id, rte)
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
    loop = asyncio.get_running_loop()
    svg = await loop.run_in_executor(None, svgrenderer.get_svg)
    return {
        "type": "tracks",
        "svg_overlay": svg,
        "tracks": [{
            "name": trk.fname,
            "color": trk.color,
            "num_points": len(trk.points)
        } for trk in rte.tracks]
    }


@sio.on('update-tracks')
@require_session(True)
@error_handler
async def update_tracks(sid: str, session_id: str, rte: VFRFunctionRoute, msg):  # pylint: disable=unused-argument
    """Update Tracks according to edits in fronted.
    Sends back a recalculated SVG with the updated tracks.
    """
    rte.update_tracks(msg.get('tracks'))
    _vfrroutes.set(session_id, rte)
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
    loop = asyncio.get_running_loop()
    svg = await loop.run_in_executor(None, svgrenderer.get_svg)
    return {
        "type": "tracks",
        "svg_overlay": svg,
        "tracks": [{
            "name": trk.fname,
            "color": trk.color,
            "num_points": len(trk.points)
        } for trk in rte.tracks]
    }

##################################################################
# Step 6: Download and save generated files or save to the cloud #
##################################################################

@sio.on('get-docx')
@require_session(True)
@error_handler
async def get_docx(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Render and send the final Word format Pilot's Log.
    It uses real Weather forecast.
    """
    loop = asyncio.get_running_loop()
    buf = await loop.run_in_executor(None, rte.create_doc, False)
    if buf:
        return {
            "type": "docx",
            "mime": 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            "filename": f"{rte.name}.docx",
        }, buf.getvalue()


@sio.on('get-png')
@require_session(True)
@error_handler
async def get_png(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Render and send the map for the Pilot's Log.
    It uses real Weather forecast.
    """
    loop = asyncio.get_running_loop()
    image = await loop.run_in_executor(None, rte.draw_map, True)
    return {
        "type": "png",
        "mime": 'image/png',
        "filename": f"{rte.name}.png"
    }, image


@sio.on('get-gpx')
@require_session(True)
@error_handler
async def get_gpx(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Return the Route in a GPX file which can be imported in
    EFBs. It uses linear approximation of the Route not to
    overload the EFB (SkyDemon slows down due to lots of points).
    """
    loop = asyncio.get_running_loop()
    plan = await loop.run_in_executor(None, rte.save_plan)
    return {
        "type": "gpx",
        "data":  plan,
        "mime": 'application/gpx+xml',
        "filename": f"{rte.name}.gpx"
    }


@sio.on('get-vfr')
@require_session(True)
@error_handler
async def get_vfr(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Return the Route serialized into JSON. Can be saved on client
    and later loaded from there."""
    return {
        "type": "vfr",
        "data":  rte.to_json(),
        "mime": 'application/vnd.VFRFunctionRoutes.project+json',
        "filename": f"{rte.name}.vfr"
    }


@sio.on('get-route-data')
@require_session(True)
@error_handler
async def get_route_data(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Returns the metadata of the Route for editing in the last step."""
    return {
        "type": "route-data",
        "name": rte.name,
        "speed": rte.speed,
        "dof":  rte.dof.isoformat(),
    }


@sio.on('set-route-data')
@require_session(True)
@error_handler
async def set_route_data(sid: str, session_id: str, rte: VFRFunctionRoute, msg):  # pylint: disable=unused-argument
    """Sets the Route's metadata and returns the new values."""
    dv = msg.get("dof", None)
    rte.name = msg.get("name", rte.name)
    rte.speed = msg.get("speed", rte.speed)
    if dv:
        d = datetime.datetime.fromisoformat(dv)
        rte.dof = d
    _vfrroutes.set(session_id, rte)
    return {
        "type": "route-data",
        "name": rte.name,
        "speed": rte.speed,
        "dof":  rte.dof.isoformat(),
    }


@sio.on('save-to-cloud')
@require_session(True)
@error_handler
async def save_to_cloud(sid: str, session_id: str, rte: VFRFunctionRoute):  # pylint: disable=unused-argument
    """Saves the Route on the server. A Route saved like this is
    available to all users of the app."""
    try:
        assert sockets.pool is not None
        async with sockets.pool.acquire() as conn:
            rows = await conn.fetch(f"""SELECT id, filename
                                        FROM {sockets.TABLE_NAME}
                                        ORDER BY filename""")
        if len(rows) < int(os.getenv("MAX_PUBLISHED_ROUTES", "100")):
            if rte.name not in [row["filename"] for row in rows]:
                async with sockets.pool.acquire() as conn:
                    await conn.execute(
                                f"""
                                INSERT INTO {sockets.TABLE_NAME} (filename, content)
                                VALUES ($1, $2::jsonb)
                                """,
                                rte.name,
                                rte.to_json(),
                            )
                return {"type": "save-to-cloud-result",
                        "result": "success",
                        "fname": rte.name
                    }

            return {"type": "save-to-cloud-result", "result": "filename-already-exists"}

        return {"type": "save-to-cloud-result", "result": "too-many-files"}

    except Exception:  # pylint: disable=broad-exception-caught
        return {"type": "save-to-cloud-result", "result": "fail"}


@sio.on('close-route')
@require_session(True)
@error_handler
async def close_route(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):  # pylint: disable=unused-argument
    """This event closes the route, thus freeing up session for other users"""
    _vfrroutes.delete(session_id)
    return True




def default_route():
    """Load the sample Route from file."""
    with open(os.path.join(Path(__file__).parent,
                           'LHFH--Lovasberény--Császár--Nyergesújfalu--LHFH.vfr'
                          ), 'rt', encoding='utf8') as f:
        rgen = VFRFunctionRoute.from_json(''.join(f.readlines()),
                                         global_requests_session,
                                         workfolder=os.path.join(rootpath, "data"),
                                         outfolder=os.path.join(rootpath, "output"),
                                         tracksfolder=os.path.join(rootpath, "data")
                                        )

    return rgen
