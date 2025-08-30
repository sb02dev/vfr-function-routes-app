# coding: utf-8
"""
Geometry classes for a VFR route defined by functions
"""
# general packages
from pathlib import Path
import traceback
from typing import Optional, Union, TYPE_CHECKING
import textwrap
from enum import Enum, auto
import datetime
import time
import os
import math
import json
from typing_extensions import Self

# projection related packages
import numpy as np

# pdf and imaging related packages
import matplotlib
matplotlib.use("Agg")
# pylint: disable=wrong-import-position
import matplotlib.axes

# gpx read and create
from lxml import etree # pylint: disable=no-name-in-module

# LaTeX evaluation related imports
from sympy.utilities.lambdify import lambdify
import sympy.abc

# package imports
from .projutils import (
    PointLonLat,
    ExtentLonLat,
    _calculate_2d_transformation_matrix,
    _apply_transformation_matrix,
    _rotate_point,
    _get_extent_from_points,
    parse_latex_with_constants
)
if TYPE_CHECKING:
    from .functionroute import VFRFunctionRoute
# pylint: enable=wrong-import-position


OPENWEATHER_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast" + \
                       "?lat={lat}&lon={lon}&appid={OPENWEATHER_APIKEY}"
MAGDEV_ENDPOINT = "https://www.ngdc.noaa.gov/geomag-web/calculators/calculateDeclination" + \
                  "?lat1={lat}&lon1={lon}" + \
                  "&startYear={when.year}&startMonth={when.month}&startDay={when.day}" + \
                  "&resultFormat=json&key={MAGDEV_APIKEY}"
OPENWEATHER_APIKEY = os.getenv("OPENWEATHER_APIKEY")
MAGDEV_APIKEY = os.getenv("MAGDEV_APIKEY")


class VFRRouteState(Enum):
    """A state enumeration of the states (essentially the steps on the
    frontend) the route can be in.
    """
    INITIATED = auto()
    AREAOFINTEREST = auto()
    WAYPOINTS = auto()
    LEGS = auto()
    ANNOTATIONS = auto()
    FINALIZED = auto()


class VFRCoordSystem(Enum):
    """The coordinate systems the app uses all the way from the functions
    to the lon-lat world coordinates.
    """
    FUNCTION = auto()
    MAPCROP_XY = auto()
    MAP_XY = auto()
    FULL_WORLD_XY = auto()
    LONLAT = auto()


class VFRPoint:
    """
    A Point object which knows its coordinate system and coordinates.
    Holds neccessary references to be able to transform from one system to another.
    """
    def __init__(self,
                 x: float, y: float,
                 coord_system: Optional[VFRCoordSystem] = VFRCoordSystem.LONLAT,
                 route: Optional["VFRFunctionRoute"] = None,
                 leg: Optional["VFRLeg"] = None):
        """
        Initialize the point
        Args
            coord_system: VFRCoordSystem
                The coordinate system this points coordinates are in
            x: float
                The horizontal coordinate or longitude (if it is a global point)
            y: float
                The vertical coordinate or latitude (if it is a global point)
        """
        self.coord_system = coord_system
        self.x, self.y = x, y
        self.route = route
        self.leg = leg

    @property
    def lon(self):
        """Convenience property: the longitude of the point
        (if it is a lon-lat pointi.e. in VFRCoordSystem.LONLAT)"""
        return self.x

    @property
    def lat(self):
        """Convenience property: the latitude of the point
        (if it is a lon-lat pointi.e. in VFRCoordSystem.LONLAT)"""
        return self.y

    def to_dict(self):
        """
        Converts this object to a JSON serializable dictionary.
        WARNING: References to `route` and `leg` are NOT preserved!
        """
        return {
            'x': self.x,
            'y': self.y,
            'coord_system': self.coord_system.name
        }


    @classmethod
    def from_dict(cls, value,
                 route: Union['VFRFunctionRoute', None] = None,
                 leg: Union['VFRLeg', None] = None):
        """
        Converts a dictionary from dict into a VFRPoint.
        WARNING: since references were not saved they can be passed to
        this method.
        """
        return VFRPoint(value['x'], value['y'], VFRCoordSystem[value['coord_system']], route, leg)


    def project_point(self, to_system: VFRCoordSystem) -> "VFRPoint":
        """
        Project this point to another coordinate system.
        It uses the parameters in the referenced route and leg (if neccessary)
        """
        if (not self.leg) and VFRCoordSystem.FUNCTION in [self.coord_system, to_system]:
            raise ValueError("There is no leg reference defined and" + \
                             " you tried to convert to/from function coordinate system.")
        if self.coord_system==to_system:
            return self
        curx, cury, cursys = self.x, self.y, self.coord_system
        if self.coord_system.value > to_system.value:
            if cursys == VFRCoordSystem.LONLAT and cursys.value > to_system.value:
                (curx, cury), cursys = self.route.proj(curx, cury), VFRCoordSystem.FULL_WORLD_XY
            if cursys == VFRCoordSystem.FULL_WORLD_XY and cursys.value > to_system.value:
                (curx, cury), cursys = \
                    _apply_transformation_matrix((curx, cury), self.route.matrix_fullmap2map), \
                    VFRCoordSystem.MAP_XY
            if cursys == VFRCoordSystem.MAP_XY and cursys.value > to_system.value:
                (curx, cury), cursys = \
                    _apply_transformation_matrix((curx, cury), self.route.matrix_map2cropmap), \
                    VFRCoordSystem.MAPCROP_XY
            if cursys == VFRCoordSystem.MAPCROP_XY and cursys.value > to_system.value:
                (curx, cury), cursys = \
                    _apply_transformation_matrix((curx, cury), self.leg.matrix_cropmap2func), \
                    VFRCoordSystem.FUNCTION
            return VFRPoint(curx, cury, cursys, self.route, self)

        if cursys == VFRCoordSystem.FUNCTION and cursys.value < to_system.value:
            (curx, cury), cursys = \
                _apply_transformation_matrix((curx, cury), self.leg.matrix_func2cropmap), \
                VFRCoordSystem.MAPCROP_XY
        if cursys == VFRCoordSystem.MAPCROP_XY and cursys.value < to_system.value:
            (curx, cury), cursys = \
                _apply_transformation_matrix((curx, cury), self.route.matrix_cropmap2map), \
                VFRCoordSystem.MAP_XY
        if cursys == VFRCoordSystem.MAP_XY and cursys.value < to_system.value:
            (curx, cury), cursys = \
                _apply_transformation_matrix((curx, cury), self.route.matrix_map2fullmap), \
                VFRCoordSystem.FULL_WORLD_XY
        if cursys == VFRCoordSystem.FULL_WORLD_XY and cursys.value < to_system.value:
            (curx, cury), cursys = \
                self.route.proj(curx, cury, inverse=True), \
                VFRCoordSystem.LONLAT
        return VFRPoint(curx, cury, cursys, self.route, self)



class VFRAnnotation:
    """The annotation bubbles the app puts on the map. It defines at which function x
    value it should point to and at what offset from there the bubble should appear.
    """

    ALWAYS_USE_REAL_WEATHER = os.getenv('ALWAYS_USE_REAL_WEATHER', "True") \
        .lower() in ["true", "yes", "on", "1"]
    BACKGROUND_COLOR = (1.0, 0.7, 0.7, 0.99)

    def __init__(self,
                 leg: "VFRLeg",
                 name: str,
                 x: float,
                 ofs: tuple[float, float]):
        """
        """
        self._leg: VFRLeg = leg
        self.name = name
        self.x = x
        self.ofs = ofs
        self._seglen = None
        self._seglens = None
        self._segtime = None
        self._times_withwind = None
        self._weather = None
        self._headings = None
        self._declination = None


    def clear_cache(self):
        """Clear the cache of cached items (they are cached because they are
        coming from the slow internet).
        """
        self._seglen = None
        self._seglens = None
        self._segtime = None
        self._times_withwind = None
        self._weather = None
        self._headings = None
        self._declination = None


    def __repr__(self):
        """The string representation of an Annotation object."""
        return f"{type(self).__name__}({self.name}, {self.x})"


    def to_dict(self):
        """Convert to a serializable dictionary."""
        return {
            'name': self.name,
            'x': self.x,
            'ofs': self.ofs
        }

    @classmethod
    def from_dict(cls, value, leg: 'VFRLeg'):
        """Initialize from a serializable dictionary."""
        return VFRAnnotation(leg, value['name'], value['x'], value['ofs'])


    @property
    def seglen(self):
        """Calculates and returns the length of the segment between this and the
        previous annotation. It returns the length in kilometers.
        """
        if self._seglen:
            return self._seglen
        x0, x1 = self._leg.ann_start_end(self)
        # calc segment points
        x = np.linspace(x0, x1, 100)
        psrc = [VFRPoint(x,
                         self._leg.function(x),
                         VFRCoordSystem.FUNCTION, self._leg.route, self._leg)
                for x in x]
        ps = [p.project_point(VFRCoordSystem.LONLAT) for p in psrc]
        # calc segment length
        self._seglen = self._leg.route.geod.line_length([p.lon for p in ps], [p.lat for p in ps])
        return self._seglen


    @property
    def seglens(self):
        """Calculates and returns the lengths of the 1/100th partition of
        the segment between this and the previous annotation. It returns
        the lengths in kilometers.
        """
        if self._seglens:
            return self._seglens
        x0, x1 = self._leg.ann_start_end(self)
        # calc segment points
        x = np.linspace(x0, x1, 100)
        psrc = [VFRPoint(x,
                         self._leg.function(x),
                         VFRCoordSystem.FUNCTION, self._leg.route, self._leg)
                for x in x]
        ps = [p.project_point(VFRCoordSystem.LONLAT) for p in psrc]
        # calc segment length
        self._seglens = self._leg.route.geod.line_lengths([p.lon for p in ps], [p.lat for p in ps])
        return self._seglens


    @property
    def segtime(self):
        """Calculates the time for the segment between this and the
        previous annotation.
        """
        if self._segtime:
            return self._segtime
        seglen = self.seglen
        self._segtime = seglen/1852/self._leg.route.speed*60 if seglen else None
        return self._segtime


    @property
    def times_withwind(self):
        """Calculates the time for the segment between this and the
        previous annotation but it is adjusted for wind effects
        """
        if self._times_withwind:
            return self._times_withwind
        headings = [h if h>=0 else h+360 for h in self.headings]
        wind_corrections = self.wind_corrections()
        speeds_withwind = [(self._leg.route.speed*math.cos(
                                math.radians(-1*wind_corrections[i]))) + \
                           (self.wind_speed*math.cos(
                               math.radians(headings[i]+wind_corrections[i]-
                                            self.wind_dir+180)))
                           for i in range(len(headings))]
                          #(speed*COS(RADIÁN(-wind_correction)))+
                          #     (wind_speed*
                          #     COS(RADIÁN(heading+wind_correction-wind_direction+180)))
        self._times_withwind = [self.seglens[i]/1852/speeds_withwind[i]*60
                                for i in range(len(self.seglens))]
        return self._times_withwind



    @property
    def headings(self) -> list[float]:
        """Returns a list of headings of 100 points of the segment from previous annotiation
        to this one."""
        if self._headings:
            return self._headings
        x0, x1 = self._leg.ann_start_end(self)
        x = np.linspace(x0, x1, 100)
        psrc = [VFRPoint(x,
                         self._leg.function(x),
                         VFRCoordSystem.FUNCTION, self._leg.route, self._leg)
                for x in x]
        ps = [p.project_point(VFRCoordSystem.LONLAT) for p in psrc]
        lat = [p.lat for p in ps]
        lon = [p.lon for p in ps]
        headings, _, _ = self._leg.route.geod.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
        def clamp(deg):
            while deg>360:
                deg-=360
            while deg<0:
                deg+=360
            return deg
        headings = [clamp(h) for h in headings]
        self._headings = headings
        return self._headings


    def get_weather(self):
        """Downloads and caches the weather forecast. Gets either a sample weather
        forecast (for quick editing) or real one from OpenWeather"""
        # only download once
        if not self._weather:
            # download weather at from point
            if self.ALWAYS_USE_REAL_WEATHER or \
                    self._leg.route.use_realtime_data:
                        # either forced by settings or requested by user (situation)
                p = VFRPoint(self.x,
                             self._leg.function(self.x),
                             VFRCoordSystem.FUNCTION, self._leg.route, self._leg)
                p = p.project_point(VFRCoordSystem.LONLAT)
                response = self._leg.route.session.get(OPENWEATHER_ENDPOINT.format(
                    lon=p.lon,
                    lat=p.lat,
                    OPENWEATHER_APIKEY=OPENWEATHER_APIKEY
                ))
                self._weather = response.json()
            else:
                with open(os.path.join(Path(__file__).parent,
                                       'sample_weather.json'),
                          'rt',
                          encoding='utf8') as f:
                    self._weather = json.load(f)


    def magnetic_deviation(self, when=datetime.datetime.now()):
        """Downloads and caches the magnetic deviation for the annotation
        point. Gets either a fix value (for quick route editing) or real one
        from www.ngdc.noaa.gov"""
        if self._declination:
            return self._declination
        try:
            if self.ALWAYS_USE_REAL_WEATHER or \
                    self._leg.route.use_realtime_data:
                    # either forced by settings or requested by user (situation)
                p = VFRPoint(self.x,
                             self._leg.function(self.x),
                             VFRCoordSystem.FUNCTION, self._leg.route, self._leg)
                p = p.project_point(VFRCoordSystem.LONLAT)
                api_res = self._leg.route.session.get(MAGDEV_ENDPOINT.format(
                    lon = p.lon,
                    lat = p.lat,
                    MAGDEV_APIKEY = MAGDEV_APIKEY,
                    when = when
                ))
                api_res = api_res.json()
                self._declination = api_res["result"][0]["declination"]
            else:
                self._declination = 6
        except Exception:  # pylint: disable=broad-exception-caught
            traceback.print_exc()
            self._declination = 5
        return self._declination


    @property
    def wind(self):
        """Based on the weather forecast returns the wind forecast at this
        annotation point at the time of flight."""
        self.get_weather()
        weather_ts = int(self._leg.route.dof.timestamp())
        latest = sorted((wfx
                         for wfx in self._weather['list']
                         if wfx['dt']<=weather_ts),
                        key=lambda wfx: wfx['dt'])
        if len(latest)<1:
            raise ValueError(
                "No wind forecast is available for that date/time" + \
                f" ({self._leg.route.dof.isoformat()})"
            )
        return latest[-1]['wind']


    @property
    def wind_speed(self) -> float:
        """Gets the speed of the forecasted wind at the annotation point."""
        return self.wind['speed']*3600/1852


    @property
    def wind_dir(self) -> float:
        """Gets the direction of the forecasted wind at the annotation point."""
        return self.wind['deg']


    def wind_corrections(self,
                         speed: Optional[float] = None,
                         headings: Optional[list[float]] = None
                        ) -> list[float]:
        """Gets the Wind Correction Angle for the list of headings given in argument
        or calculated for 100 pointsbetween this and the previous annotation point."""
        if not speed:
            speed = self._leg.route.speed
        if not headings:
            headings = self.headings
        return [math.degrees(
                    math.asin(self.wind_speed/self._leg.route.speed*
                              math.sin(math.radians(h-self.wind_dir+180))))
                for h in headings]
               #FOK(ARCSIN(wind_speed/speed*SIN(RADIÁN(heading-wind_direction+180))))



    def draw(self, ax: matplotlib.axes.Axes):
        """Draws the annotation bubble on a MatPlotLib Figure."""
        start = time.perf_counter_ns()
        xy = VFRPoint(self.x,
                      self._leg.function(self.x),
                      VFRCoordSystem.FUNCTION, self._leg.route, self._leg) \
                      .project_point(VFRCoordSystem.MAPCROP_XY)
        seglen = self.seglen
        segtime = self.segtime
        segtime_wind = sum(self.times_withwind)
        seghdgs = self.headings
        wind_corrs = self.wind_corrections(headings=seghdgs)
        wind_corr = wind_corrs[-1] if wind_corrs else None
        mag_dev = self.magnetic_deviation(self._leg.route.dof)
        s_seglen = f"\ndist: {seglen/1852:.1f}NM\ntime: {math.floor(segtime):3d}:" + \
                   f"{math.floor((segtime-math.floor(segtime))*60):02d}" + \
                   f" / {math.floor(segtime_wind):3d}:" + \
                   f"{math.floor((segtime_wind-math.floor(segtime_wind))*60):02d}"
        if self._leg.annotations.index(self) == 0:
            s_seglen = ""
        calc_time = time.perf_counter_ns() - start

        ann = ax.annotate( # pylint: disable=unused-variable
            f'{self.name}\ntrack: ${self.headings[-1]:.0f}\\degree${mag_dev:+.0f}(M)' + \
            f'{wind_corr:+.0f}(W:{self.wind_speed:.0f}/{self.wind_dir:.0f}){s_seglen}',
            xy=(xy.x, xy.y), xycoords='data',
            xytext=(self.ofs[0], self.ofs[1]), textcoords='offset points',
            size=5.5, va="center",
            bbox={"boxstyle": "round", "fc": self.BACKGROUND_COLOR, "ec": "none"},
            arrowprops={ "arrowstyle": "wedge,tail_width=1.",
                         "fc": self.BACKGROUND_COLOR,
                         "ec": "none",
                         "patchA": None,
                         "patchB": None,
                         "relpos": (0.2, 0.5)
                       }
            )

        return calc_time


class VFRLeg:
    """A class representing a Leg of the Route. It defines the starting and ending point
    of the Leg (lon-lat), the function (like `sin(x)`) the Leg must follow, and optional
    constraint point(s) to adjust the curve of the Leg slightly.
    """

    def __init__(self,  # pylint: disable=too-many-arguments,disable=too-many-positional-arguments
                 route: "VFRFunctionRoute",
                 name: str,
                 function_name: str,
                 function_range: str,
                 points: list[tuple[VFRPoint, float]]):
        """
        """
        self._route: "VFRFunctionRoute" = route
        self.name = name
        self.function_name = function_name
        self.calc_function()
        self.function_range = function_range
        self.points = points
        for p, _ in self.points:
            p.leg = self
        self.annotations: list[VFRAnnotation] = []

        self._matrix_func2cropmap = None
        self._matrix_cropmap2func = None

        self.color="red"
        self.lw=2


    def add_annotation(self, name: str, x: float, ofs: tuple[float, float]) -> Self:
        """Initializes and adds an annotation bubble to this curved
        Leg of the Route.
        """
        self._route.ensure_state(VFRRouteState.LEGS)
        newannotation = VFRAnnotation(self, name, x, ofs)
        self.annotations.append(newannotation)
        return self


    @property
    def route(self):
        """A read-only accessor to the parent route"""
        return self._route

    @property
    def matrix_cropmap2func(self):
        """A read-only accessor to the inverse transformation matrix"""
        return self._matrix_cropmap2func

    @property
    def matrix_func2cropmap(self):
        """A read-only accessor to the transformation matrix"""
        return self._matrix_func2cropmap


    def get_extent(self) -> ExtentLonLat:
        """Get the extent of the Leg in terms of min-(lon-lat)/max-(lon-lat)
        taking into consideration the curvature of the function."""
        x = np.linspace(min(x for p, x in self.points),
                        max(x for p, x in self.points),
                        100
                       )
        if not hasattr(self, '_matrix_cropmap2func') or self._matrix_cropmap2func is None:
            self.calc_transformations()
        if not self.function:
            self.calc_function()
        psrc = [VFRPoint(x,
                         self.function(x),
                         VFRCoordSystem.FUNCTION, self._route, self)
                for x in x]
        ps = [p.project_point(VFRCoordSystem.LONLAT) for p in psrc]
        pll = [PointLonLat(p.lon, p.lat) for p in ps] + \
              [PointLonLat(p.lon, p.lat) for p, x in self.points]
        return _get_extent_from_points(pll)


    def draw(self, ax, with_annotations: bool = True):
        """Draw the leg on a MatPlotLib Figure considering the function curvature,
        the projection of the points from lon-lat to map coordinates and transforming
        the function into map coordinates.
        
        Args
            ax
                A MatPlotLib Axes object to draw on
            with_annotations: bool
                Wether to also draw the annotation bubbles (defaults to True)
        """
        # draw planned track
        x = np.linspace(min(x for p, x in self.points),
                        max(x for p, x in self.points),
                        100
                       )
        if not hasattr(self, '_matrix_cropmap2func') or self._matrix_cropmap2func is None:
            self.calc_transformations()
        if not self.function:
            self.calc_function()
        psrc = [VFRPoint(x,
                         self.function(x),
                         VFRCoordSystem.FUNCTION, self._route, self)
                for x in x]
        ps = [p.project_point(VFRCoordSystem.MAPCROP_XY) for p in psrc]
        ax.plot([p.x for p in ps],
                [p.y for p in ps],
                color=self.color,
                lw=self.lw
               )
        # draw annotations
        calc_time = 0
        if with_annotations:
            for a in self.annotations:
                calc_time += a.draw(ax)

        return calc_time


    def calc_function(self):
        """Converts a LaTeX string (user input) into a Python lambda
        function (calculation basis).
        On conversion error it falls back to the identity function."""
        try:
            parsedfun = parse_latex_with_constants(self.function_name) # parse_latex(latex)
            self.function = lambdify(sympy.abc.x, parsedfun, modules=["math"])
        except Exception:  # pylint: disable=broad-exception-caught
            self.function = lambda x: x # fallback to linear


    def calc_transformations(self):
        """Calculate the transformation matrix from function coordinate
        system to the cropped map coordinate system. It respects the optional
        constraint points. Gives a best approximation.
        """
        self.calc_function()
        sp = [(x, self.function(x)) for (p, x) in self.points]
        dpp = [p.project_point(VFRCoordSystem.MAPCROP_XY) for p, x in self.points]
        dp = [(p.x, p.y) for p in dpp]
        if len(sp) < 3:
            sp.append(_rotate_point(sp[0], sp[1], -90))
            dp.append(_rotate_point(dp[0], dp[1], 90))
        try:
            self._matrix_func2cropmap = _calculate_2d_transformation_matrix(sp, dp)
            self._matrix_cropmap2func = np.linalg.inv(self._matrix_func2cropmap)
        except Exception: # pylint: disable=broad-exception-caught
            pass # keep the old matrix


    def ann_start_end(self, ann: VFRAnnotation) -> float:
        """Returns the function-x value of the given and the previous
        annotation. If this is the first annotation point, it gives an
        x value adjusted from current annotation's in the correct direction
        by a small amount (good for the heading calculations).
        """
        # calc start and end x
        i = self.annotations.index(ann)
        x1 = self.annotations[i].x
        if i > 0:
            x0 = self.annotations[i-1].x
        else:
            dirmul = -1.0 if self.annotations[i].x < self.annotations[i+1].x else 1.0
            x0 = x1 + dirmul*0.00001
        return x0, x1


    def to_dict(self):
        """Convert the Leg to a serializable dictionary."""
        return {
            'name': self.name,
            'function_name': self.function_name,
            'function_range': self.function_range,
            'points': [{'p': p.to_dict(), 'x': x} for p, x in self.points]
        }

    @classmethod
    def from_dict(cls, value, route: Union['VFRFunctionRoute', None]):
        """Initialize the Leg from a serializable dictionary."""
        return VFRLeg(route,
                      value['name'],
                      value['function_name'],
                      value['function_range'],
                      [(VFRPoint.from_dict(pdef['p'], route), pdef['x'])
                       for pdef in value['points']])

    def __repr__(self):
        """String representation of the Leg."""
        s = f"{type(self).__name__}({self.name}, {self.function_name})\n"
        for a in self.annotations:
            s += textwrap.indent(repr(a), "  ")+"\n"
        return s


class VFRTrack:
    """A class representing a Track on the Route (i.e. an actually flown path).
    It is initialized from a .GPX file or a GPX string, defines the color with
    which it will be drawn onto the map.
    """

    def __init__(self,
                 route: "VFRFunctionRoute",
                 fname: Union[str, Path],
                 color: str,
                 xmlb: Optional[bytes] = None,
                 load: bool = True
                ):
        self._route = route
        self.fname = fname
        self.color = color
        self.points: list[VFRPoint] = []
        if load:
            self.points=self.read_gpx(fname=fname, xmlb=xmlb)

    def read_gpx(self,
                 fname: Union[str, Path] = None,
                 xmlb: Optional[bytes] = None
                ) -> list[VFRPoint]:
        """Reads flown points from a GPX file / GPX string"""
        if xmlb:
            plangpx = etree.fromstring(xmlb)
        else:
            plangpx = etree.parse(fname)
        ns = {"gpx": "http://www.topografix.com/GPX/1/1",
              "geotracker": "http://ilyabogdanovich.com/gpx/extensions/geotracker"}
        planptx = plangpx.xpath("/gpx:gpx/gpx:trk/gpx:trkseg/gpx:trkpt", namespaces=ns)
        planpts: list[VFRPoint] = []
        for _, ptx in enumerate(planptx):
            lon = float(ptx.get('lon'))
            lat = float(ptx.get('lat'))
            planpts.append(
                VFRPoint(lon, lat, VFRCoordSystem.LONLAT, self._route)
            )
        return planpts

    def draw(self, ax: matplotlib.axes.Axes):
        """Draw track on a MatPlotLib Figure"""
        ps = [p.project_point(VFRCoordSystem.MAPCROP_XY) for p in self.points]
        ax.plot([p.x for p in ps],
                [p.y for p in ps],
                color=self.color,
                lw=2
               )

    def to_dict(self):
        """Convert the object to a serializable dictionary"""
        return {
            'name': self.fname,
            'color': self.color,
            'points': [p.to_dict() for p in self.points]
        }

    @classmethod
    def from_dict(cls, value, route: 'VFRFunctionRoute'):
        """Initialize the object from a serializable dictionary"""
        trk = VFRTrack(route, value['name'], value['color'], load=False)
        trk.points = [VFRPoint.from_dict(p, route) for p in value['points']]
        return trk

    def get_extent(self):
        """Get the extent of the track by enumerating its points"""
        return _get_extent_from_points([PointLonLat(p.lon, p.lat) for p in self.points])
