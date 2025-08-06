"""
Tile rendering capabilities
"""
import math
from typing import Iterator, Optional, Literal
from pathlib import Path
import pymupdf
import math


class TileRenderer:
    """
    A class rendering tiles from a map in a pdf.

    Parameters:

    """
    def __init__(self,
                 pdf_fname: str | Path,
                 crop_rect: tuple[tuple[float, float], tuple[float, float]],
                 crop_rect_source: Literal['pdf', 'pdf_margins', 'target'],
                 dpi: float,
                 tile_size: tuple[float, float] = (512, 512)
                 ):
        # save parameters
        self.pdf_fname = pdf_fname
        self.crop_rect = crop_rect
        self.crop_rect_source = crop_rect_source
        self.dpi = dpi
        self.tile_size: tuple[float, float] = tile_size
        # init state variables
        self._pdf_document: pymupdf.Document = None
        self.image_size: tuple[int, int] = None
        self._clip: pymupdf.Rect = None
        self.tile_count: tuple[int, int] = None

    def __enter__(self) -> 'TileRenderer':
        """
        Sets up the environment to generate tiles.
        """
        # open pdf
        self._pdf_document = pymupdf.open(self.pdf_fname)
        page = self._pdf_document[0]

        # calculate crop_rect
        scale = 1/72*self.dpi
        if self.crop_rect_source == 'pdf':
            scaled_crop_rect = self.crop_rect
        elif self.crop_rect_source == 'pdf_margins':
            page_rect = page.rect  # the page rectangle
            scaled_crop_rect = ((self.crop_rect[0][0], self.crop_rect[0][1]),
                                (page_rect.width - self.crop_rect[1][0], page_rect.height - self.crop_rect[1][1]))
        elif self.crop_rect_source == 'target':
            scaled_crop_rect = ((self.crop_rect[0][0]*scale, self.crop_rect[0][1]*scale),
                                (self.crop_rect[1][0]*scale, self.crop_rect[1][1]*scale))
        self._clip = pymupdf.Rect(scaled_crop_rect[0][0],
                                 scaled_crop_rect[0][1],
                                 scaled_crop_rect[1][0],
                                 scaled_crop_rect[1][1])  # the area we want

        # calculate tile numbers
        self.image_size = (self._clip.width * scale, self._clip.height * scale)
        self.tile_count = (math.ceil(self.image_size[0] / self.tile_size[0]),
                           math.ceil(self.image_size[1] / self.tile_size[1]))

        # return
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # close the pdf file
        self._pdf_document = None

    def get_tile(self, x: int, y: int) -> bytes:
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

        # get the image
        pixmap: pymupdf.Pixmap = page.get_pixmap(clip=clip, dpi=self.dpi)
        return pixmap.tobytes("jpg", 85)

    def get_tile_order(self) -> Iterator[tuple[int, int]]:
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
