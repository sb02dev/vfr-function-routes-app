"""
Map managing utilities
"""
import os
import io
from typing import Union
import json
import requests

# pdf and imaging related packages
import pymupdf
import PIL
import matplotlib
matplotlib.use("Agg")
# pylint: disable=wrong-import-position
import matplotlib.pyplot as plt
from matplotlib.backend_bases import MouseButton
import numpy as np

from .projutils import PointLonLat, PointXY
from .rendering import SimpleRect, TileRenderer
# pylint: enable=wrong-import-position


class MapDefinition:
    """The definition of how to use an official map from PDF form
    Download URL, crop regions, transformation from x-y to lon-lat,
    projection string, etc.
    """

    def __init__(self,  # pylint: disable=too-many-arguments,disable=too-many-positional-arguments
                 name: str,
                 url: str,
                 projection_string: str,
                 page_num: int,
                 margins: SimpleRect,
                 defaultarea: dict[str, PointLonLat],
                 points: dict[PointLonLat, PointXY],
                 dpis: list[int],
                 datadir: str,
                 request_session: requests.Session):
        self.name = name
        self.url = url
        self.page_num = page_num
        self.projection_string = projection_string
        self.margins = margins
        self.area = defaultarea
        self.points = points
        self.datafolder = datadir
        self.request_session = request_session
        self.download_map()
        self.tilerenderers = {dpi: TileRenderer(self.name,
                                                self.datafolder,
                                                self.name+'.pdf',
                                                self.page_num,
                                                self.margins,
                                                dpi
                                                ) for dpi in dpis}

    def download_map(self):
        """Downloads the map in PDF form from the Internet and stores it locally."""
        pdf_destination = os.path.join(self.datafolder, self.name+".pdf")
        if not os.path.isfile(pdf_destination):
            response = self.request_session.get(self.url, timeout=10)
            with open(pdf_destination, 'wb') as pdf_file:
                pdf_file.write(response.content)


    def get_tilerenderer(self, dpi: int) -> Union[TileRenderer, None]:
        """Get the TileRenderer for the specified resolution"""
        return self.tilerenderers.get(dpi, None)


    @classmethod
    def from_dict(cls, dct: dict, dpis: list[int], datadir: str, request_session: requests.Session):
        """A factory method to be able to load the object from file."""
        return MapDefinition(dct["name"],
                             dct["url"],
                             dct["projection_string"],
                             dct["pagenum"],
                             SimpleRect(PointXY(dct["margins"]["left"],
                                                dct["margins"]["top"]),
                                        PointXY(dct["margins"]["right"],
                                                dct["margins"]["bottom"])),
                             {"top-left": PointLonLat(
                                 dct["defaultarea"]["top-left"]["lon"],
                                 dct["defaultarea"]["top-left"]["lat"]),
                             "bottom-right": PointLonLat(
                                 dct["defaultarea"]["bottom-right"]["lon"],
                                 dct["defaultarea"]["bottom-right"]["lat"])},
                             {PointLonLat(p["lon"], p["lat"]): PointXY(p["x"], p["y"])
                              for p in dct["projectionpoints"]},
                             dpis,
                             datadir,
                             request_session
        )


class MapManager:
    """
    A Manager class for the maps available in the app (defined in a json file in maps/ folder)
    """
    def __init__(self, dpis: list[int], request_session: requests.Session):
        self.dpis = dpis
        self.request_session = request_session
        # get folder paths
        self.rootdir = os.path.dirname(os.path.dirname(__file__))
        self.datadir = os.path.join(self.rootdir, "data")
        self.mapsdir = os.path.join(self.rootdir, "maps")
        # get list of maps
        maps = [self.read_map_config(os.path.join(self.mapsdir, n),
                                     self.dpis,
                                     self.datadir)
                for n in os.listdir(self.mapsdir)
                if os.path.isfile(os.path.join(self.mapsdir, n)) and \
                   os.path.basename(n).lower().endswith('.json')
        ]
        self.maps = {map.name: map for map in maps}
        # save the first instance
        if not hasattr(self.__class__, "_instance"):
            self.__class__._instance = self


    @classmethod
    def instance(cls):
        """Singleton pattern accessor"""
        if hasattr(cls, "_instance"):
            return cls._instance
        return None


    def read_map_config(self, fname: str, dpis: list[int], datadir: str) -> MapDefinition:
        """Load the definition of a map from disk"""
        with open(fname, "rt", encoding="utf8") as f:
            return MapDefinition.from_dict(json.load(f), dpis, datadir, self.request_session)


    def download_maps(self):
        """Download all maps"""
        for _, curmap in self.maps.items():
            curmap.download_map(self.request_session)


    def get_tilerenderer(self, mapname: str, dpi: int) -> TileRenderer:
        """Get TileRenderer based on the name of the map and the resolution"""
        curmap = self.maps.get(mapname, None)
        if curmap is None:
            return None
        return curmap.get_tilerenderer(dpi)


    @staticmethod
    def map_areaselect_lowres(pdf_path: str,  # pylint: disable=too-many-statements
                              area: SimpleRect,
                              fullmap_points: list[PointXY]
                             ) -> tuple[SimpleRect, bool]:
        """An interactive 'clicker' to find coordinates of points.
        Helper for defining a new map
        """
        # load pdf as image
        pdf_document = pymupdf.open(pdf_path)
        page = pdf_document[0]
        print("Page rect: ", page.rect)
        pdfimg = PIL.Image.open(io.BytesIO(page.get_pixmap().tobytes("png")))
        # set up plot
        matplotlib.use("TkAgg")
        fig, ax = plt.subplots()
        ax.imshow(pdfimg)
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        # set up rectangle
        points = [
            PointXY(area.p0.x, area.p0.y),
            PointXY(area.p1.x, area.p0.y),
            PointXY(area.p1.x, area.p1.y),
            PointXY(area.p0.x, area.p1.y)
        ]
        _ = ax.scatter([p[0] for p in fullmap_points],
                       [p[1] for p in fullmap_points], c="red", marker="X")
        sc = ax.scatter([p.x for p in points], [p.y for p in points], s=100, zorder=3, picker=True)
        rect_line, = ax.plot([p.x for p in points] + [points[0].x],
                             [p.y for p in points] + [points[0].y],
                             "b-",
                             lw=2)
        dragging_idx = None
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        cont = True
        # set up interaction
        def on_press(event):
            nonlocal dragging_idx
            nonlocal points
            # Skip if not inside axes or not left click
            if event.inaxes != ax:
                return
            # Skip if toolbar is in zoom or pan mode
            if plt.get_current_fig_manager().toolbar.mode != "":
                return
            # Find nearest corner (if within threshold)
            if event.button == 1:
                pts = np.column_stack([[p.x for p in points], [p.y for p in points]])
                click = np.array([event.xdata, event.ydata])
                dists = np.linalg.norm(pts - click, axis=1)
                idx = np.argmin(dists)
                if dists[idx] < 30:  # sensitivity threshold
                    dragging_idx = idx
        def on_motion(event):
            nonlocal dragging_idx, area, points
            if dragging_idx is None:
                return
            if event.inaxes != ax:
                return
            # Update dragged corner
            if dragging_idx == 0: # top-left
                area = SimpleRect(PointXY(event.xdata, event.ydata),
                                  PointXY(area.p1.x, area.p1.y))
            elif dragging_idx == 1: # top-right
                area = SimpleRect(PointXY(area.p0.x, event.ydata),
                                  PointXY(event.xdata, area.p1.y))
            elif dragging_idx == 2:  # bottom-right
                area = SimpleRect(PointXY(area.p0.x, area.p0.y),
                                  PointXY(event.xdata, event.ydata))
            elif dragging_idx == 3:  # bottom-left
                area = SimpleRect(PointXY(event.xdata, area.p0.y),
                                  PointXY(area.p1.x, event.ydata))
            points = [
                PointXY(area.p0.x, area.p0.y),
                PointXY(area.p1.x, area.p0.y),
                PointXY(area.p1.x, area.p1.y),
                PointXY(area.p0.x, area.p1.y)
            ]
            # Update scatter and line
            sc.set_offsets(points)
            rect_line.set_data([p.x for p in points] + [points[0].x],
                               [p.y for p in points] + [points[0].y])
            fig.canvas.draw_idle()
        def on_release(event): # pylint: disable=unused-argument
            nonlocal dragging_idx
            dragging_idx = None
        def on_key(event):
            nonlocal cont
            if event.key == "escape":   # close on ESC
                plt.close(fig)
                cont = False
        fig.canvas.mpl_connect("button_press_event", on_press)
        fig.canvas.mpl_connect("motion_notify_event", on_motion)
        fig.canvas.mpl_connect("button_release_event", on_release)
        fig.canvas.mpl_connect("key_press_event", on_key)
        # do the plotting
        plt.show(block=True)
        matplotlib.use("Agg")
        return area, cont


    @staticmethod
    def map_clicker_highres(pdf_path: str,
                            area: SimpleRect,
                            fullmap_points: list[PointXY]
                           ) -> tuple[list[PointXY], bool]:
        """An interactive 'clicker' to find coordinates of points.
        Helper for defining a new map
        """
        # convert fullmap_points to cropmap_points
        points = [PointXY((p.x - area.p0.x)/72*600,
                          (p.y - area.p0.y)/72*600)
                  for p in fullmap_points]
        # load pdf as image
        pdf_document = pymupdf.open(pdf_path)
        page = pdf_document[0]
        clip = pymupdf.Rect(area.p0.x, area.p0.y, area.p1.x, area.p1.y)
        pdfimg = PIL.Image.open(io.BytesIO(page.get_pixmap(clip=clip, dpi=600).tobytes("png")))
        # set up plot
        matplotlib.use("TkAgg")
        fig, ax = plt.subplots()
        ax.imshow(pdfimg)
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        pts_artist = ax.scatter([p[0] for p in points],
                                [p[1] for p in points], c="red", marker="X")
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        cont = True
        # set up interaction
        def on_click(event):
            nonlocal points
            # Skip if not inside axes or not left click
            if event.inaxes != ax:
                return
            # Skip if toolbar is in zoom or pan mode
            if plt.get_current_fig_manager().toolbar.mode != "":
                return
            # add or remove point
            if event.button is MouseButton.LEFT:
                points.append(PointXY(event.xdata, event.ydata))
            elif event.button is MouseButton.RIGHT:
                if len(points) == 0:
                    return
                click_point = np.array([event.xdata, event.ydata])
                pts_vec = np.column_stack([[p[0] for p in points], [p[1] for p in points]])
                dists = np.linalg.norm(pts_vec - click_point, axis=1)
                idx = np.argmin(dists)
                if dists[idx]<30:
                    points.pop(idx)
            if len(points)>0:
                pts_artist.set_offsets(points)
            else:
                pts_artist.set_offsets(np.empty((0,2)))
            fig.canvas.draw_idle()
        def on_key(event):
            nonlocal cont
            if event.key == "escape":   # close on ESC
                plt.close(fig)
                cont = False
        fig.canvas.mpl_connect('button_press_event', on_click)
        fig.canvas.mpl_connect("key_press_event", on_key)
        # do the plotting
        plt.show(block=True)
        # convert back
        new_points = [PointXY(p.x/600*72 + area.p0.x, p.y/600*72 + area.p0.y) for p in points]
        # return
        matplotlib.use("TkAgg")
        return new_points, cont



    @staticmethod
    def setup_new_map():
        """The main loop of the helper script for defining a new map."""
        print("Let's setup a new map.")
        # get the basic data
        name = input("Enter the name of the new map: ")
        url = input("Enter the URL: ")
        # get folder paths
        rootdir = os.path.dirname(os.path.dirname(__file__))
        datadir = os.path.join(rootdir, "data")
        #mapsdir = os.path.join(rootdir, "maps")
        # download map
        pdf_destination = os.path.join(datadir, name+".pdf")
        if not os.path.isfile(pdf_destination):
            response = requests.get(url, timeout=10)
            with open(pdf_destination, 'wb') as pdf_file:
                pdf_file.write(response.content)
        # iterate while user exits
        points: list[PointXY] = []
        area = SimpleRect(PointXY(0, 0), PointXY(100, 100))
        cont = True
        while cont:
            # draw full map in low resolution and select area
            area, cont = MapManager.map_areaselect_lowres(pdf_destination, area, points)
            if not cont:
                break
            # zoom in on area and on point click print the coordinates in pdf system
            points, cont = MapManager.map_clicker_highres(pdf_destination, area, points)
        print(points)
        # collect information from the above + ask for lon-lat
        print("According to the points you clicked above, give me the following data:")
        # collect: margins
        left = input("  Left margin of the PDF: ")
        top = input("  Top margin of the PDF: ")
        right = input("  Right margin of the PDF " + \
                      "(Don't forget to substract the X value from Page rect right): ")
        bottom = input("  Bottom margin of the PDF " + \
                       "(Don't forget to substract the Y value from Page rect bottom): ")
        # TODO: collect: projection points and their lon-lat values
        projpoints = []
        # write json definition
        def_obj = {
            "name": name,
            "url": url,
            "projection_string": "+proj=lcc +lon_0=-90 +lat_1=46 +lat_2=48 +ellps=WGS84",
            "margins": {
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom
            },
            "projectionpoints": projpoints
        }
        print(json.dumps(def_obj))
