import datetime
import json, io, base64
import os
from fastapi import APIRouter, WebSocket
from dotenv import load_dotenv

import matplotlib.pyplot as plt
import requests

from VFRFunctionRoutes import VFRFunctionRoute, VFRPoint
from VFRFunctionRoutes.classes import VFRCoordSystem, VFRRouteState


load_dotenv()
rootpath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

routes = APIRouter()


@routes.get("/wtf")
async def wtf():
    return {'message': 'It works!'}


_routes: dict = {}

@routes.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = websocket.cookies.get("session_id")
    await websocket.accept()

    rte: VFRFunctionRoute = _routes.get(session_id, None)
    width = 800
    height = 600

    while True:
        try:
            data = await websocket.receive_text()
            msg = json.loads(data)
            event = msg.get("type")

            if event in ['init', 'resize']:
                width = msg.get("width", 800)
                height = msg.get("height", 600)

            match event:
                ####################
                # General messages #
                ####################
                case 'step-back':
                    if rte and rte._state.value>1:
                        rte.set_state(VFRRouteState(rte._state.value-1))

                case 'step-forward':
                    if rte and rte._state.value<max(v.value for v in VFRRouteState):
                        rte.set_state(rte._state.value+1)

                ################################################
                # Step 0: Initialize a VFRFunctionRoute object #
                ################################################
                case 'create':
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
                        tracksfolder=os.path.join(rootpath, "data")
                    )
                    _routes[session_id] = rte
                case 'sample':
                    rte = default_route()
                    _routes[session_id] = rte
                case 'load':
                    data = json.loads(msg.get('data'))
                    print(data)
                    rte = default_route()
                    _routes[session_id] = rte

                #######################################################
                # Step 1: mark an 'area of interest' on a low-res map #
                #######################################################
                case 'get-low-res-map':
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

                case 'set-area-of-interest':
                    if rte:
                        step = msg.get("step", False)
                        tl = msg.get("topleft")
                        br = msg.get("bottomright")
                        rte.set_area_of_interest(tl.get("x"), tl.get("y"), br.get("x"), br.get("y"))
                        if step:
                            rte.set_state(VFRRouteState.AREAOFINTEREST)
                        tl = rte.area_of_interest["top-left"].project_point(VFRCoordSystem.MAP_XY)
                        br = rte.area_of_interest["bottom-right"].project_point(VFRCoordSystem.MAP_XY)
                        await websocket.send_text(json.dumps({
                            "type": "area-of-interest",
                            "step": step,
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
                case 'get-high-res-map':
                    if rte:
                        with rte.get_highres_map() as fig:
                            image = _get_image_from_figure(fig, dpi=rte.DPI)
                            await websocket.send_text(json.dumps({
                                "type": "high-res",
                                "image": image,
                                "waypoints": [{"name": name,
                                               "x": pp.x, 
                                               "y": pp.y,
                                               "lon": p.lon,
                                               "lat": p.lat,
                                              } for name, p, pp in [(name, p, p.project_point(VFRCoordSystem.MAPCROP_XY)) for name, p in rte.waypoints]]
                            }))

                case 'update-wps':
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


        except Exception as e:
            print(f"WebSocket error: {e}")
            import traceback
            traceback.print_exc()
            break


def _get_image_from_figure(fig: plt.figure, size: tuple[float, float] = None, dpi: float = None) -> str:
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


    rgen.add_leg(
        'LHFH->Lovasberény',
        '$f(x)=\\sqrt[3]{{x}}$ $x\\in [0,1.5]$',
        '$x=0$ at Lovasberény, $x=1.5$ at LHFH',
        lambda x: x ** (1. / 3.),
        [
            # (lat, lon, x),
            (VFRPoint(18.55314689455907, 47.31145066437747), 0),
            (VFRPoint(18.912424867046774, 47.48950030173632), 1.5)
        ]
    ).add_annotation("START", 1.5, (-120, 10)) \
    .add_annotation("Etyek", 0.8, (20, -25)) \
    .add_annotation("Alcsútdoboz", 0.3, (25, -45)) \
    .add_annotation("Vértesacsa", 0.12, (35, -75)) \
    .add_annotation("Lovasberény", 0.0001, (-90, 25))

    rgen.add_leg(
        'Lovasberény->Császár',
        r'$f(x)=\frac{1}{e^x}$ $x\in [-\frac{\pi}{2},\pi]$',
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
        r'$f(x)=sin(x)$ $x\in [0,\pi]$',
        r'$x=0$ at Császár, $x=\pi$ at LHFH, $x=\frac{\pi}{2}$ at Nyergesújfalu',
        lambda x: math.sin(x),
        [
            (VFRPoint(18.13993451767051, 47.50100085714328), 0),
            (VFRPoint(18.912424867046774, 47.48950030173632), math.pi),
            (VFRPoint(18.54614123145077, 47.7612944935143), math.pi/2)
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

    rgen.finalize()

    return rgen    