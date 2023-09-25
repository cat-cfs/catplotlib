import os
import logging
import pandas as pd
from collections import defaultdict
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from glob import glob
from multiprocessing import Pool
from catplotlib.util import gdal
from catplotlib.animator.color.colorizer import Colorizer
from catplotlib.provider.units import Units
from catplotlib.provider.resultsprovider import ResultsProvider
from catplotlib.spatial.layer import Layer
from catplotlib.spatial.display.frame import Frame
from catplotlib.animator.plot.basicresultsplot import BasicResultsPlot
from catplotlib.util.config import pool_workers
from catplotlib.util.config import gdal_creation_options
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.tempfile import TempFileManager

class SpatialIndicator(ResultsProvider):
    '''
    Defines an ecosystem indicator from the GCBM results to render into colorized
    Frame objects using only GCBM output spatial layers.

    Arguments:
    'indicator' -- the short name of the indicator.
    'layer_pattern' -- a file pattern (including directory path) or list of
        patterns in glob format to find the spatial outputs for the indicator,
        i.e. "c:\\my_run\\NPP_*.tif". Can also be specified as a tuple of
        (file pattern or list of patterns, Units) to specify the native units
        of the layers (i.e. Units.Tc) - otherwise the default of Units.TcPerHa
        is used.
    'title' -- the indicator title for presentation - uses the indicator name if
        not provided.
    'graph_units' -- a Units enum value for the graph units - result values will
        be converted to these units. If set to Units.Blank, a graph will not be
        rendered.
    'map_units' -- a Units enum value for the map units - spatial output values
        will be converted to the target units if necessary.
    'background_color' -- the background (bounding box) color to use for the map
        frames.
    'colorizer' -- a Colorizer to create the map legend with - defaults to
        basic Colorizer which bins values into equal-sized buckets.
    '''

    def __init__(self, indicator, layer_pattern, title=None, graph_units=Units.Tc,
                 map_units=Units.TcPerHa, background_color=(255, 255, 255),
                 colorizer=None):
        self._indicator = indicator
        self._layer_pattern = layer_pattern
        self._title = title or indicator
        self._graph_units = graph_units or Units.Tc
        self._map_units = map_units or Units.TcPerHa
        self._background_color = background_color
        self._colorizer = colorizer or Colorizer()
        self._last_bbox_path = None
        self._layers = None
        self._cropped_layers = None

    @property
    def title(self):
        '''Gets the indicator title.'''
        return self._title

    @property
    def indicator(self):
        '''Gets the short title for the indicator.'''
        return self._indicator

    @property
    def map_units(self):
        '''Gets the Units for the spatial output.'''
        return self._map_units
    
    @property
    def graph_units(self):
        '''Gets the Units for the graphed/non-spatial output.'''
        return self._graph_units

    @property
    def simulation_years(self):
        '''Gets the years present in the simulation.'''
        layers = self._prepare_layers()

        return min((l.year for l in layers)), max((l.year for l in layers))
    
    def render_map_frames(self, bounding_box=None, start_year=None, end_year=None):
        '''
        Renders the indicator's spatial output into colorized Frame objects.

        Arguments:
        'bounding_box' -- optional bounding box Layer; spatial output will be
            cropped to the bounding box's minimum spatial extent and nodata pixels.

        Returns a list of colorized Frames, one for each year of output, and a
        legend in dictionary format describing the colors.
        '''
        logging.info(f"{self.title}: rendering map frames")
        layers = self._prepare_layers(bounding_box)
        
        layer_years = {layer.year for layer in layers}
        render_years = set(range(start_year, end_year + 1)) if start_year and end_year else layer_years
        working_layers = [layer for layer in layers if layer.year in render_years]

        legend = self._colorizer.create_legend(working_layers)

        logging.info("    rendering layers")
        with Pool(pool_workers) as pool:
            tasks = [pool.apply_async(layer.render, (legend,)) for layer in working_layers]
            rendered_layers = [task.get() for task in tasks]

            # Add the background to the rendered layers.
            background_layer = bounding_box or working_layers[0]
            background_frame = background_layer.flatten().render(
                {1: {"color": self._background_color}}, bounding_box=bounding_box, transparent=False)

            logging.info("    compositing output with background layer")
            rendered_layers = [layer.composite(background_frame, True) for layer in rendered_layers]

            missing_years = render_years - layer_years
            rendered_layers.extend([
                Frame(year, background_frame.path, background_frame.scale)
                for year in missing_years])
            
            return rendered_layers, legend

    def render_graph_frames(self, start_year=None, end_year=None, **kwargs):
        '''
        Renders the indicator's non-spatial output into a graph.

        Arguments:
        Any accepted by GCBMResultsProvider and subclasses.

        Returns a list of Frames, one for each year of output.
        '''
        if self._graph_units == Units.Blank:
            return None

        plot = BasicResultsPlot(self._indicator, self, self._graph_units)
        logging.info(f"{self.title}: rendering graph frames")

        return plot.render(start_year=start_year, end_year=end_year, **kwargs)
    
    def get_annual_result(self, indicator, start_year=None, end_year=None,
                          units=Units.Tc, bounding_box=None, **kwargs):
        '''See ResultsProvider.get_annual_result.'''
        layers = self._prepare_layers(bounding_box)

        if not start_year or not end_year:
            start_year, end_year = self.simulation_years

        result_years = list(range(start_year, end_year + 1))
        working_layers = [layer for layer in layers if layer.year in result_years]
        with Pool(pool_workers) as pool:
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

    def _prepare_layers(self, bounding_box=None):
        if not self._layers:
            logging.info("Preparing layers")
            self._find_layers()
    
        if not bounding_box:
            logging.info("Using cached base layers")
            return self._layers
        
        if self._cropped_layers and bounding_box.path == self._last_bbox_path:
            logging.info("Using cached cropped layers")
            return self._cropped_layers
    
        logging.info("Preparing cropped layers")
        with Pool(pool_workers) as pool:
            self._cropped_layers = pool.map(bounding_box.crop, self._layers)
            self._last_bbox_path = bounding_box.path
        
        return self._cropped_layers

    def _find_layers(self):
        layers_by_year = defaultdict(list)
        units = Units.TcPerHa
        if isinstance(self._layer_pattern, tuple):
            pattern, units = self._layer_pattern
            
        for pattern in ([pattern] if isinstance(pattern, str) else pattern):
            for layer_path in glob(pattern):
                year = os.path.splitext(layer_path)[0][-4:]
                layer = Layer(layer_path, year, units=units)
                layers_by_year[layer.year].append(layer)

        if not layers_by_year:
            raise IOError(f"No spatial output found for pattern: {self._layer_pattern}")

        # Merge the layers together by year if this is a fragmented collection of layers.
        with ThreadPoolExecutor(pool_workers) as pool:
            self._layers = list(pool.map(self._merge_layers, layers_by_year.values()))

    def _merge_layers(self, layers):
        if len(layers) == 1:
            return layers[0]

        output_path = TempFileManager.mktmp(suffix=".tif")
        gdal.SetCacheMax(gdal_memory_limit)
        gdal.Warp(output_path, [layer.path for layer in layers], creationOptions=gdal_creation_options)
        merged_layer = Layer(output_path, layers[0].year, layers[0].interpretation, layers[0].units)

        return merged_layer

    def _find_year(self, layers, year):
        return next(filter(lambda layer: layer.year == year, layers), None)
