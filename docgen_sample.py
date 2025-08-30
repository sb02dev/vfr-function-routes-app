"""
An example use of VFRFunctionRoutes library
"""
import os
import math
import datetime
import requests
from dotenv import load_dotenv
load_dotenv()

from VFRFunctionRoutes import VFRFunctionRoute, VFRPoint, VFRRouteState, MapManager #pylint: disable=wrong-import-position


sess = requests.Session()

rootpath = os.path.dirname(os.path.abspath(__file__))

rgen = VFRFunctionRoute(
    "LHFH--Lovasberény--Császár--Nyergesújfalu--LHFH",
    MapManager.instance().maps.get("HUNGARY", None),
    100,
    dof=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=2),
    session=sess,
    workfolder=os.path.join(rootpath, "data"),
    outfolder=os.path.join(rootpath, "output"),
    tracksfolder=os.path.join(rootpath, "data")
)

rgen.set_state(VFRRouteState.LEGS) # because we also want to add annotations

rgen.add_leg(
    'LHFH->Lovasberény',
    r'\sqrt[3]{{x}}',
    '$x=0$ at Lovasberény, $x=1.5$ at LHFH',
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
    r'\frac{1}{e^x}',
    r'$x=\pi$ at Lovasberény, $x=-\frac{\pi}{2}$ at Császár',
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
    r'\sin(x)',
    r'$x=0$ at Császár, $x=\pi$ at LHFH, $x=\frac{\pi}{2}$ at Nyergesújfalu',
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

rgen.set_state(VFRRouteState.ANNOTATIONS)

rgen.finalize()



#print(rgen)

#rgen.draw_map()
#rgen.fig.show()
#rgen.fig.waitforbuttonpress()

rgen.create_doc()

#rgen.save_plan()
