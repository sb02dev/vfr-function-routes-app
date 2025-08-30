"""This script helps configuring a new map for the server"""
#import requests

from VFRFunctionRoutes import MapManager

if __name__ == "__main__":
    MapManager.setup_new_map()
    #mapmanager = MapManager([72, 200, 600], requests.Session())
