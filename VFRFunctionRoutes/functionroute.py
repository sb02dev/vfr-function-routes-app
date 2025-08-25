# coding: utf-8
"""
Calculates VFR routes where the legs are defined as a function
"""
# general packages
import json
from pathlib import Path
from typing import Optional, Union
import textwrap
import datetime
import os
import io
import math

import requests

# projection related packages
from pyproj import Proj, Geod
import numpy as np

# pdf and imaging related packages
import PIL
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# document creation related packages
from docx import Document
from docx.shared import Cm

# gpx read and create
import gpxpy

# package imports
from .projutils import (
    PointLonLat, PointXY,
    ExtentLonLat, ExtentXY,
    _calculate_2d_transformation_matrix,
    _apply_transformation_matrix,
    _get_extent_from_points,
    _get_extent_from_extents,
)
from .docxutils import add_formula_par
from .rendering import SimpleRect
from .maps import MapDefinition, MapManager
from .geometry import VFRRouteState, VFRLeg, VFRTrack, VFRPoint, VFRCoordSystem, VFRAnnotation


class VFRFunctionRoute:
    """
    A class that can be used to
      - gradually build up a route
      - add flight tracks
      - generate a map of the route and tracks
      - generate a flight plan document
      - generate a flight plan file for SkyDaemon
    """
    
    HIGH_DPI = int(os.getenv("HIGH_DPI", "600"))
    LOW_DPI = int(os.getenv("LOW_DPI", "72"))
    DOC_DPI = int(os.getenv("DOC_DPI", "200"))


    @property
    def use_realtime_data(self):
        return self._use_realtime_data
    
    @use_realtime_data.setter
    def use_realtime_data(self, val):
        self._use_realtime_data = val
        for l in self.legs:
            for a in l.annotations:
                a._clear_cache()

    
    def __init__(self,
                 name: str,
                 mapdef: MapDefinition,
                 speed: float,
                 dof: datetime.datetime,
                 session: requests.Session = None,
                 workfolder: Union[str, Path, None] = None,
                 outfolder: Union[str, Path, None] = None,
                 tracksfolder: Union[str, Path, None] = None
                ):
        """
        """
        self._state = VFRRouteState.INITIATED
        self.name = name
        self.map = mapdef
        self.speed = speed
        self.dof = dof
        self.workfolder = workfolder
        self.outfolder = outfolder
        self.tracksfolder = tracksfolder
        self.legs: list[VFRLeg] = []
        self.tracks: list[VFRTrack] = []
        self._session = session if session else requests.Session()
        self.waypoints: list[tuple[str, VFRPoint]] = []
        self.area_of_interest = {
            'top-left': VFRPoint(self.map.area["top-left"].lon, self.map.area["top-left"].lat, VFRCoordSystem.LONLAT, self),
            'bottom-right': VFRPoint(self.map.area["bottom-right"].lon, self.map.area["bottom-right"].lat, VFRCoordSystem.LONLAT, self)
        }
        self._use_realtime_data = False
        self.calc_extents()
        self.calc_transformations()
        

    def _ensure_state(self, required_state: VFRRouteState, ensure_minimum: bool = True, ensure_exactly: bool = False):
        """
        Ensure the object is in the desired state. Otherwise raise an exception.

        Args
            required_state: VFRRouteState
                The state we compare to
            
            ensure_minimum: bool
                The direction we compare: if True we need to have at least
                the given state, if False we need to have at most the given
                state.

            ensure_exactly: bool
                We have to have exactly the given state (no more, no less).
        """
        if ensure_exactly:
            if self._state.value!=required_state.value:
                raise RuntimeError(f"VFRFunctionRoutes object not in required state: Current {self._state}, required exact state: {required_state}.")
        elif ensure_minimum:
            if self._state.value<required_state.value:
                raise RuntimeError(f"VFRFunctionRoutes object not in required state: Current {self._state}, required minimum state: {required_state}.")
        else:
            if self._state.value>required_state.value:
                raise RuntimeError(f"VFRFunctionRoutes object not in required state: Current {self._state}, required maximum state: {required_state}.")
        
    
    def set_state(self, required_state: VFRRouteState):
        if self._state==required_state:
            return
        if self._state.value<required_state.value: # forward stepping
            if self._state == VFRRouteState.INITIATED and required_state.value > self._state.value:
                # INITIADED -> AREAOFINTEREST
                self._state = VFRRouteState.AREAOFINTEREST
                self.calc_extents()
                self.calc_transformations()
            if self._state==VFRRouteState.AREAOFINTEREST and required_state.value>self._state.value:
                # AREAOFINTEREST -> WAYPOINTS
                self._state = VFRRouteState.WAYPOINTS
                self.waypoints_to_legs()
                self.calc_extents()
                self.calc_transformations()
            if self._state == VFRRouteState.WAYPOINTS and required_state.value > self._state.value:
                # WAYPOINTS -> LEGS
                self._state = VFRRouteState.LEGS
                self.legs_to_annotations()
                self.calc_extents()
                self.calc_transformations()
            if self._state == VFRRouteState.LEGS and required_state.value > self._state.value:
                # LEGS -> ANNOTATIONS
                self._state = VFRRouteState.ANNOTATIONS
            if self._state == VFRRouteState.ANNOTATIONS and required_state.value > self._state.value:
                # ANNOTATIONS -> FINALIZED
                self.finalize()
        else: # backward stepping
            # TODO: currently nothing is done (we could free up resources, etc)
            self._state = required_state


    def waypoints_to_legs(self):
        """
        Converts waypoints to legs considering the already existing ones
        """
        for i, wp_start in enumerate(self.waypoints):
            wp_end = self.waypoints[i+1 if i+1<len(self.waypoints) else 0] # circle around (last point is the same as first)
            if len(self.legs)>i: # we have a leg at that position
                leg = self.legs[i]
                # so we adjust its endpoints position (not the x value)
                leg.points[0] = (VFRPoint(wp_start[1].lon, wp_start[1].lat, VFRCoordSystem.LONLAT, self), leg.points[0][1])
                leg.points[-1] = (VFRPoint(wp_end[1].lon, wp_end[1].lat, VFRCoordSystem.LONLAT, self), leg.points[-1][1])
                # we adjust the name of the leg
                leg.name = f"{wp_start[0]} -- {wp_end[0]}"
                # we adjust the annotations so we have the first and last match
                if len(leg.annotations)>0:
                    leg.annotations[0].x = leg.points[0][1]
                else:
                    leg.add_annotation('???', leg.points[0][1], (0,0))
                if len(leg.annotations)>1:
                    leg.annotations[-1].x = leg.points[-1][1]
                else:
                    leg.add_annotation('???', leg.points[-1][1], (0,0))
            else: # we don't have a leg yet
                # so we add a new one
                func_range = f"x=0\\textrm{{ at {wp_start[0]}, }}x=1\\textrm{{ at {wp_end[0]}}}"
                self.add_leg(f"{wp_start[0]} -- {wp_end[0]}", f"x^{i+1}", func_range, lambda x: x**i,
                             [
                                 (VFRPoint(wp_start[1].lon, wp_start[1].lat, VFRCoordSystem.LONLAT, self), 0),
                                 (VFRPoint(wp_end[1].lon, wp_end[1].lat, VFRCoordSystem.LONLAT, self), 1)
                             ])


    def legs_to_annotations(self):
        """
        Transfers information from leg points to annotations (at least a start and an end is needed)
        """
        for leg in self.legs:
            if len(leg.annotations) > 0:
                leg.annotations[0].x = leg.points[0][1]
            else:
                leg.add_annotation('???', leg.points[0][1], (0, 0))
            if len(leg.annotations) > 1:
                leg.annotations[-1].x = leg.points[-1][1]
            else:
                leg.add_annotation('???', leg.points[-1][1], (0, 0))


    def finalize(self):
        self._ensure_state(VFRRouteState.ANNOTATIONS)
        self.calc_extents()
        self.calc_transformations()
        # TODO: obtain live data (from internet)
        self._state = VFRRouteState.FINALIZED
        

    def set_area_of_interest(self, top_left_x: float, top_left_y: float, bottom_right_x: float, bottom_right_y: float) -> None:
        self._ensure_state(VFRRouteState.INITIATED)
        self.area_of_interest = {
            'top-left': VFRPoint(top_left_x, top_left_y, VFRCoordSystem.MAP_XY, self).project_point(VFRCoordSystem.LONLAT),
            'bottom-right': VFRPoint(bottom_right_x, bottom_right_y, VFRCoordSystem.MAP_XY, self).project_point(VFRCoordSystem.LONLAT)
        }

    def set_area_of_interest_lonlat(self, top_left_lon: float, top_left_lat: float, bottom_right_lon: float, bottom_right_lat: float) -> None:
        self._ensure_state(VFRRouteState.INITIATED)
        self.area_of_interest = {
            'top-left': VFRPoint(top_left_lon, top_left_lat, VFRCoordSystem.LONLAT, self),
            'bottom-right': VFRPoint(bottom_right_lon, bottom_right_lat, VFRCoordSystem.LONLAT, self)
        }

    def _get_image_from_figure(self, fig, size: tuple[float, float] = None, dpi: float = None) -> bytes:
        buf = io.BytesIO()
        if size:
            figsize = fig.get_size_inches()
            dpi = min(size[0] / figsize[0], size[1] / figsize[1])
        fig.savefig(buf, format="png", dpi=dpi, transparent=True)
        buf.seek(0)
        return buf


    def draw_annotations(self):
        fig = plt.figure()
        ax = plt.Axes(fig, [0., 0., 1., 1.])
        ax.set_axis_off()
        fig.add_axes(ax)

        calc_time = 0
        for l in self.legs:
            calc_time += l.draw(ax, True)

        print(f'calculation time: {calc_time:15,d}')
        
        return fig


    def draw_tracks(self):
        fig = plt.figure()
        ax = plt.Axes(fig, [0., 0., 1., 1.])
        ax.set_axis_off()
        fig.add_axes(ax)

        for l in self.legs:
            l.draw(ax, False)
        for t in self.tracks:
            t.draw(ax)

        return fig


    def add_waypoint(self, name: str, point: VFRPoint):
        point.route = self
        self.waypoints.append((name, point.project_point(VFRCoordSystem.LONLAT)))


    def update_waypoints(self, wps: list[dict]):
        # calculate new waypoints
        self.waypoints = [(wp["name"], VFRPoint(wp["x"], wp["y"], VFRCoordSystem.MAPCROP_XY, self).project_point(VFRCoordSystem.LONLAT)) for wp in wps]


    def update_legs(self, legs: list[dict]):
        # set legs according to edits
        for i, leg in enumerate(legs):
            curleg = self.legs[i]
            # setup general
            curleg.name = leg["name"]
            # setup function
            curleg.function_range = leg["function_range"]
            latex = leg["function_name"]
            curleg.function_name = latex
            curleg.calc_function()
            # setup constraint points
            lp_start, lp_end = curleg.points[0], curleg.points[-1]
            newpoints: list[tuple[VFRPoint, float]] = []
            for j, pt in enumerate(leg["points"]):
                if j==0:
                    newpoints.append((lp_start[0], pt["func_x"]))
                elif j==len(leg["points"])-1:
                    newpoints.append((lp_end[0], pt["func_x"]))
                else:
                    newpoints.append((
                        VFRPoint(pt["x"], pt["y"], VFRCoordSystem.MAPCROP_XY, self, curleg).project_point(VFRCoordSystem.LONLAT),
                        pt["func_x"]
                    ))
            curleg.points = newpoints
            # recalculate
            curleg.calc_transformations()


    def update_annotations(self, legs: list[dict]):
        for i, l in enumerate(legs):
            if i>len(self.legs)-1:
                break
            if self.legs[i].name!=l['name']:
                print(f"WARNING: leg number {i} name does not match ({self.legs[i].name}!={l['name']})")
            self.legs[i].annotations = [VFRAnnotation(self.legs[i],
                                                      a['name'],
                                                      a['func_x'],
                                                      (a['ofs']['x'], a['ofs']['y']))
                                        for a in l['annotations']
                                       ]


    def add_leg(self, 
                name: str,
                function_name: str,
                function_range: str,
                function,
                points: list[tuple[VFRPoint, float]]) -> VFRLeg:
        """
        """
        self._ensure_state(VFRRouteState.WAYPOINTS)
        for p, x in points:
            p.route = self
        newleg = VFRLeg(self, name, function_name, function_range, function, points)
        self.legs.append(newleg)
        return newleg
        
    def add_track(self,
                  fname: Union[str, Path],
                  color: str,
                  xmlb: Optional[bytes] = None):
        """Adds a flown track to show on the map.
        
        Args:
            fname: str
                The filename of the track (it will be looked for in the trackfolders folder
                if xmlstring is not given)
            color: str
        """
        self._ensure_state(VFRRouteState.ANNOTATIONS)
        self.tracks.append(VFRTrack(self, fname, color, xmlb=xmlb))
        return self
    

    def update_tracks(self, tracks):
        newtracks: list[VFRTrack] = []
        for t in self.tracks:
            if t.fname in [nt['name'] for nt in tracks]:
                newtracks.append(t)
                t.color = [nt['color'] for nt in tracks if nt['name']==t.fname][0]
        self.tracks = newtracks
        
        
    def calc_transformations(self):
        """Calculates and saves the transformations between coordinate systems.
        
        The following coordinate systems are neccessary:
            1. the function coordinate system
            2. cropped map image coordinates
            3. the map image coordinate system
            4. full-world x-y coordinates
            5. the latitude-longitude coordinates on the earth
            
        It is neccessary to transform between those coordinate systems:
            - 1->2 to draw the route on the image
            - 1->5 to save the route to a flightplan
            - 5->2 to draw tracks on the map image
        Problem:
            2 through 5 is map dependent
            1 is function (leg) dependent
        """
        # to consider:
        #   map false_easting, false_northing values calc/hardcoded
        #   map scale
        # calculate transformations for LONLAT<->FULL_WORLD_XY
        self._proj_str = "+proj=lcc +lon_0=-90 +lat_1=46 +lat_2=48 +ellps=WGS84"
        self._proj = Proj(self._proj_str)
        self._geod = Geod(self._proj_str)
        #print(self._proj(16,48.5))
        #print(self._proj(17,47.5))
        # calculate transformations for FULL_WORLD_XY<->MAP_XY
        p = [self._proj(ll.lon, ll.lat) for ll in self.map.points.keys()] # convert to fullworld map coord
        pp = [PointXY(pxy.x/72*self.LOW_DPI, pxy.y/72*self.LOW_DPI) for pxy in self.map.points.values()] # must scale it to LOW_DPI from default pdf metric of 72
        self._matrix_fullmap2map = _calculate_2d_transformation_matrix(p, pp) # calc matrix from fullworld map coord to map coord
        self._matrix_map2fullmap = np.linalg.inv(self._matrix_fullmap2map)
        #print("TEST lonlat to mapxy:")
        #for i, (lonlat, xy) in enumerate(self.PDF_IN_WORLD_XY.items()):
        #    print(f"  {lonlat} -> {p[i]} -> {xy} vs {_apply_transformation_matrix(p[i], self._matrix_fullmap2map)}")
        # calculate transformations for MAP_XY<->MAPCROP_XY
        p = self.get_mapxyextent()
        pp = [
            (0, 0),
            (0, (p.maxy-p.miny)*self.HIGH_DPI/self.LOW_DPI),
            ((p.maxx-p.minx)*self.HIGH_DPI/self.LOW_DPI, 0),
            ((p.maxx-p.minx)*self.HIGH_DPI/self.LOW_DPI, (p.maxy-p.miny)*self.HIGH_DPI/self.LOW_DPI),
        ]  # also scale it up!
        p = [
            (p.minx, p.miny),
            (p.minx, p.maxy),
            (p.maxx, p.miny),
            (p.maxx, p.maxy),
        ]
        self._matrix_map2cropmap = _calculate_2d_transformation_matrix(p, pp)
        self._matrix_cropmap2map = np.linalg.inv(self._matrix_map2cropmap)
        #print("TEST mapxy to cropmapxy:")
        #for i, (mapxy, cropmapxy) in enumerate(zip(p, pp)):
        #    print(f"  {mapxy} -> {cropmapxy} vs {_apply_transformation_matrix(mapxy, self._matrix_map2cropmap)}")
        # calculate transformations for each leg
        for leg in self.legs:
            leg.calc_transformations()
        
        
    def calc_extents(self, margin_x: float = .2, margin_y: Optional[float] = None):
        """Calculates and saves the extents of the neccessary map.
        
        Calculates the top-left and bottom-right coordinates of the map
        that will contain all points of the route. It also adds a margin
        in both directions given in the parameters as a percentage.

        If there are no legs nor tracks, than it defaults to an area around Budapest.
        
        Args:
            margin_x:
                Horizontal additional margin. Given in percentage of the
                distance of minimum and maximum lateral coordinates.
                Default is 10%
            margin_y:
                Optional vertical margin. Given in percentage of the
                distance of minimum and maximum longitudinal coordinates.
                Default is equal to horizontal margin.
        """
        lat0, lat1, lon0, lon1 = (self.area_of_interest["top-left"].lat,
                                    self.area_of_interest["bottom-right"].lat,
                                    self.area_of_interest["top-left"].lon,
                                    self.area_of_interest["bottom-right"].lon)
        AOI = ExtentLonLat(
            min(lon0, lon1),
            min(lat0, lat1),
            max(lon0, lon1),
            max(lat0, lat1)
        )
        if self._state in [VFRRouteState.INITIATED, VFRRouteState.AREAOFINTEREST, VFRRouteState.WAYPOINTS]:
            # at this stage we only have area of interest (which is always set, at least to a default)
            self.extent = AOI
        elif self._state in [VFRRouteState.LEGS, VFRRouteState.ANNOTATIONS, VFRRouteState.FINALIZED]:
            # get the automatic bounding box
            if len(self.legs)==0 and len(self.tracks)==0:
                # no legs, no tracks fall back to waypoints extent
                if len(self.waypoints)==0:
                    self.extent = AOI
                    return
                else:
                    extent = _get_extent_from_points([PointLonLat(p.lon, p.lat) for name, p in self.waypoints])
            else:
                # we have at least one leg or track, use those (leg points contain waypoints)
                extent = _get_extent_from_extents(
                        [l.get_extent() for l in self.legs] +
                        [t.get_extent() for t in self.tracks]
                    )
            # add margins
            if margin_y is None:
                margin_y = margin_x
            extent_with_margins = ExtentLonLat(
                    extent.minlon - (extent.maxlon-extent.minlon)*margin_x,
                    extent.minlat - (extent.maxlat-extent.minlat)*margin_y,
                    extent.maxlon + (extent.maxlon-extent.minlon)*margin_x,
                    extent.maxlat + (extent.maxlat-extent.minlat)*margin_y
                )
            # get the bounding box of the automatic and the manually defined
            # (i.e. only increase manually given box)
            extent_or_aoi = ExtentLonLat(
                min(extent_with_margins.minlon, AOI.minlon),
                min(extent_with_margins.minlat, AOI.minlat),
                max(extent_with_margins.maxlon, AOI.maxlon),
                max(extent_with_margins.maxlat, AOI.maxlat)
            )
            self.extent = extent_or_aoi


    def get_mapxyextent(self) -> ExtentXY:
        p = [
            PointLonLat(self.extent.minlon, self.extent.minlat), # minlon-minlat -> leftbottom
            PointLonLat(self.extent.minlon, self.extent.maxlat), # minlon-maxlat -> lefttop
            PointLonLat(self.extent.maxlon, self.extent.minlat), # maxlon-minlat -> rightbottom
            PointLonLat(self.extent.maxlon, self.extent.maxlat), # maxlon-maxlat -> righttop
        ]
        p = [self._proj(ll.lon, ll.lat) for ll in p] # projected to FULL_WORLD_XY
        p = [_apply_transformation_matrix(pp, self._matrix_fullmap2map) for pp in p] # projected to MAP_XY (LOW_DPI)
        p = [PointXY(pp[0], pp[1]) for pp in p]
        return ExtentXY(
            min(pp.x for pp in p),
            min(pp.y for pp in p),
            max(pp.x for pp in p),
            max(pp.y for pp in p)
        )


    def draw_map(self, use_realtime: Optional[bool] = None):
        """Draws a matplotlib based map of the defined route.
        
        Args:
        
        Returns:
            The matplotlib axes of the final plot.
        """
        self._ensure_state(VFRRouteState.FINALIZED)

        setRTD, oldRTD = False, self.use_realtime_data
        if use_realtime is not None:
            if use_realtime!=self.use_realtime_data:
                oldRTD, self.use_realtime_data, setRTD = self.use_realtime_data, True, True

        try:
            # draw background
            bg_img = self.calc_basemap()
            
            # initialize map
            fig = plt.figure()
            ax = plt.Axes(fig, [0., 0., 1., 1.])
            ax.set_axis_off()
            fig.add_axes(ax)
            
            # draw the map parts
            for l in self.legs:
                l.draw(ax)
            for t in self.tracks:
                t.draw(ax)
            
            # render the overlay
            fig.set_size_inches((c/self.DOC_DPI for c in [bg_img.width, bg_img.height]))
            ax.set_xlim(0, bg_img.size[0]/self.DOC_DPI*self.HIGH_DPI)
            ax.set_ylim(bg_img.size[1]/self.DOC_DPI*self.HIGH_DPI, 0)
            overlay_pngbuf = self._get_image_from_figure(fig, dpi=self.DOC_DPI)
            overlay_img = PIL.Image.open(overlay_pngbuf)
            plt.close(fig)

        finally:
            if setRTD:
                self.use_realtime_data = oldRTD

        # return the composited
        composited = PIL.Image.alpha_composite(bg_img.convert('RGBA'), overlay_img.convert('RGBA'))
        buf = io.BytesIO()
        composited.save(buf, 'png')
        buf.seek(0)
        return buf.getvalue()
        

    def calc_basemap_clip(self) -> SimpleRect:
        # calc clip coordinates from the appropriate lon-lat corners
        lat0, lat1, lon0, lon1 = self.extent.minlat, self.extent.maxlat, self.extent.minlon, self.extent.maxlon
        # adjust for non-rectangle because of projection type
        corners_lonlat = [
            VFRPoint(lon0, lat0, route=self),
            VFRPoint(lon1, lat1, route=self),
            VFRPoint(lon1, lat0, route=self),
            VFRPoint(lon0, lat1, route=self)
        ]
        corners_map = [p.project_point(to_system=VFRCoordSystem.MAP_XY) for p in corners_lonlat]
        x0 = min([p.x for p in corners_map])
        y0 = min([p.y for p in corners_map])
        x1 = max([p.x for p in corners_map])
        y1 = max([p.y for p in corners_map])
        # the order of them is important
        if y1<y0:
            y0, y1 = y1, y0
        # this is in LOW_DPI => convert it back to PDF coordinates
        ((x0, y0), (x1, y1)) = ((x0/self.LOW_DPI*72, y0/self.LOW_DPI*72),
                                (x1/self.LOW_DPI*72, y1/self.LOW_DPI*72))
        ((xm, ym), (_, _)) = self.map.margins
        ((x0, y0), (x1, y1)) = ((xm+x0, ym+y0), (xm+x1, ym+y1))
        return SimpleRect(PointXY(x0, y0), PointXY(x1, y1))


    def calc_basemap(self):
        # clip the image
        tiles = self.map.get_tilerenderer(int(os.getenv('DOC_DPI', '200')))
        tile_list, crop, image_size, tile_range = tiles.get_tile_list_for_area(self.calc_basemap_clip())
        composite = PIL.Image.new("RGBA", [int(s) for s in image_size], (0, 0, 0, 0))
        for p in tile_list:
            tile = tiles.get_tile(p.x, p.y, return_format='image')
            # we need to shift the images, other cropping not needed (its outside anyway)
            x = int((p.x - tile_range[0])*tiles.tile_size[0] - crop.p0.x)
            y = int((p.y - tile_range[2])*tiles.tile_size[1] - crop.p0.y)
            composite.paste(tile, (x, y))
        return composite
            
            
    def create_doc(self, save: bool = True) -> Union[io.BytesIO, None]:
        """
        Generates a report of the route as a Word document
        Argument: a list of a tuple
        - first element is a tuple of the leg data
            - 1st element is the name (section header)
            - 2nd element is the function with the bounds used as a text
            - 3rd element is the definition of x points to real life as a text
        - second element is a list of segment data, which is a tuple
            - 1st element is the name
            - 2nd element is the heading at that point
            - 3rd element is the length of the curve segment in meters
            - 4th element is the time used for that curve segment
        """
        self._ensure_state(VFRRouteState.FINALIZED)
        # draw map if we don't have it yet and save the image
        oldRTD, setRTD = False, False
        if not self.use_realtime_data:
            oldRTD, self.use_realtime_data, setRTD = self.use_realtime_data, True, True
        image = self.draw_map()
        imgname = os.path.join(self.outfolder, self.name+'.png')
        with open(imgname, "wb") as f:
            f.write(image)

        # header and image
        doc = Document()

        for section in doc.sections:
            section.top_margin = Cm(1)
            section.bottom_margin = Cm(1)
            section.left_margin = Cm(1)
            section.right_margin = Cm(1)

        doc.add_heading('Route Plan', 0)
        doc.add_paragraph(f"Planned speed: {self.speed} KIAS.")
        doc.add_paragraph(f"Wind forecast for {self.dof:%Y-%m-%d %H:%M %Z}.")
        doc.add_picture(f'{imgname}', width=Cm(19.00))
        doc.add_page_break()

        # legs
        totdist, tottime, tottimewc = 0, 0, 0
        for leg in self.legs:
            # leg heading and definiton
            doc.add_heading(leg.name, level=1)
            doc.add_heading("Definition", level=2)
            add_formula_par(doc, leg.function_name, style="List Bullet")
            add_formula_par(doc, leg.function_range, style="List Bullet")
            doc.add_heading("Segments", level=2)

            # leg table header
            tab = doc.add_table(rows=1, cols=8)
            tab.autofit = True
            tab.allow_autofit = True
            tab.style = "Colorful Shading Accent 1"
            for i, hdr in enumerate(["Name", "Hdg", "Mag", "WCA", "Length", "Time", "Tme(WC)", "Wind"]):
                tab.rows[0].cells[i].text = hdr

            # leg table rows (per annotations)
            for ann in leg.annotations:
                seglen = ann.seglen
                segtime = ann.segtime
                segtime_wind = sum(ann.times_withwind)
                seghdgs = ann.headings
                seghdg = seghdgs[-1]
                wind_corrs = ann.wind_corrections(headings=seghdgs)
                wind_corr = wind_corrs[-1] if wind_corrs else None
                magdev = ann.magnetic_deviation(self.dof)


                row_cells = tab.add_row().cells
            
                row_cells[0].text = ann.name
                #row_cells[0].width = Cm(2)
                
                row_cells[1].text = f"{seghdg:5.0f}\N{DEGREE SIGN}"
                row_cells[2].text = f"{magdev:3.0f}\N{DEGREE SIGN}"
                row_cells[3].text = f"{wind_corr:3.0f}\N{DEGREE SIGN}"
                row_cells[4].text = f"{seglen/1852 if seglen is not None else '-':{'' if seglen is None else '.1f'}}NM"
                row_cells[5].text = f"{math.floor(segtime) if segtime is not None else '-':{'' if segtime is None else '2d'}}"+\
                                    f":{math.floor((segtime-math.floor(segtime))*60) if segtime is not None else '--':{'' if segtime is None else '02d'}}"
                row_cells[6].text = f"{math.floor(segtime_wind) if segtime_wind is not None else '-':{'' if segtime_wind is None else '2d'}}"+\
                                    f":{math.floor((segtime_wind-math.floor(segtime_wind))*60) if segtime_wind is not None else '--':{'' if segtime_wind is None else '02d'}}"
                row_cells[7].text = f"{ann.wind_dir:3d}\N{DEGREE SIGN} {ann.wind_speed:.0f}kts"

                totdist+=seglen if seglen is not None else 0
                tottime+=segtime if segtime is not None else 0
                tottimewc+=segtime_wind if segtime_wind is not None else 0

        # total distance/time
        doc.add_paragraph(f"Total: {totdist/1852:.0f} NM, " +
                          f"{math.floor(tottime):2d}:{math.floor((tottime-math.floor(tottime))*60):02d} / " +
                          f"{math.floor(tottimewc):2d}:{math.floor((tottimewc-math.floor(tottimewc))*60):02d}"
                         )


        # save it
        if setRTD:
            self.use_realtime_data = oldRTD
        if save:
            docname = os.path.join(self.outfolder, self.name+'.docx')
            doc.save(docname)
            return
        else:
            buf = io.BytesIO()
            doc.save(buf)
            buf.seek(0)
            return buf


    def save_plan(self):
        self._ensure_state(VFRRouteState.FINALIZED)
        gpx = gpxpy.gpx.GPX()
        gpx.name = "Elmebeteg VFR útvonal"
        gpx.time = datetime.datetime.now()
        rte = gpxpy.gpx.GPXRoute(name="Elmebeteg VFR útvonal")
        for leg in self.legs:
            x = np.linspace(min([x for p, x in leg.points]),
                            max([x for p, x in leg.points]),
                            100
                            )
            psrc = [VFRPoint(x, leg.function(x), VFRCoordSystem.FUNCTION, self, leg) for x in x]
            ps = [p.project_point(VFRCoordSystem.LONLAT) for p in psrc]
            pt = [gpxpy.gpx.GPXRoutePoint(p.lat, p.lon, name=leg.name if i==0 else None) for i, p in enumerate(ps)]
            rte.points.extend(pt)
        gpx.routes.append(rte)
        return gpx.to_xml()


    def __repr__(self):
        """
        """
        s = f"{type(self).__name__}({self.name})\n"
        for l in self.legs:
            s += textwrap.indent(repr(l), "  ")
        return s
    

    def toDict(self):
        # initiate json object with basic info
        jsonrte = {
            'name': self.name,
            'mapname': self.map.name,
            'speed': self.speed,
            'dof': self.dof.isoformat(),
            'state': self._state.name
        }
        # step 1: area of interest
        #if self._state.value>=VFRRouteState.AREAOFINTEREST.value:
        jsonrte['step1'] = { 'area_of_interest': {
            'top-left': self.area_of_interest['top-left'].toDict(),
            'bottom-right': self.area_of_interest['bottom-right'].toDict(),
        }}
        # step 2: waypoints
        #if self._state.value>=VFRRouteState.WAYPOINTS.value:
        jsonrte['step2'] = { 'waypoints': [(wp[0], wp[1].toDict()) for wp in self.waypoints] }
        # step 3: legs
        #if self._state.value>=VFRRouteState.LEGS.value:
        jsonrte['step3'] = { 'legs': [leg.toDict() for leg in self.legs] }
        # step 4: annotation points
        #if self._state.value>=VFRRouteState.ANNOTATIONS.value:
        jsonrte['step4'] = { 'annotations': [[ann.toDict() for ann in leg.annotations] for leg in self.legs] }
        # step 5: tracks
        #if self._state.value>=VFRRouteState.FINALIZED.value:
        jsonrte['step5'] = { 'tracks': [t.toDict() for t in self.tracks]}
        # return
        return jsonrte
    
    def toJSON(self):
        return json.dumps(self.toDict(), indent=2)
    

    @classmethod
    def fromJSON(cls, jsonstring: str, 
                 session: requests.Session = None,
                 workfolder: Union[str, Path, None] = None,
                 outfolder: Union[str, Path, None] = None,
                 tracksfolder: Union[str, Path, None] = None):
        # decode json
        jsonrte = json.loads(jsonstring)
        # load it
        return VFRFunctionRoute.fromDict(jsonrte, session, workfolder, outfolder, tracksfolder)

    @classmethod
    def fromDict(cls, jsonrte: dict,
                 session: requests.Session = None,
                 workfolder: Union[str, Path, None] = None,
                 outfolder: Union[str, Path, None] = None,
                 tracksfolder: Union[str, Path, None] = None):
        # initiate with basic info
        rte = VFRFunctionRoute(jsonrte['name'],
                               MapManager.instance().maps.get(jsonrte['mapname']),
                               jsonrte['speed'],
                               datetime.datetime.fromisoformat(jsonrte['dof']),
                               session, workfolder, outfolder, tracksfolder)
        state = VFRRouteState[jsonrte['state']]
        # step 1: area of interest
        #if state.value>=VFRRouteState.AREAOFINTEREST.value:
        rte.area_of_interest = {
            'top-left': VFRPoint.fromDict(jsonrte['step1']['area_of_interest']['top-left'], rte),
            'bottom-right': VFRPoint.fromDict(jsonrte['step1']['area_of_interest']['bottom-right'], rte),
        }
        #rte.set_state(VFRRouteState.AREAOFINTEREST)
        # step 2: waypoints
        #if state.value>=VFRRouteState.WAYPOINTS.value:
        rte.waypoints = [(name, VFRPoint.fromDict(p, rte)) for name, p in jsonrte['step2']['waypoints']]
        #rte.set_state(VFRRouteState.WAYPOINTS)
        # step 3: legs
        #if state.value>=VFRRouteState.LEGS.value:
        rte.legs = [VFRLeg.fromDict(leg, rte) for leg in jsonrte['step3']['legs']]
        #rte.set_state(VFRRouteState.LEGS)
        # step 4: annotation points
        #if state.value>=VFRRouteState.ANNOTATIONS.value:
        for i, l in enumerate(jsonrte['step4']['annotations']):
            leg = rte.legs[i]
            leg.annotations = [VFRAnnotation.fromDict(ann, leg) for ann in l]
        #rte.set_state(VFRRouteState.ANNOTATIONS)
        # step 5: tracks
        #if state.value>=VFRRouteState.FINALIZED.value:
        rte.tracks = [VFRTrack.fromDict(t, rte) for t in jsonrte['step5']['tracks']]
        #rte.set_state(VFRRouteState.FINALIZED)
        # set final state and return
        rte.set_state(state)
        return rte
