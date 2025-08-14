import asyncio
import datetime
from http import HTTPStatus
from pathlib import Path
import time
import json
import io
import base64
import os
from typing import Optional, Union
import uuid
import unicodedata
import re
from fastapi import APIRouter, HTTPException, Response, WebSocket

from dotenv import load_dotenv
load_dotenv()

import matplotlib.pyplot as plt
import requests

from VFRFunctionRoutes import VFRFunctionRoute, VFRPoint, TileRenderer, SVGRenderer  # pylint: disable=no-name-in-module
from VFRFunctionRoutes.classes import VFRCoordSystem, VFRRouteState  # pylint: disable=no-name-in-module
from VFRFunctionRoutes.projutils import PointXY
from VFRFunctionRoutes.rendering import SimpleRect


rootpath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

routes = APIRouter()

global_requests_session = requests.Session()
VFRFunctionRoute.download_map(global_requests_session, os.path.join(rootpath, 'data'))

tilerenderers = {
    'low': TileRenderer("hungarymap",
                        os.path.join(rootpath, "data"),
                        VFRFunctionRoute.PDF_FILE,
                        0,
                        VFRFunctionRoute.PDF_MARGINS,
                        VFRFunctionRoute.LOW_DPI),
    'high': TileRenderer("hungarymap",
                         os.path.join(rootpath, "data"),
                         VFRFunctionRoute.PDF_FILE,
                         0,
                         VFRFunctionRoute.PDF_MARGINS,
                         VFRFunctionRoute.HIGH_DPI),
}


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



_vfrroutes = SessionStore(ttl_seconds=3600)
_vfrroutes.load()


async def cleanup_loop():
    while True:
        _vfrroutes.cleanup()
        _vfrroutes.save()
        await asyncio.sleep(60)  # run every minute


async def send_tiled_image_header(websocket: WebSocket, renderer: TileRenderer, area: SimpleRect, additional_data: dict = None):
    if additional_data is None:
        additional_data = {}
    _, crop, image_size, tile_range = renderer.get_tile_list_for_area(area)
    await websocket.send_json({"type": "tiled-image",
                               "tilesetname": renderer.tileset_name,
                               "dpi": renderer.dpi,
                               "tilesize": {"x": renderer.tile_size[0], "y": renderer.tile_size[1]},
                               "tilecount": {"x": renderer.tile_count[0], "y": renderer.tile_count[1]},
                               "imagesize": {"x": image_size[0], "y": image_size[1]},
                               "tilecrop": {"x0": crop.p0.x, "y0": crop.p0.y, "x1": crop.p1.x, "y1": crop.p1.y},
                               "tilerange": {"x": tile_range[0:2], "y": tile_range[2:4]},
                               "additional_data": additional_data,
                              })


@routes.get("/tile/{tileset_name}/{dpi}/{x}/{y}",
            responses={
                200: {
                    "content": {"image/png": {}}
                }
            },
            response_class=Response)
async def get_tile(tileset_name: str, dpi: int, x: int, y:int):
    matching_renderers = [r for k, r in tilerenderers.items() if r.tileset_name==tileset_name and r.dpi==dpi]
    if len(matching_renderers)>1:
        raise HTTPException(HTTPStatus.BAD_REQUEST, 
                            f"Multiple renderers matched ({tileset_name}, {dpi})", 
                            {"X-Error": "Multiple renderers matched"}
                           )
    if len(matching_renderers)==0:
        raise HTTPException(HTTPStatus.BAD_REQUEST,
                            f"No renderers matched ({tileset_name}, {dpi})", 
                            {"X-Error": "No renderers matched"}
                           )
    renderer = matching_renderers[0]
    image = renderer.get_tile(x, y)
    return Response(content=image,
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=2592000, immutable", # 30 days
                        "ETag": f"tilecache-{tileset_name}-{dpi}-{x}-{y}",
                        "Last-Modified": datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
                    })



@routes.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = None):
    await websocket.accept()

    if not session_id:
        session_id = websocket.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        await websocket.send_json({"type": "new_session", "session_id": session_id})
    print("Session id:", session_id)

    rte: Union[VFRFunctionRoute, None] = _vfrroutes.get(session_id)

    while True:
        try:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msgtype = msg.get("type")

            ####################
            # General messages #
            ####################
            if msgtype=='step':
                if rte:
                    step = msg.get("step", rte._state.value+1)
                    try:
                        newstate = VFRRouteState(step)
                        rte.set_state(newstate)
                    except ValueError:
                        print(f"Not a valid VFRRouteState: {step}")

            ################################################
            # Step 0: Initialize a VFRFunctionRoute object #
            ################################################
            elif msgtype == 'get-published-routes':
                routefiles = [f for f in os.listdir(os.path.join(rootpath, "routes")) if os.path.isfile(os.path.join(rootpath, "routes", f)) and f.endswith('.vfr')]
                await websocket.send_json({"type": "published-routes", "routes": routefiles})
            elif msgtype=='create':
                try:
                    dv = msg.get("dof", None)
                    if dv:
                        d = datetime.datetime.fromisoformat(dv)
                    else:
                        d = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)
                    rte = VFRFunctionRoute(
                        msg.get("name", "Untitled route"),
                        msg.get("speed", 90),
                        d,
                        session = global_requests_session,
                        workfolder=os.path.join(rootpath, "data"),
                        outfolder=os.path.join(rootpath, "output"),
                        tracksfolder=os.path.join(rootpath, "tracks")
                    )
                    _vfrroutes.set(session_id, rte)
                    await websocket.send_json({"type": "load-result", "result": "success"})
                except:
                    await websocket.send_json({"type": "load-result", "result": "failed"})
            elif msgtype=='sample':
                try:
                    rte = default_route()
                    _vfrroutes.set(session_id, rte)
                    await websocket.send_json({"type": "load-result", "result": "success"})
                except:
                    await websocket.send_json({"type": "load-result", "result": "failed"})
            elif msgtype == 'load':
                try:
                    rte = VFRFunctionRoute.fromJSON(
                        msg.get('data'),
                        session=global_requests_session,
                        workfolder=os.path.join(rootpath, "data"),
                        outfolder=os.path.join(rootpath, "output"),
                        tracksfolder=os.path.join(rootpath, "tracks")
                    )

                    _vfrroutes.set(session_id, rte)
                    await websocket.send_json({"type": "load-result", "result": "success", "step": rte._state.value})
                except:
                    await websocket.send_json({"type": "load-result", "result": "failed"})
            elif msgtype=='load-published':
                try:
                    with open(os.path.join(rootpath, "routes", msg["fname"]), 'rt', encoding='utf8') as f:
                        rte = VFRFunctionRoute.fromJSON(''.join(f.readlines()),
                                                        global_requests_session,
                                                        workfolder=os.path.join(rootpath, "data"),
                                                        outfolder=os.path.join(rootpath, "output"),
                                                        tracksfolder=os.path.join(rootpath, "data")
                                                        )
                    _vfrroutes.set(session_id, rte)
                    await websocket.send_json({"type": "load-result", "result": "success", "step": rte._state.value})
                except:
                    await websocket.send_json({"type": "load-result", "result": "failed"})

            #######################################################
            # Step 1: mark an 'area of interest' on a low-res map #
            #######################################################
            elif msgtype=='get-area-of-interest': 
                if rte:
                    tl = rte.area_of_interest["top-left"].project_point(VFRCoordSystem.MAP_XY)
                    br = rte.area_of_interest["bottom-right"].project_point(VFRCoordSystem.MAP_XY)
                    await websocket.send_text(json.dumps({
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
                    }))

            elif msgtype == 'get-low-res-map':
                if rte:
                    renderer = tilerenderers["low"]
                    await send_tiled_image_header(websocket, renderer, TileRenderer.rect_to_simplerect(renderer._crop_rect))

            elif msgtype=='set-area-of-interest':
                if rte:
                    tl = msg.get("topleft")
                    br = msg.get("bottomright")
                    rte.set_area_of_interest(tl.get("x"), tl.get("y"), br.get("x"), br.get("y"))
                    _vfrroutes.set(session_id, rte)
                    tl = rte.area_of_interest["top-left"].project_point(VFRCoordSystem.MAP_XY)
                    br = rte.area_of_interest["bottom-right"].project_point(VFRCoordSystem.MAP_XY)
                    await websocket.send_text(json.dumps({
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
                    }))

            ####################################################################
            # Step 2: mark the waypoints on a high-res map of area of interest #
            ####################################################################
            elif msgtype=='get-waypoints':
                if rte:
                    await websocket.send_text(json.dumps({
                        "type": "waypoints",
                        "waypoints": [{"name": name,
                                        "x": pp.x, 
                                        "y": pp.y,
                                        "lon": p.lon,
                                        "lat": p.lat,
                                        } for name, p, pp in [(name, p, p.project_point(VFRCoordSystem.MAPCROP_XY)) for name, p in rte.waypoints]]
                    }))

            elif msgtype == 'get-waypoints-map':
                if rte:
                    await send_tiled_image_header(websocket, tilerenderers["high"], rte.calc_basemap_clip())

            elif msgtype=='update-wps':
                if rte:
                    rte.update_waypoints(msg.get("waypoints"))
                    _vfrroutes.set(session_id, rte)
                    wps = [{
                        "name": name,
                        "x": pp.x,
                        "y": pp.y,
                        "lon": p.lon,
                        "lat": p.lat,
                    } for name, p, pp in [(name, p, p.project_point(VFRCoordSystem.MAPCROP_XY)) for name, p in rte.waypoints]]
                    await websocket.send_text(json.dumps({
                        "type": "waypoints",
                        "waypoints": wps,
                    }))

            ################################################################################
            # Step 3: define the legs: add constraint points, define function and x values #
            ################################################################################
            elif msgtype=='get-legs':
                if rte:
                    await websocket.send_text(json.dumps({
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
                    }))

            elif msgtype == 'get-legs-map':
                if rte:
                    await send_tiled_image_header(websocket, tilerenderers["high"], rte.calc_basemap_clip())

            elif msgtype=='update-legs':
                if rte:
                    rte.update_legs(msg.get("legs"))
                    _vfrroutes.set(session_id, rte)
                    await websocket.send_text(json.dumps({
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
                    }))

            #############################################################################
            # Step 4: define annotation points, their names and an offset of the bubble #
            #############################################################################
            elif msgtype=='get-annotations':
                if rte:
                    await websocket.send_json({
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
                    })

            elif msgtype == 'get-annotations-map':
                if rte:
                    clip = rte.calc_basemap_clip()
                    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_annotations)
                    await send_tiled_image_header(websocket,
                                                  tilerenderers["high"],
                                                  clip, {
                                                    "svg_overlay": svgrenderer.get_svg(),
                                                  }
                                                 )

            elif msgtype=='update-annotations':
                if rte:
                    rte.update_annotations(msg.get("annotations"))
                    _vfrroutes.set(session_id, rte)
                    clip = rte.calc_basemap_clip()
                    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_annotations)
                    await websocket.send_text(json.dumps({
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
                    }))

            ###################################
            # Step 5: add tracks to the route #
            ###################################
            elif msgtype=='get-tracks':
                if rte:
                    await websocket.send_text(json.dumps({
                        "type": "tracks",
                        "tracks": [{
                            "name": trk.fname,
                            "color": trk.color,
                            "num_points": len(trk.points)
                        } for trk in rte.tracks]
                    }))

            elif msgtype == 'get-tracks-map':
                if rte:
                    clip = rte.calc_basemap_clip()
                    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
                    await send_tiled_image_header(websocket,
                                                  tilerenderers["high"],
                                                  clip, {
                                                    "svg_overlay": svgrenderer.get_svg(),
                                                  }
                                                 )

            elif msgtype == 'load-track':
                if rte:
                    rte.add_track(msg.get('filename'), msg.get('color', '#0000FF'), base64.b64decode(msg.get('data')))
                    _vfrroutes.set(session_id, rte)
                    clip = rte.calc_basemap_clip()
                    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
                    await websocket.send_text(json.dumps({
                        "type": "tracks",
                        "svg_overlay": svgrenderer.get_svg(),
                        "tracks": [{
                            "name": trk.fname,
                            "color": trk.color,
                            "num_points": len(trk.points)
                        } for trk in rte.tracks]
                    }))

            elif msgtype=='update-tracks':
                if rte:
                    rte.update_tracks(msg.get('tracks'))
                    _vfrroutes.set(session_id, rte)
                    clip = rte.calc_basemap_clip()
                    svgrenderer = SVGRenderer(clip, 'pdf', rte.HIGH_DPI, rte.HIGH_DPI, draw_func=rte.draw_tracks)
                    await websocket.send_text(json.dumps({
                        "type": "tracks",
                        "svg_overlay": svgrenderer.get_svg(),
                        "tracks": [{
                            "name": trk.fname,
                            "color": trk.color,
                            "num_points": len(trk.points)
                        } for trk in rte.tracks]
                    }))

            ##################################################################
            # Step 6: Download and save generated files or save to the cloud #
            ##################################################################
            elif msgtype=='get-docx':
                if rte:
                    buf = rte.create_doc(False)
                    if buf:
                        await websocket.send_text(json.dumps({
                            "type": "docx",
                            "mime": 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            "filename": f"{rte.name}.docx",
                        }))
                        await websocket.send_bytes(buf.getvalue())

            elif msgtype=='get-png':
                if rte:
                    image = rte.draw_map(True)
                    await websocket.send_json({
                        "type": "png",
                        "mime": 'image/png',
                        "filename": f"{rte.name}.png"
                    })
                    await websocket.send_bytes(image)

            elif msgtype=='get-gpx':
                if rte:
                    await websocket.send_text(json.dumps({
                        "type": "gpx",
                        "data":  rte.save_plan(),
                        "mime": 'application/gpx+xml',
                        "filename": f"{rte.name}.gpx"
                    }))

            elif msgtype=='get-vfr':
                if rte:
                    await websocket.send_text(json.dumps({
                        "type": "vfr",
                        "data":  rte.toJSON(),
                        "mime": 'application/vnd.VFRFunctionRoutes.project+json',
                        "filename": f"{rte.name}.vfr"
                    }))

            elif msgtype=='get-dof':
                if rte:
                    await websocket.send_text(json.dumps({
                        "type": "dof",
                        "dof":  rte.dof.isoformat(),
                    }))

            elif msgtype == 'set-dof':
                if rte:
                    dv = msg.get("dof", None)
                    if dv:
                        d = datetime.datetime.fromisoformat(dv)
                        rte.dof = d
                        _vfrroutes.set(session_id, rte)
                    await websocket.send_text(json.dumps({
                        "type": "dof",
                        "dof":  rte.dof.isoformat(),
                    }))

            elif msgtype == 'save-to-cloud':
                if rte:
                    try:
                        if len(os.listdir(os.path.join(rootpath, 'routes')))<100:
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
                            await websocket.send_json({"type": "save-to-cloud-result",
                                                    "result": "success",
                                                    "fname": fname})
                        else:
                            await websocket.send_json({"type": "save-to-cloud-result", "result": "too-many-files"})
                    except:
                        await websocket.send_json({"type": "save-to-cloud-result", "result": "fail"})
                else:
                    await websocket.send_json({"type": "save-to-cloud-result", "result": "no-route"})




        except Exception as e:
            print(f"WebSocket error: {e}")
            import traceback
            traceback.print_exc()
            break




def default_route():
    with open(os.path.join(Path(__file__).parent, 'LHFH--Lovasberény--Császár--Nyergesújfalu--LHFH.vfr'), 'rt', encoding='utf8') as f:
        rgen = VFRFunctionRoute.fromJSON(''.join(f.readlines()),
                                         global_requests_session,
                                         workfolder=os.path.join(rootpath, "data"),
                                         outfolder=os.path.join(rootpath, "output"),
                                         tracksfolder=os.path.join(rootpath, "data")
                                        )
    
    return rgen