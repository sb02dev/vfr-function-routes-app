"""
Tile rendering capabilities
"""
import io
import math
import os
from typing import Callable, Iterator, NamedTuple, Optional, Literal, Union
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import PIL
import pymupdf

from .projutils import PointXY


SimpleRect = NamedTuple('SimpleRect', [('p0', PointXY), ('p1', PointXY)])
PointXYInt = NamedTuple('PointXYInt', [('x', int), ('y', int)])

class TileRenderer:
    """
    A class rendering tiles from a map in a pdf.

    Parameters:

    """
    def __init__(self,
                 tileset_name: str,
                 datafolder: str,
                 pdf_fname: str,
                 page_num: int,
                 pdf_margins: SimpleRect,
                 dpi: float,
                 tile_size: PointXY = PointXY(512, 512),
                 ):
        # save parameters
        self.tileset_name = tileset_name
        self.datafolder = datafolder
        self.pdf_fname: str = pdf_fname
        self.page_num = page_num
        self.pdf_margins: SimpleRect = pdf_margins
        self.dpi: float = dpi
        self.tile_size: PointXY = tile_size
        self._fig = None

        # open pdf
        self._pdf_document: pymupdf.Document = pymupdf.open(os.path.join(self.datafolder, self.pdf_fname))
        self._page = self._pdf_document[self.page_num]

        # calculate image and tile sizes
        self._page_rect = self._page.rect
        self._crop_rect = pymupdf.Rect(
            (self._page_rect.x0 + self.pdf_margins.p0.x),
            (self._page_rect.y0 + self.pdf_margins.p0.y),
            (self._page_rect.x1 - self.pdf_margins.p1.x),
            (self._page_rect.y1 - self.pdf_margins.p1.y)
        )
        self._scale = 1 / 72 * self.dpi
        self.image_size: PointXYInt = PointXYInt((self._crop_rect.x1 - self._crop_rect.x0) * self._scale,
                                                (self._crop_rect.y1 - self._crop_rect.y0) * self._scale)
        self.tile_count: PointXYInt  = PointXYInt(math.ceil(self.image_size.x / self.tile_size.x),
                                                  math.ceil(self.image_size.y / self.tile_size.y))
        

    def __del__(self):
        self._pdf_document.close()
        self._pdf_document = None


    def get_tile_list_for_area(self, crop_rect: SimpleRect) -> tuple[list[PointXYInt], SimpleRect, PointXY, tuple[float, float, float, float]]:
        """
        Get a list of tiles needed for a given area along with the neccessary cropping (in pixels).

        Parameters:
            crop_rect: SimpleRect
                The area desired in PDF coordinates (72 dpi)
        """
        # list the tiles neccessary
        tile_size_pdf = PointXY(self.tile_size.x / self._scale, self.tile_size.y / self._scale)
        tile_x0 = math.floor((crop_rect.p0.x - self.pdf_margins.p0.x) / tile_size_pdf.x)
        tile_x1 = math.ceil((crop_rect.p1.x - self.pdf_margins.p0.x) / tile_size_pdf.x)
        tile_y0 = math.floor((crop_rect.p0.y - self.pdf_margins.p0.y) / tile_size_pdf.y)
        tile_y1 = math.ceil((crop_rect.p1.y - self.pdf_margins.p0.y) / tile_size_pdf.y)

        tile_list: list[PointXYInt] = [
            PointXYInt(tx, ty)
            for ty in range(tile_y0, tile_y1)
            for tx in range(tile_x0, tile_x1)
        ]

        ordered_tile_list = list(self.get_tile_order(tile_list, (tile_x1 + tile_x0)/2, (tile_y1 + tile_y0)/2))

        # calculate right and bottom to handle the edge case when the last tile is shorter
        tileright = min(self._crop_rect.x1, self._crop_rect.x0 + tile_x1 * tile_size_pdf.x)
        tilebottom = min(self._crop_rect.y1, self._crop_rect.y0 + tile_y1 * tile_size_pdf.y)

        # calculate the region to be cropped
        crop_pdf = SimpleRect(PointXY(max(0, (crop_rect.p0.x - self._crop_rect.x0) - tile_x0 * tile_size_pdf.x),
                                      max(0, (crop_rect.p0.y - self._crop_rect.y0) - tile_y0 * tile_size_pdf.y)),
                              PointXY(max(0, tileright - crop_rect.p1.x),
                                      max(0, tilebottom - crop_rect.p1.y)))

        cropping: SimpleRect = SimpleRect(PointXYInt(crop_pdf.p0.x * self._scale,
                                                     crop_pdf.p0.y * self._scale),
                                          PointXYInt(crop_pdf.p1.x * self._scale,
                                                     crop_pdf.p1.y * self._scale))

        # calculate the cropped image size
        image_size: PointXYInt = PointXYInt((crop_rect.p1.x - crop_rect.p0.x) * self._scale,
                                            (crop_rect.p1.y - crop_rect.p0.y) * self._scale)


        # put it together in the return value
        return ordered_tile_list, cropping, image_size, [tile_x0, tile_x1, tile_y0, tile_y1]


    def get_tile(self, x: int, y: int, return_format: Literal['buf', 'image'] = 'buf') -> Union[bytes, PIL.Image]:
        """
        Get the tile at the xth row yth column as a PNG bytes array
        """
        # check cache
        tile_id = self._get_tile_id(x, y)
        tilecache_fname = os.path.join(self.datafolder, tile_id+".png")
        if os.path.isfile(tilecache_fname):
            if return_format=='image':
                return PIL.Image.open(tilecache_fname)
            with open(tilecache_fname, "rb") as f:
                return f.read()
            

        # calculate the clip coordinates
        x_pixels = x * self.tile_size[0]
        y_pixels = y * self.tile_size[1]
        clip = pymupdf.Rect(
            self._crop_rect.x0 + x_pixels/self._scale,
            self._crop_rect.y0 + y_pixels/self._scale,
            min(self._crop_rect.x1, self._crop_rect.x0 + (x_pixels + self.tile_size.x - 1)/self._scale),
            min(self._crop_rect.y1, self._crop_rect.y0 + (y_pixels + self.tile_size.y - 1)/self._scale)
        )

        pixmap: pymupdf.Pixmap = self._page.get_pixmap(clip=clip, dpi=self.dpi)

        if not self._fig:
            # only background: just get the image
            buf = pixmap.tobytes("png")
            with open(tilecache_fname, "wb") as f:
                f.write(buf)
            if return_format=='buf':
                return buf
            bufio = io.BytesIO(buf)
            return PIL.Image.open(bufio).convert("RGBA")

        # get the image as a Pillow Image object
        bg_img: PIL.Image = PIL.Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGBA")

        # render a tile of the overlay figure
        fig = self._fig
        self._fig.set_size_inches((c/self.dpi for c in [bg_img.width, bg_img.height]))
        ax = fig.get_axes()[0]
        ax.set_xlim(x*self.tile_size.x,
                    min(self.image_size.x-1, (x+1)*self.tile_size.x-1))
        ax.set_ylim(min(self.image_size.y-1, (y+1)*self.tile_size.y-1),
                    y*self.tile_size.y)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches="tight", pad_inches=0, dpi=self.dpi, transparent=True)
        buf.seek(0)
        overlay_img = PIL.Image.open(buf).convert("RGBA")

        # composite the two images
        final_img = PIL.Image.alpha_composite(bg_img, overlay_img).convert("RGB")
        buf = io.BytesIO()
        final_img.save(buf, 'png')
        buf.seek(0)
        with open(tilecache_fname, "wb") as f:
            f.write(buf.getvalue())
        if return_format == 'image':
            return final_img

        # return as jpg buffer
        buf.seek(0)
        return buf.getvalue()


    def get_tile_order(self, in_tiles = Optional[list[PointXYInt]], center_x: float = None, center_y: float = None) -> Iterator[PointXYInt]:
        """
        Get a list of tile coordinates ordered by priority (closer to center)
        """            
        cx = self.tile_count.x / 2 if not center_x else center_x;
        cy = self.tile_count.y / 2 if not center_y else center_y;

        if in_tiles:
            tiles: list[tuple[PointXYInt, float]] = [
                (t, math.sqrt(
                    (t.x + 0.5 - cx)*(t.x + 0.5 - cx) +
                    (t.y + 0.5 - cy)*(t.y + 0.5 - cy))
                )
                for t in in_tiles
            ]
        else:
            tiles: list[tuple[PointXYInt, float]] = [
                (PointXYInt(xi, yi), math.sqrt(
                    (xi + 0.5 - cx)*(xi + 0.5 - cx) +
                    (yi + 0.5 - cy)*(yi + 0.5 - cy))
                 )
                for xi in range(self.tile_count[0])
                for yi in range(self.tile_count[1])
            ]

        # sort by distance from center(smallest first)
        tiles.sort(key=lambda item: item[1])
        for item in tiles:
            yield item[0]

    
    def _get_tile_id(self, x: int, y: int) -> str:
        return f"tilecache_{self.tileset_name}_{self.dpi}DPI_x{x}_y{y}"
    
    @staticmethod
    def rect_to_simplerect(rect: pymupdf.Rect) -> SimpleRect:
        return SimpleRect(PointXY(rect.x0, rect.y0),
                          PointXY(rect.x1, rect.y1))



class SVGRenderer():
    """
    Renders overlays (no map background) with Matplotlib into svg byte arrays
    """
    def __init__(self,
                 crop_rect: SimpleRect,
                 crop_rect_source: Literal['pdf', 'target'],
                 dpi: float,
                 original_dpi: float,
                 draw_func: Callable
                 ):
        # save parameters
        self.dpi = dpi
        self.odpi = original_dpi
        self._draw_func = draw_func
        # calculate image size
        if crop_rect_source == 'pdf':
            self.image_size = PointXY((crop_rect.p1.x-crop_rect.p0.x) / 72 * self.dpi,
                                      (crop_rect.p1.y-crop_rect.p0.y) / 72 * self.dpi)
        elif crop_rect_source == 'target':
            self.image_size = PointXY((crop_rect.p1.x-crop_rect.p0.x),
                                      (crop_rect.p1.y-crop_rect.p0.y))

    
    def get_svg(self):

        import time

        matplotlib.rcParams['svg.fonttype'] = 'none'  # Use text, not curves
    
        start = time.perf_counter_ns()
        fig=self._draw_func()

        fig.set_size_inches((c/self.odpi for c in self.image_size))
        ax=fig.get_axes()[0]
        ax.set_xlim(0, self.image_size.x)
        ax.set_ylim(self.image_size.y, 0)

        buf=io.StringIO()
        fig.savefig(buf, format='svg', dpi=self.dpi, transparent=True)
        buf.seek(0)

        plt.close(fig)

        print(f"total time: {time.perf_counter_ns() - start:15,d}")

        return buf.getvalue()

