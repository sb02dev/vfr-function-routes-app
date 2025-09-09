"""NavAid database queries"""
import os
import re
import requests
import pyproj
import pandas as pd

from .projutils import PointLonLat

OURAIRPORTS_DATA_URL = "https://davidmegginson.github.io/ourairports-data/"
ARC_POINT_DEF_RE = re.compile(r'^([A-Z]{3})\/(\d{1,3})\/([\d\.]*)\/([\d\.]*)$')

class NavAidDatabase:
    """NavAid database helper class"""

    def __init__(self, workdir: str):
        self.workdir = workdir
        self.geod = pyproj.Geod(
            "+proj=lcc +lon_0=-90 +lat_1=46 +lat_2=48 +ellps=WGS84")
        for ds_name in ['navaids', 'airports']:
            self.download_dataset(ds_name)
        self.df_navaids = pd.read_csv(os.path.join(self.workdir, 'navaids.csv'))
        self.df_airports = pd.read_csv(os.path.join(self.workdir, 'airports.csv'))


    def lookup_airports(self, search: str) -> list[str]:
        """Search for airports in the database based on the search string"""
        airport_def = self.df_airports[
            ((self.df_airports['ident'].str.match('.*'+search+'.*')) |
             (self.df_airports['name'].str.match('.*'+search+'.*'))) &
            (self.df_airports['type'].isin(
                ['heliport','large_airport','medium_airport','small_airport']
            )
            )]
        return list(airport_def['ident'])


    def lookup_navaids(self, search: str) -> list[str]:
        """Search for navaids in the database based on the search string"""
        vor_station_def = self.df_navaids[
            (self.df_navaids['ident'].str.match('.*'+search+'.*')) &
            (self.df_navaids['type'].isin(
                ['VOR', 'VOR-DME']
            )
        )]
        return list(vor_station_def['ident'])


    def get_airport_location(self, airport_lookup: str):
        """Get a location from an airport identifier"""
        airport_def = self.df_airports[
            (self.df_airports['ident'] == airport_lookup) &
            (self.df_airports['type'].isin(
                ['heliport', 'large_airport', 'medium_airport', 'small_airport']
            ))]
        if len(airport_def.index) != 1:
            raise ValueError(
                "There are none/multiple VOR stations with that name")
        airport_def = airport_def.iloc[0]
        airport = PointLonLat(airport_def["longitude_deg"],
                                    airport_def["latitude_deg"])
        return airport


    def get_vor_location(self, vor_lookup: str):
        """Get a location from a VOR name or a VOR/Radial/DME/magnetic_adj string"""
        if '/' not in vor_lookup:
            vor_station_def = self.df_navaids[
                (self.df_navaids['ident'] == vor_lookup) &
                (self.df_navaids['type'].isin(['VOR', 'VOR-DME'])
            )]
            if len(vor_station_def.index) != 1:
                raise ValueError("There are none/multiple VOR stations with that name")
            vor_station_def = vor_station_def.iloc[0]
            vor_station = PointLonLat(vor_station_def["longitude_deg"],
                                    vor_station_def["latitude_deg"])
            return vor_station
        else:
            # get input
            m = ARC_POINT_DEF_RE.match(vor_lookup)
            if m is None:
                raise ValueError(
                    "The VOR lookup syntax is wrong")
            vor = m.group(1)
            radial = int(m.group(2))
            dme = float(m.group(3))
            magn = float(m.group(4))
            # get the vor coords
            vor_station_def = self.df_navaids[
                (self.df_navaids['ident'] == vor) &
                (self.df_navaids['type'].isin(['VOR', 'VOR-DME'])
                 )]
            if len(vor_station_def.index) != 1:
                raise ValueError(
                    "There are none/multiple VOR stations with that name")
            vor_station_def = vor_station_def.iloc[0]
            vor_station = PointLonLat(vor_station_def["longitude_deg"],
                                      vor_station_def["latitude_deg"])
            # calculate
            rad_adj = radial + magn
            dme_meters = dme * 1852
            dest_lon, dest_lat, _ = self.geod.fwd(
                vor_station.lon,
                vor_station.lat,
                rad_adj,
                dme_meters
            )
        return PointLonLat(dest_lon, dest_lat)


    def download_dataset(self, dataset_name: str) -> None:
        """Download the CSV file from ourairports datasets (.csv extension
        should not be added)
        """
        if not os.path.isfile(os.path.join(self.workdir, dataset_name+".csv")):
            resp = requests.get(
                url=OURAIRPORTS_DATA_URL+dataset_name+".csv",
                timeout=10
            )
            with open(os.path.join(self.workdir, dataset_name+'.csv'), "wb") as f:
                f.write(resp.content)
