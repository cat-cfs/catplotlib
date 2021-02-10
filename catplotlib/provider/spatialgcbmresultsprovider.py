import os
import sqlite3
import gdal
import pandas as pd
from multiprocessing import Pool
from glob import glob
from collections import OrderedDict
from catplotlib.spatial.layer import Layer
from catplotlib.provider.units import Units
from catplotlib.provider.resultsprovider import ResultsProvider
from catplotlib.util.utmzones import find_best_projection

class SpatialGcbmResultsProvider(ResultsProvider):
    '''
    Retrieves non-spatial annual results from a stack of spatial layers.

    Arguments:
    'pattern' -- glob pattern for spatial layers to read.
    'layers' -- instead of specifying a file pattern to search for, a list of Layer
        objects can be provided directly.
    '''

    def __init__(self, pattern=None, layers=None, *args, **kwargs):
        self._pattern = pattern
        self._layers = layers
        if not (pattern or layers):
            raise RuntimeError("Must provide either a file pattern or a list of Layer objects")

    @property
    def simulation_years(self):
        '''See GcbmResultsProvider.simulation_years.'''
        layers = self._layers or self._find_layers()
        return min((l.year for l in layers)), max((l.year for l in layers))

    def get_annual_result(self, indicator, start_year=None, end_year=None,
                          units=Units.Tc, bounding_box=None, **kwargs):
        '''See GcbmResultsProvider.get_annual_result.'''
        layers = self._layers or self._find_layers()
        if not start_year or not end_year:
            start_year, end_year = self.simulation_years

        _, units_tc, _ = units.value

        result_years = list(range(start_year, end_year + 1))
        working_layers = [layer for layer in layers if layer.year in result_years]
        with Pool() as pool:
            if bounding_box:
                working_layers = pool.map(bounding_box.crop, working_layers)

            data = OrderedDict()
            data["year"] = []
            data["value"] = []
            for year in result_years:
                data["year"].append(year)
                layer = self._find_year(working_layers, year)
                if not layer:
                    data["value"].append(0)
                    continue

                data["value"].append(layer.aggregate(units))

            return pd.DataFrame(data)

    def _find_layers(self):
        pattern = self._pattern
        units = Units.TcPerHa
        if isinstance(self._pattern, tuple):
            pattern, units = self._pattern

        layers = []
        for layer_path in glob(pattern):
            year = os.path.splitext(layer_path)[0][-4:]
            layer = Layer(layer_path, year, units=units)
            layers.append(layer)

        if not layers:
            raise IOError(f"No spatial output found for pattern: {pattern}")

        return layers

    def _find_year(self, layers, year):
        return next(filter(lambda layer: layer.year == year, layers), None)
