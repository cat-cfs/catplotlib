import os
import logging
from pathlib import Path
from glob import glob
from multiprocessing import Pool
from catplotlib.animator.indicator.indicator import Indicator
from catplotlib.provider.units import Units
from catplotlib.provider.spatialgcbmresultsprovider import SpatialGcbmResultsProvider
from catplotlib.animator.plot.basicresultsplot import BasicResultsPlot
from catplotlib.spatial.layercollection import LayerCollection
from catplotlib.spatial.layer import Layer
from catplotlib.util.config import pool_workers

class CompositeIndicator(Indicator):
    '''
    A spatial-only indicator that combines multiple GCBM outputs into a single one,
    i.e. all of the components that make up NBP into NBP.

    Arguments:
    'indicator' -- the short name of the indicator.
    'patterns' -- a dictionary of file pattern (including directory path) in glob
        format to blend mode, where the file pattern is used to find the spatial
        outputs for an indicator, i.e. "c:\\my_run\\NPP_*.tif", and the blend mode
        is used to combine the indicator into a composite value.
    'title' -- the indicator title for presentation - uses the indicator name if
        not provided.
    'graph_units' -- a Units enum value for the graph units - result values will
        be converted to these units.
    'map_units' -- a Units enum value for the map units - spatial output values
        will be converted to these units.
    'background_color' -- the background (bounding box) color to use for the map
        frames.
    'colorizer' -- a Colorizer to create the map legend with - defaults to
        simple Colorizer which bins values into equal-sized buckets.
    'simulation_start_year' -- if using multiband layers, the year that band 1
        (timestep 1) corresponds to.
    '''

    def __init__(self, indicator, patterns, title=None, graph_units=Units.Tc,
                 map_units=Units.TcPerHa, background_color=(255, 255, 255), colorizer=None,
                 simulation_start_year=None):

        super().__init__(indicator, None, None, None, title, graph_units, map_units,
                         background_color, colorizer)

        self._patterns = patterns
        self._composite_layers = None
        self._simulation_start_year = simulation_start_year

    def render_map_frames(self, bounding_box=None, start_year=None, end_year=None):
        '''
        Renders the indicator's spatial output into colorized Frame objects.

        Arguments:
        'bounding_box' -- optional bounding box Layer; spatial output will be
            cropped to the bounding box's minimum spatial extent and nodata pixels.

        Returns a list of colorized Frames, one for each year of output, and a
        legend in dictionary format describing the colors.
        '''
        self._init(bounding_box)
        if not start_year or not end_year:
            start_year, end_year = self._results_provider.simulation_years
        
        return self._composite_layers.render(bounding_box, start_year, end_year, self._map_units)

    def render_graph_frames(self, start_year=None, end_year=None, **kwargs):
        '''
        Renders the indicator's non-spatial output into a graph.

        Arguments:
        Any accepted by GCBMResultsProvider and subclasses.

        Returns a list of Frames, one for each year of output.
        '''
        self._init(**kwargs)
        plot = BasicResultsPlot(self._indicator, self._results_provider, self._graph_units)
        
        return plot.render(start_year=start_year, end_year=end_year, **kwargs)

    def _init(self, bounding_box=None, **kwargs):
        if not self._composite_layers:
            self._composite_layers = LayerCollection(
                background_color=self._background_color, colorizer=self._colorizer)

            layer_collections = []
            for pattern, blend_mode in self._patterns.items():
                layer_collections.extend([self._find_layers(pattern, bounding_box), blend_mode])

            self._composite_layers = self._composite_layers.blend(*layer_collections)
            self._results_provider = SpatialGcbmResultsProvider(layers=self._composite_layers.layers)
       
    def _find_layers(self, pattern, bounding_box=None):
        units = Units.TcPerHa
        if isinstance(pattern, tuple):
            pattern, units = pattern

        layers = []
        with Pool(pool_workers) as pool:
            tasks = []
            for layer_path in glob(pattern):
                if not Layer(layer_path).is_multiband:
                    year = Path(layer_path).stem.rsplit("_", 1)[1]
                    layer = Layer(layer_path, year, units=units)
                    if bounding_box:
                        tasks.append(pool.apply_async(bounding_box.crop, (layer,)))
                    else:
                        layers.append(layer)
                else:
                    layer = Layer(layer_path, simulation_start_year=self._simulation_start_year, units=units)
                    for sublayer in layer.unpack():
                        if bounding_box:
                            tasks.append(pool.apply_async(bounding_box.crop, (sublayer,)))
                        else:
                            layers.append(sublayer)
            
            layers.extend((task.get() for task in tasks))

        if not layers:
            logging.warning(f"No spatial output found for pattern: {pattern}")

        layer_collection = LayerCollection(layers, self._background_color)

        return layer_collection
