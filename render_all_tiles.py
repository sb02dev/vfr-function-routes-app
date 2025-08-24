import os
from dotenv import load_dotenv
load_dotenv()
import requests

from VFRFunctionRoutes import MapManager

if __name__ == "__main__":
    mapmanager = MapManager(
        [int(os.getenv(var, str(val)))
         for var, val
         in zip(['LOW_DPI', 'DOC_DPI', 'HIGH_DPI'],
                [72, 200, 600])],
        requests.Session())
    count = 0
    for mapname, curmap in mapmanager.maps.items():
        for dpi, tr in curmap.tilerenderers.items():
            count += tr.tile_count.x * tr.tile_count.y
    index = 0
    for mapname, curmap in mapmanager.maps.items():
        for dpi, tr in curmap.tilerenderers.items():
            for xi in range(tr.tile_count.x):
                for yi in range(tr.tile_count.y):
                    print(f"Generating {mapname}-{dpi}-x{xi}-y{yi} ({index}/{count})", flush=True)
                    tr.get_tile(xi, yi)
                    index += 1
