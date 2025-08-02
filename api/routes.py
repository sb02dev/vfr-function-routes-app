import datetime
import json
import io
import base64
import os
from typing import Union
from fastapi import APIRouter, WebSocket
from dotenv import load_dotenv
load_dotenv()

import matplotlib.pyplot as plt
import requests

from VFRFunctionRoutes import VFRFunctionRoute, VFRPoint  # pylint: disable=no-name-in-module
from VFRFunctionRoutes.classes import VFRCoordSystem, VFRRouteState  # pylint: disable=no-name-in-module


rootpath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

routes = APIRouter()


_vfrroutes: dict = {}

@routes.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = websocket.cookies.get("session_id")
    await websocket.accept()

    rte: Union[VFRFunctionRoute, None] = _vfrroutes.get(session_id, None)

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
                    rte.set_state(VFRRouteState(msg.get("step", rte._state.value+1)))

            ################################################
            # Step 0: Initialize a VFRFunctionRoute object #
            ################################################
            elif msgtype=='create':
                dv = msg.get("dof", None)
                if dv:
                    d = datetime.datetime.fromisoformat(dv)
                else:
                    d = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)
                rte = VFRFunctionRoute(
                    msg.get("name", "Untitled route"),
                    msg.get("speed", 90),
                    d,
                    session = requests.Session(),
                    workfolder=os.path.join(rootpath, "data"),
                    outfolder=os.path.join(rootpath, "output"),
                    tracksfolder=os.path.join(rootpath, "tracks")
                )
                _vfrroutes[session_id] = rte
            elif msgtype=='sample':
                rte = default_route()
                _vfrroutes[session_id] = rte
            elif msgtype=='load':
                rte = VFRFunctionRoute.fromJSON(
                    msg.get('data'), 
                    session=requests.Session(),
                    workfolder=os.path.join(rootpath, "data"),
                    outfolder=os.path.join(rootpath, "output"),
                    tracksfolder=os.path.join(rootpath, "tracks")
                )

                _vfrroutes[session_id] = rte

            #######################################################
            # Step 1: mark an 'area of interest' on a low-res map #
            #######################################################
            elif msgtype=='get-low-res-map':
                if rte:
                    tl = rte.area_of_interest["top-left"].project_point(VFRCoordSystem.MAP_XY)
                    br = rte.area_of_interest["bottom-right"].project_point(VFRCoordSystem.MAP_XY)
                    with rte.get_lowres_map() as fig:
                        image = _get_image_from_figure(fig, dpi=rte.LOWDPI)
                        await websocket.send_text(json.dumps({
                            "type": "low-res", 
                            "image": image,
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

            elif msgtype=='set-area-of-interest':
                if rte:
                    tl = msg.get("topleft")
                    br = msg.get("bottomright")
                    rte.set_area_of_interest(tl.get("x"), tl.get("y"), br.get("x"), br.get("y"))
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
            elif msgtype=='get-waypoints-map':
                if rte:
                    with rte.get_highres_map() as (fig, _):
                        image = _get_image_from_figure(fig, dpi=rte.DPI)
                        await websocket.send_text(json.dumps({
                            "type": "waypoints-map",
                            "image": image,
                            "waypoints": [{"name": name,
                                            "x": pp.x, 
                                            "y": pp.y,
                                            "lon": p.lon,
                                            "lat": p.lat,
                                            } for name, p, pp in [(name, p, p.project_point(VFRCoordSystem.MAPCROP_XY)) for name, p in rte.waypoints]]
                        }))

            elif msgtype=='update-wps':
                if rte:
                    rte.updateWaypoints(msg.get("waypoints"))
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
            elif msgtype=='get-legs-map':
                if rte:
                    with rte.get_highres_map() as (fig, _):
                        image = _get_image_from_figure(fig, dpi=rte.DPI)
                        await websocket.send_text(json.dumps({
                            "type": "legs-map",
                            "image": image,
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

            elif msgtype=='update-legs':
                if rte:
                    rte.updateLegs(msg.get("legs"))
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
            elif msgtype=='get-annotations-map':
                if rte:
                    with rte.get_annotations_map() as (fig, _):
                        image = _get_image_from_figure(fig, dpi=rte.DPI)
                        await websocket.send_text(json.dumps({
                            "type": "annotations-map",
                            "image": image,
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
            elif msgtype=='get-tracks-map':
                if rte:
                    with rte.get_tracks_map() as (fig, _):
                        image = _get_image_from_figure(fig, dpi=rte.DPI)
                        await websocket.send_text(json.dumps({
                            "type": "tracks-map",
                            "image": image,
                            "tracks": [{
                                "name": trk.fname,
                                "color": trk.color,
                                "num_points": len(trk.points)
                            } for trk in rte.tracks]
                        }))

            elif msgtype=='load-track':
                if rte:
                    rte.add_track(msg.get('filename'), msg.get('color', '#0000FF'), base64.b64decode(msg.get('data')))
                    with rte.get_tracks_map() as (fig, _):
                        image = _get_image_from_figure(fig, dpi=rte.DPI)
                        await websocket.send_text(json.dumps({
                            "type": "tracks-map",
                            "image": image,
                            "tracks": [{
                                "name": trk.fname,
                                "color": trk.color,
                                "num_points": len(trk.points)
                            } for trk in rte.tracks]
                        }))

            elif msgtype=='update-tracks':
                if rte:
                    rte.update_tracks(msg.get('tracks'))
                    with rte.get_tracks_map() as (fig, _):
                        image = _get_image_from_figure(fig, dpi=rte.DPI)
                        await websocket.send_text(json.dumps({
                            "type": "tracks-map",
                            "image": image,
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
                        b64 = base64.b64encode(buf.read()).decode("utf-8")
                        await websocket.send_text(json.dumps({
                            "type": "docx",
                            "data": b64,
                            "mime": 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            "filename": f"{rte.name}.docx",
                        }))

            elif msgtype=='get-png':
                if rte:
                    fig, _ = rte.draw_map()
                    image = _get_image_from_figure(fig, dpi=rte.DPI)
                    plt.close(fig)
                    await websocket.send_text(json.dumps({
                        "type": "png",
                        "data":  image,
                        "mime": 'image/png',
                        "filename": f"{rte.name}.png"
                    }))

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




        except Exception as e:
            print(f"WebSocket error: {e}")
            import traceback
            traceback.print_exc()
            break


def _get_image_from_figure(fig, size: tuple[float, float] = None, dpi: float = None) -> str:
    buf = io.BytesIO()
    if size:
        figsize = fig.get_size_inches()
        dpi = min(size[0] / figsize[0], size[1] / figsize[1])
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0, dpi=dpi)
    buf.seek(0)
    image = base64.b64encode(buf.read()).decode("utf-8")
    return image



def default_route():
    import math
    sess = requests.Session()
    rgen = VFRFunctionRoute(
        "LHFH--Lovasberény--Császár--Nyergesújfalu--LHFH",
        100,
        # datetime.datetime(2025, 6, 9, 7, 0, tzinfo=datetime.timezone.utc),
        datetime.datetime.now(datetime.timezone.utc) +
        datetime.timedelta(days=2),
        session=sess,
        workfolder=r"E:\dev\projects\VFRFunctionRoutes\data",
        outfolder=r"E:\dev\projects\VFRFunctionRoutes\output",
        tracksfolder=r"E:\dev\projects\VFRFunctionRoutes\data"
    )

    rgen.set_area_of_interest(858, 542, 1268, 852)

    rgen.set_state(VFRRouteState.AREAOFINTEREST)

    rgen.add_waypoint("LHFH", VFRPoint(18.912424867046774, 47.48950030173632, VFRCoordSystem.LONLAT, rgen))
    rgen.add_waypoint("Lovasberény", VFRPoint(18.55314689455907, 47.31145066437747, VFRCoordSystem.LONLAT, rgen))
    rgen.add_waypoint("Császár", VFRPoint(18.13993451767051, 47.50100085714328, VFRCoordSystem.LONLAT, rgen))

    rgen.set_state(VFRRouteState.LEGS) # because we also want to add annotations

    rgen.legs = [] # TODO: currently recreate (should be updating and calculating lambdas)
    rgen.add_leg(
        'LHFH->Lovasberény',
        '\\sqrt[3]{{x}}',
        '$x=0$ at Lovasberény, $x=1.5$ at LHFH',
        lambda x: x ** (1. / 3.),
        [
            # (lat, lon, x),
            (VFRPoint(18.912424867046774, 47.48950030173632), 1.5),
            (VFRPoint(18.55314689455907, 47.31145066437747), 0)
        ]
    ).add_annotation("START", 1.5, (-120, 10)) \
    .add_annotation("Etyek", 0.8, (20, -25)) \
    .add_annotation("Alcsútdoboz", 0.3, (25, -45)) \
    .add_annotation("Vértesacsa", 0.12, (35, -75)) \
    .add_annotation("Lovasberény", 0.0001, (-90, 25))

    rgen.add_leg(
        'Lovasberény->Császár',
        r'\frac{1}{e^x}',
        r'$x=\pi$ at Lovasberény, $x=-\frac{\pi}{2}$ at Császár',
        lambda x: 1. / math.exp(x),
        [
            (VFRPoint(18.55314689455907, 47.31145066437747), math.pi),
            (VFRPoint(18.13993451767051, 47.50100085714328), -math.pi/2)
        ]
    ).add_annotation("Lovasberény", math.pi, (-30, -35)) \
    .add_annotation("Zámolyi vízt", math.pi-1., (-80, -30)) \
    .add_annotation("Csber/Malmás", math.pi-3., (-100, -40)) \
    .add_annotation("Mór", math.pi-3.9, (-100, -20)) \
    .add_annotation("Császár", -math.pi/2, (-90, -40)) \

    rgen.add_leg(
        'Császár->LHFH',
        r'\sin\left(x\right)',
        r'$x=0$ at Császár, $x=\pi$ at LHFH, $x=\frac{\pi}{2}$ at Nyergesújfalu',
        lambda x: math.sin(x), # pylint disable=unneccessary-lambda
        [
            (VFRPoint(18.13993451767051, 47.50100085714328), 0),
            (VFRPoint(18.54614123145077, 47.7612944935143), math.pi/2),
            (VFRPoint(18.912424867046774, 47.48950030173632), math.pi)
        ]
    ).add_annotation("Császár", 0, (-80, 40)) \
    .add_annotation("Szákszend", 0.15, (10, 0)) \
    .add_annotation("M1", 0.5, (-110, 20)) \
    .add_annotation("Tata", 0.7, (-60, 40)) \
    .add_annotation("Dsztmikl", 0.93, (0, -80)) \
    .add_annotation("Lábatlan", 1.35, (-40, 30)) \
    .add_annotation("Nyergesújfalu", 1.6, (20, 30)) \
    .add_annotation("Csolnok", 2.25, (-110, -20)) \
    .add_annotation("Tinnye", 2.57, (-25, 60)) \
    .add_annotation("Telki", 2.9, (-33, 80)) \
    .add_annotation("END", math.pi, (-140, 60))

    rgen.set_state(VFRRouteState.ANNOTATIONS)

    rgen.finalize()

    return rgen    