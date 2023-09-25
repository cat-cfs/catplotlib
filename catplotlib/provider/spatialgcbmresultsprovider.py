import os
import pandas as pd
from multiprocessing import Pool
from glob import glob
from collections import defaultdict
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from catplotlib.spatial.layer import Layer
from catplotlib.provider.units import Units
from catplotlib.provider.resultsprovider import ResultsProvider
from catplotlib.util.config import pool_workers
from catplotlib.util.config import gdal_creation_options
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.config import catplotlib_memory_limit
from catplotlib.util.tempfile import TempFileManager
from catplotlib.util import gdal

class SpatialGcbmResultsProvider(ResultsProvider):
    '''
    Retrieves non-spatial annual results from a stack of spatial layers.

    Arguments:
    'pattern' -- glob pattern or list of patterns for spatial layers to read,
        or a tuple of (glob pattern or list of patterns, Units) describing the
        native units of the layers (default: TcPerHa).
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
        if not self._layers:
            self._find_layers()

        return min((l.year for l in self._layers)), max((l.year for l in self._layers))

    def get_annual_result(self, indicator, start_year=None, end_year=None,
                          units=Units.Tc, bounding_box=None, **kwargs):
        '''See ResultsProvider.get_annual_result.'''
        if not self._layers:
            self._find_layers()

        if not start_year or not end_year:
            start_year, end_year = self.simulation_years

        result_years = list(range(start_year, end_year + 1))
        working_layers = [layer for layer in self._layers if layer.year in result_years]
        with Pool(pool_workers) as pool:
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
        layers_by_year = defaultdict(list)
        pattern = self._pattern
        units = Units.TcPerHa
        if isinstance(self._pattern, tuple):
            pattern, units = self._pattern
            
        for p in ([pattern] if isinstance(pattern, str) else pattern):
            for layer_path in glob(p):
                year = os.path.splitext(layer_path)[0][-4:]
                layer = Layer(layer_path, year, units=units)
                layers_by_year[layer.year].append(layer)

        if not layers_by_year:
            raise IOError(f"No spatial output found for pattern: {p}")

        # Merge the layers together by year if this is a fragmented collection of layers.
        with ThreadPoolExecutor(pool_workers) as pool:
            self._layers = list(pool.map(self._merge_layers, layers_by_year.values()))

    def _merge_layers(self, layers):
        if len(layers) == 1:
            return layers[0]

        output_path = TempFileManager.mktmp(suffix=".tif")
        gdal.SetCacheMax(catplotlib_memory_limit)
        gdal.Warp(output_path, [layer.path for layer in layers], creationOptions=gdal_creation_options)
        merged_layer = Layer(output_path, layers[0].year, layers[0].interpretation, layers[0].units)

        return merged_layer

    def _find_year(self, layers, year):
        return next(filter(lambda layer: layer.year == year, layers), None)
