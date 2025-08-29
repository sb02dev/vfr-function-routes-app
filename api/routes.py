import asyncio
import base64
import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
import re
import time
import json
import os
import traceback
from typing import Optional, Union
import unicodedata
import uuid
import logging

from fastapi import APIRouter, HTTPException, Response, WebSocket, WebSocketException, WebSocketDisconnect, status

from dotenv import load_dotenv
load_dotenv()

import requests

from VFRFunctionRoutes import *
from .sockets import sio, SESSION_COOKIE_NAME



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

mapmanager = MapManager([int(os.getenv("LOW_DPI", "72")),
                         int(os.getenv("DOC_DPI", "200")),
                         int(os.getenv("HIGH_DPI", "600"))
                        ], global_requests_session)



def pregenerate_tiles():
    """Generates tile caches for all tiles in all maps"""
    count_all_tiles = 0
    for mapname, curmap in mapmanager.maps.items():
        for dpi, tr in curmap.tilerenderers.items():
            count_all_tiles += tr.tile_count.x * tr.tile_count.y
    count_finished_tiles = 0
    for mapname, curmap in mapmanager.maps.items():
        for dpi, tr in curmap.tilerenderers.items():
            for xi in range(tr.tile_count.x):
                for yi in range(tr.tile_count.y):
                    #print(f"Generating {mapname}-{dpi}-x{xi}-y{yi} ({count_finished_tiles}/{count_all_tiles})", flush=True)
                    try:
                        tr.get_tile(xi, yi, return_format='none')
                        count_finished_tiles += 1
                    except:
                        _logger.error(traceback.format_exc())


class SessionStore:
    def __init__(self, ttl_seconds: int = 600):
        # session_id -> (data, expiry_time)
        self._store: dict[str, tuple[time.time, VFRFunctionRoute]] = {}
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
            json_store[k] = { "expiry": exp, "route": rte.toDict() }
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
                    VFRFunctionRoute.fromDict(v['route'],
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
    while True:
        _vfrroutes.cleanup()
        _vfrroutes.save()
        await asyncio.sleep(60)  # run every minute


async def get_tiled_image_header(renderer: TileRenderer, area: SimpleRect, additional_data: dict = None):
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
    renderer = mapmanager.get_tilerenderer(tileset_name, dpi)
    if renderer is None:
        raise HTTPException(HTTPStatus.BAD_REQUEST,
                            f"No renderers matched ({tileset_name}, {dpi})", 
                            {"X-Error": "No renderers matched"}
                           )
    image = renderer.get_tile(x, y)
    return Response(content=image,
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=2592000, immutable", # 30 days
                        "ETag": f"tilecache-{tileset_name}-{dpi}-{x}-{y}",
                        "Last-Modified": datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
                    })


@routes.get("/cachestatus")
async def get_cache_status():
    count_all_tiles = 0
    for mapname, curmap in mapmanager.maps.items():
        for dpi, tr in curmap.tilerenderers.items():
            count_all_tiles += tr.tile_count.x * tr.tile_count.y
    count_finished_tiles = 0
    for mapname, curmap in mapmanager.maps.items():
        for dpi, tr in curmap.tilerenderers.items():
            for xi in range(tr.tile_count.x):
                for yi in range(tr.tile_count.y):
                    if os.path.isfile(os.path.join(tr.datafolder, tr._get_tile_id(xi, yi)+".png")):
                        count_finished_tiles += 1
    return {"finished": count_finished_tiles,
            "total": count_all_tiles,
            "progress": f"{count_finished_tiles/count_all_tiles*100 if count_all_tiles!=0 else 0:.2f}%"
           }


##########################################
### Socket.IO lifecycle event handlers ###
##########################################
_sid_to_session_id: dict[str, str] = {}

@sio.on("connect")
async def connect(sid, environ, auth):
    """Socket.IO Connect: Session management + authentication"""
    # get session_id from cookies (sent by client if it already has it)
    cookies = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    session_id = cookies.get("session_id").value if "session_id" in cookies else None

    if not session_id and isinstance(auth, dict):
        session_id = auth.get(SESSION_COOKIE_NAME)

    new_session = False
    if not session_id:
        # fallback: generate one if handshake didn’t have it
        session_id = str(uuid.uuid4())
        new_session = True

    # load the session
    rte: Optional[VFRFunctionRoute] = _vfrroutes.get(session_id)

    # limit connections
    if rte is None and _vfrroutes.count() >= MAX_SESSIONS:
        raise ConnectionRefusedError("session limit reached")

    # if a new session id is issued, communicate it
    if new_session:
        await sio.emit("new_session", {"session_id": session_id}, to=sid)

    # log
    _logger.info("New connection to session %s from %s", session_id, sid)

    # set the session id enter that as a room and accept connection
    environ["session_id"] = session_id
    _sid_to_session_id[sid] = session_id
    await sio.enter_room(sid, session_id)
    return True

@sio.on("disconnect")
async def sio_disconnect(sid):
    _sid_to_session_id.pop(sid, None)

# helpers to obtain the session_id
def _get_session_id_from_room(sid: str) -> str:
    return next(r for r in sio._sio.rooms(sid) if r != sid)

def _get_session_id_from_environ(sid: str) -> str:
    return sio._sio.get_environ(sid).get(SESSION_COOKIE_NAME)

def _get_session_id_from_dict(sid: str) -> str:
    return _sid_to_session_id.get(sid, '---')

def get_session(sid: str) -> tuple[str, VFRFunctionRoute]:
    """Prepare the session variables for any given Socket.IO event"""
    # get the session id from somewhere
    session_id = _get_session_id_from_room(sid)
    # increase the session expiry
    _vfrroutes.touch(session_id)
    # get the route for the session
    rte = _vfrroutes.get(session_id)
    # return
    return session_id, rte


def require_session(require_route: bool=True):
    def decorator(handler):
        async def wrapper(sid, *args):
            session_id, rte = get_session(sid)
            if require_route and rte is None:
                # send error message
                await sio.emit("result", {"result": "no-route"}, to=sid)
                return None
            return await handler(sid, session_id, rte, *args)
        return wrapper
    return decorator


def error_handler(handler):
    async def wrapper(sid, *args):
        try:
            return await handler(sid, *args)
        except Exception as error:
            trace = traceback.format_exc()
            _logger.error(f"[{sid}] error in {handler.__name__}: {error}\n{trace}")
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
async def do_step(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    session_id, rte = get_session(sid)
    if rte:
        step = msg.get("step", rte._state.value+1)
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
async def get_published_routes(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    routefiles = [f for f in os.listdir(os.path.join(rootpath, "routes")) if os.path.isfile(os.path.join(rootpath, "routes", f)) and f.endswith('.vfr')]
    return {"type": "published-routes",
            "routes": routefiles,
            "has_open_route": rte is not None,
            "maps": list(mapmanager.maps.keys())
           }

@sio.on('create')
@require_session(False)
@error_handler
async def create_new_route(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    try:
        dv = msg.get("dof", None)
        if dv:
            d = datetime.datetime.fromisoformat(dv)
        else:
            d = datetime.datetime.now(datetime.timezone.utc) + \
                datetime.timedelta(days=2)
        rte = VFRFunctionRoute(
            msg.get("name", "Untitled route"),
            mapmanager.maps.get(msg.get("mapname", "HUNGARY"), None),
            msg.get("speed", 90),
            d,
            session=global_requests_session,
            workfolder=os.path.join(rootpath, "data"),
            outfolder=os.path.join(rootpath, "output"),
            tracksfolder=os.path.join(rootpath, "tracks")
        )
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success"}
    except Exception as e:
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


@sio.on('sample')
@require_session(False)
@error_handler
async def create_sample(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    try:
        rte = default_route()
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success"}
    except Exception as e:
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


@sio.on('load')
@require_session(False)
@error_handler
async def load_local_route(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    try:
        rte = VFRFunctionRoute.fromJSON(
            msg.get('data'),
            session=global_requests_session,
            workfolder=os.path.join(rootpath, "data"),
            outfolder=os.path.join(rootpath, "output"),
            tracksfolder=os.path.join(rootpath, "tracks")
        )
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success", "step": rte._state.value}
    except Exception as e:
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


@sio.on('load-published')
@require_session(False)
@error_handler
async def load_published_route(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    try:
        with open(os.path.join(rootpath, "routes", msg["fname"]), 'rt', encoding='utf8') as f:
            rte = VFRFunctionRoute.fromJSON(''.join(f.readlines()),
                                            global_requests_session,
                                            workfolder=os.path.join(rootpath, "data"),
                                            outfolder=os.path.join(rootpath, "output"),
                                            tracksfolder=os.path.join(rootpath, "data")
                                           )
        _vfrroutes.set(session_id, rte)
        return {"type": "load-result", "result": "success", "step": rte._state.value}
    except Exception as e:
        traceback.print_exc()
        return {"type": "load-result", "result": "failed", "exception": e}


#######################################################
# Step 1: mark an 'area of interest' on a low-res map #
#######################################################

@sio.on('get-area-of-interest')
@require_session(True)
@error_handler
async def get_area_of_interest(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
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
async def get_low_res_map(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    renderer = rte.map.get_tilerenderer(int(os.getenv('LOW_DPI', '72')))
    return await get_tiled_image_header(renderer, TileRenderer.rect_to_simplerect(renderer._crop_rect))


@sio.on('set-area-of-interest')
@require_session(True)
@error_handler
async def set_area_of_interest(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
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
async def get_waypoints(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    return {
        "type": "waypoints",
        "waypoints": [{"name": name,
                        "x": pp.x,
                        "y": pp.y,
                        "lon": p.lon,
                        "lat": p.lat,
                        } for name, p, pp in [(name, p, p.project_point(VFRCoordSystem.MAPCROP_XY)) for name, p in rte.waypoints]]
    }


@sio.on('get-waypoints-map')
@require_session(True)
@error_handler
async def get_waypoints_map(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    return await get_tiled_image_header(renderer, rte.calc_basemap_clip())


@sio.on('update-wps')
@require_session(True)
@error_handler
async def update_waypoints(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    rte.update_waypoints(msg.get("waypoints"))
    _vfrroutes.set(session_id, rte)
    wps = [{
        "name": name,
        "x": pp.x,
        "y": pp.y,
        "lon": p.lon,
        "lat": p.lat,
    } for name, p, pp in [(name, p, p.project_point(VFRCoordSystem.MAPCROP_XY)) for name, p in rte.waypoints]]
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
async def get_legs(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    return {
        "type": "legs",
        "legs": [{"name": leg.name,
                    "function_name": leg.function_name,
                    "function_range": leg.function_range,
                    "matrix_func2cropmap": leg._matrix_func2cropmap.tolist(),
                    "matrix_cropmap2func": leg._matrix_cropmap2func.tolist(),
                    "points": [{
                        "lon": p.lon, 
                        "lat": p.lat,
                        "x": pp.x,
                        "y": pp.y,
                        "func_x": x
                    } for p, x, pp in [(p, x, p.project_point(VFRCoordSystem.MAPCROP_XY)) for p, x in leg.points]],
                    }  for leg in rte.legs]
    }


@sio.on('get-legs-map')
@require_session(True)
@error_handler
async def get_legs(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    return await get_tiled_image_header(renderer, rte.calc_basemap_clip())


@sio.on('update-legs')
@require_session(True)
@error_handler
async def update_legs(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    rte.update_legs(msg.get("legs"))
    _vfrroutes.set(session_id, rte)
    return {
        "type": "legs",
        "legs": [{"name": leg.name,
                    "function_name": leg.function_name,
                    "function_range": leg.function_range,
                    "matrix_func2cropmap": leg._matrix_func2cropmap.tolist(),
                    "matrix_cropmap2func": leg._matrix_cropmap2func.tolist(),
                    "points": [{
                        "lon": p.lon,
                        "lat": p.lat,
                        "x": pp.x,
                        "y": pp.y,
                        "func_x": x
                    } for p, x, pp in [(p, x, p.project_point(VFRCoordSystem.MAPCROP_XY)) for p, x in leg.points]],
                    } for leg in rte.legs]
    }


#############################################################################
# Step 4: define annotation points, their names and an offset of the bubble #
#############################################################################

@sio.on('get-annotations')
@require_session(True)
@error_handler
async def get_annotations(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    return {
        "type": "annotations",
        "annotations": [{
                    "name": leg.name,
                    "function_name": leg.function_name,
                    "matrix_func2cropmap": leg._matrix_func2cropmap.tolist(),
                    "matrix_cropmap2func": leg._matrix_cropmap2func.tolist(),
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
async def get_annotations_map(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_annotations)
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    return await get_tiled_image_header(renderer,
                                        clip, {
                                            "svg_overlay": svgrenderer.get_svg(),
                                        }
                                       )


@sio.on('update-annotations')
@require_session(True)
@error_handler
async def update_annotations(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    rte.update_annotations(msg.get("annotations"))
    _vfrroutes.set(session_id, rte)
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_annotations)
    return {
        "type": "annotations",
        "svg_overlay": svgrenderer.get_svg(),
        "annotations": [{
                    "name": leg.name,
                    "function_name": leg.function_name,
                    "matrix_func2cropmap": leg._matrix_func2cropmap.tolist(),
                    "matrix_cropmap2func": leg._matrix_cropmap2func.tolist(),
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
async def get_tracks(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
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
async def get_tracks_map(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
    renderer = rte.map.get_tilerenderer(int(os.getenv('HIGH_DPI', '600')))
    return await get_tiled_image_header(renderer,
                                        clip, {
                                            "svg_overlay": svgrenderer.get_svg(),
                                        }
                                       )


@sio.on('load-track')
@require_session(True)
@error_handler
async def load_track(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    rte.add_track(msg.get('filename'), msg.get('color', '#0000FF'), base64.b64decode(msg.get('data')))
    _vfrroutes.set(session_id, rte)
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
    return {
        "type": "tracks",
        "svg_overlay": svgrenderer.get_svg(),
        "tracks": [{
            "name": trk.fname,
            "color": trk.color,
            "num_points": len(trk.points)
        } for trk in rte.tracks]
    }


@sio.on('update-tracks')
@require_session(True)
@error_handler
async def update_tracks(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
    rte.update_tracks(msg.get('tracks'))
    _vfrroutes.set(session_id, rte)
    clip = rte.calc_basemap_clip()
    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
    return {
        "type": "tracks",
        "svg_overlay": svgrenderer.get_svg(),
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
async def get_docx(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    buf = rte.create_doc(False)
    if buf:
        return {
            "type": "docx",
            "mime": 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            "filename": f"{rte.name}.docx",
        }, buf.getvalue()


@sio.on('get-png')
@require_session(True)
@error_handler
async def get_png(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    image = rte.draw_map(True)
    return {
        "type": "png",
        "mime": 'image/png',
        "filename": f"{rte.name}.png"
    }, image


@sio.on('get-gpx')
@require_session(True)
@error_handler
async def get_gpx(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    return {
        "type": "gpx",
        "data":  rte.save_plan(),
        "mime": 'application/gpx+xml',
        "filename": f"{rte.name}.gpx"
    }


@sio.on('get-vfr')
@require_session(True)
@error_handler
async def get_vfr(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    return {
        "type": "vfr",
        "data":  rte.toJSON(),
        "mime": 'application/vnd.VFRFunctionRoutes.project+json',
        "filename": f"{rte.name}.vfr"
    }


@sio.on('get-route-data')
@require_session(True)
@error_handler
async def get_route_data(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    return {
        "type": "route-data",
        "name": rte.name,
        "speed": rte.speed,
        "dof":  rte.dof.isoformat(),
    }


@sio.on('set-route-data')
@require_session(True)
@error_handler
async def set_route_data(sid: str, session_id: str, rte: Optional[VFRFunctionRoute], msg):
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
async def save_to_cloud(sid: str, session_id: str, rte: Optional[VFRFunctionRoute]):
    try:
        if len(os.listdir(os.path.join(rootpath, 'routes'))) < 100:
            rtename_normalized = re.sub(r'[^a-zA-Z0-9\- !@#$%\^\(\)]',
                                        '_',
                                        unicodedata.normalize('NFKD', rte.name).
                                        encode('ascii', errors='replace').decode('ascii'))
            fname = f"{rtename_normalized}.vfr"
            cnt = 0
            while os.path.isfile(os.path.join(rootpath, 'routes', fname)):
                fname = f"{rtename_normalized}-{cnt:04d}.vfr"
                cnt += 1
            with open(os.path.join(rootpath, 'routes', fname), "wt", encoding='utf8') as f:
                f.write(rte.toJSON())
            return {"type": "save-to-cloud-result",
                    "result": "success",
                    "fname": fname
                   }
        else:
            return {"type": "save-to-cloud-result", "result": "too-many-files"}
    except Exception as e:
        return {"type": "save-to-cloud-result", "result": "fail"}




def default_route():
    with open(os.path.join(Path(__file__).parent, 'LHFH--Lovasberény--Császár--Nyergesújfalu--LHFH.vfr'), 'rt', encoding='utf8') as f:
        rgen = VFRFunctionRoute.fromJSON(''.join(f.readlines()),
                                         global_requests_session,
                                         workfolder=os.path.join(rootpath, "data"),
                                         outfolder=os.path.join(rootpath, "output"),
                                         tracksfolder=os.path.join(rootpath, "data")
                                        )
    
    return rgen