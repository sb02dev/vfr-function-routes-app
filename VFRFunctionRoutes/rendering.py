"""
Tile rendering capabilities
"""
import io
import math
from typing import Callable, Iterator, Optional, Literal, Union
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import PIL
import pymupdf


class TileRenderer:
    """
    A class rendering tiles from a map in a pdf.

    Parameters:

    """
    def __init__(self,
                 pdf_fname: str,
                 crop_rect: tuple[tuple[float, float], tuple[float, float]],
                 crop_rect_source: Literal['pdf', 'pdf_margins', 'target'],
                 dpi: float,
                 tile_size: tuple[float, float] = (512, 512),
                 draw_func: Optional[Callable] = None
                 ):
        # save parameters
        self.pdf_fname = pdf_fname
        self.crop_rect = crop_rect
        self.crop_rect_source = crop_rect_source
        self.dpi = dpi
        self.tile_size: tuple[float, float] = tile_size
        self._draw_func = draw_func
        # init state variables
        self._pdf_document: pymupdf.Document = None
        self.image_size: tuple[int, int] = None
        self._clip: pymupdf.Rect = None
        self.tile_count: tuple[int, int] = None
        self._fig = None

    def __enter__(self) -> 'TileRenderer':
        """
        Sets up the environment to generate tiles.
        """
        # open pdf
        self._pdf_document = pymupdf.open(self.pdf_fname)
        page = self._pdf_document[0]

        # calculate crop_rect
        scale = 1/72*self.dpi
        scaled_crop_rect = self.crop_rect
        if self.crop_rect_source == 'pdf_margins':
            page_rect = page.rect  # the page rectangle
            scaled_crop_rect = ((self.crop_rect[0][0], self.crop_rect[0][1]),
                                (page_rect.width - self.crop_rect[1][0], page_rect.height - self.crop_rect[1][1]))
        elif self.crop_rect_source == 'target':
            scaled_crop_rect = ((self.crop_rect[0][0]/scale, self.crop_rect[0][1]/scale),
                                (self.crop_rect[1][0]/scale, self.crop_rect[1][1]/scale))
        self._clip = pymupdf.Rect(scaled_crop_rect[0][0],
                                 scaled_crop_rect[0][1],
                                 scaled_crop_rect[1][0],
                                 scaled_crop_rect[1][1])  # the area we want

        # calculate tile numbers
        self.image_size = (self._clip.width * scale, self._clip.height * scale)
        self.tile_count = (math.ceil(self.image_size[0] / self.tile_size[0]),
                           math.ceil(self.image_size[1] / self.tile_size[1]))
        
        # if we have a draw_func, call it
        if self._draw_func:
            self._fig = self._draw_func()


        # return
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # close the pdf file
        self._pdf_document = None
        if self._fig:
            plt.close(self._fig)

    def get_tile(self, x: int, y: int, return_format: Literal['buf', 'image'] = 'buf') -> Union[bytes, PIL.Image]:
        """
        Get the tile at the xth row yth column as a PNG bytes array
        """
        # calculate the clip coordinates
        page = self._pdf_document[0]
        scale = 1/72*self.dpi
        ((mx0, my0), (mx1, my1)) = ((self._clip.x0, self._clip.y0), (self._clip.x1, self._clip.y1))
        x_pixels = x * self.tile_size[0]
        y_pixels = y * self.tile_size[1]
        clip = pymupdf.Rect(
            mx0 + x_pixels/scale,
            my0 + y_pixels/scale,
            min(mx1, mx0 + (x_pixels + self.tile_size[0] - 1)/scale),
            min(my1, my0 + (y_pixels + self.tile_size[1] - 1)/scale)
        )

        pixmap: pymupdf.Pixmap = page.get_pixmap(clip=clip, dpi=self.dpi)

        if not self._fig:
            # only background: just get the image
            if return_format=='buf':
                return pixmap.tobytes("jpg", 85)
            return PIL.Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGBA")    

        # get the image as a Pillow Image object
        bg_img: PIL.Image = PIL.Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGBA")

        # render a tile of the overlay figure
        fig = self._fig
        self._fig.set_size_inches((c/self.dpi for c in [bg_img.width, bg_img.height]))
        ax = fig.get_axes()[0]
        ax.set_xlim(x*self.tile_size[0],
                    min(self.image_size[0]-1, (x+1)*self.tile_size[0]-1))
        ax.set_ylim(min(self.image_size[1]-1, (y+1)*self.tile_size[1]-1),
                    y*self.tile_size[1])
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches="tight", pad_inches=0, dpi=self.dpi, transparent=True)
        buf.seek(0)
        overlay_img = PIL.Image.open(buf).convert("RGBA")

        # composite the two images
        final_img = PIL.Image.alpha_composite(bg_img, overlay_img).convert("RGB")
        if return_format=='image':
            return final_img

        # return as jpg buffer
        buf = io.BytesIO()
        final_img.save(buf, 'jpeg', quality=85)
        buf.seek(0)
        return buf.getvalue()


    def get_tile_order(self) -> Iterator[tuple[int, int]]:
        """
        Get a list of tile coordinates ordered by priority (closer to center)
        """            
        cx = self.tile_count[0] / 2
        cy = self.tile_count[1] / 2

        tiles: list[tuple[int, int, float]] = []

        for xi in range(self.tile_count[0]):
            for yi in range(self.tile_count[1]):
                dx = xi + 0.5 - cx
                dy = yi + 0.5 - cy
                dist = math.sqrt(dx * dx + dy * dy)
                tiles.append((xi, yi, dist))

        # sort by distance from center(smallest first)
        tiles.sort(key=lambda item: item[2])
        for item in tiles:
            yield (item[0], item[1])
