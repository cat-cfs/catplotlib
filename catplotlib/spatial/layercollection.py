import os
import shutil
from itertools import chain
from collections import defaultdict
from multiprocessing import Pool
from catplotlib.util import gdal
from catplotlib.spatial.layer import Layer
from catplotlib.provider.units import Units
from catplotlib.spatial.layer import BlendMode
from catplotlib.animator.color.colorizer import Colorizer
from catplotlib.spatial.display.frame import Frame
from catplotlib.util.config import gdal_creation_options
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.config import pool_workers
from catplotlib.util.tempfile import TempFileManager

class LayerCollection:
    '''
    A collection of Layer objects that belong together in an animation. The layers
    in the collection should be generally related, i.e. a collection of interpreted
    layers along the same theme (disturbances), or a collection of value layers for
    the same indicator (NPP, ...).

    Layers in the collection can be for different years - when the collection is
    rendered, the layers will be merged together by year, and each year will
    become a separate Frame object.

    Arguments:
    'layers' -- a list of Layer objects to include in the collection.
    'background_color' -- RGB tuple for the background color.
    'colorizer' -- a Colorizer to create the legend with - defaults to
        basic Colorizer which bins values into 8 equal-sized buckets.
    '''

    def __init__(self, layers=None, background_color=(224, 224, 224), colorizer=None):
        self._layers = layers or []
        self._background_color = background_color
        self._colorizer = colorizer or Colorizer()

    @property
    def empty(self):
        '''Checks if this collection is empty.'''
        return not self._layers

    @property
    def layers(self):
        '''Gets the layers in this collection.'''
        return list(self._layers)

    def append(self, layer):
        '''Appends a layer to the collection.'''
        self._layers.append(layer)

    def merge(self, other):
        '''Merges another LayerCollection's layers into this one.'''
        self._layers.extend(other._layers)

    def save_copy(self, path, base_name=None):
        '''Saves the (potentially temporary) layers in this collection to a new path.'''
        os.makedirs(path, exist_ok=True)
        for layer in self._layers:
            output_filename = os.path.basename(layer.path) if not base_name \
                else f"{base_name}_{layer.year}.tif"

            abs_output_filename = os.path.join(path, output_filename)
            if os.path.exists(abs_output_filename):
                os.remove(abs_output_filename)

            shutil.copyfile(layer.path, abs_output_filename)

    def convert_units(self, units, area_only=False):
        '''
        Converts the units in this collection's layers to a new type.
        
        Arguments:
        'units' -- the units to convert to.
        'area_only' -- only perform per-hectare <-> per-pixel conversion
        '''
        return LayerCollection([layer.convert_units(units, area_only) for layer in self._layers],
                               self._background_color, self._colorizer)

    def blend(self, *collections):
        '''
        Blends this collection's layer values with one or more other collections.

        Arguments:
        'collections' -- one or more other LayerCollections to blend paired with
            the blend mode, i.e.
            some_layers.blend(layers_a, BlendMode.Add, layers_b, BlendMode.Subtract)
        '''
        blend_collections = list(zip(collections[::2], collections[1::2]))
        blended_collection = LayerCollection(background_color=self._background_color, colorizer=self._colorizer)

        years = set(chain(
            (layer.year for layer in self._layers),
            *[(layer.year for layer in collection._layers) for collection, _ in blend_collections]))

        for year in years:
            local_layers = list(filter(lambda layer: layer.year == year, self._layers))
            if len(local_layers) > 1:
                raise RuntimeError("Cannot blend collections containing more than one layer per year.")

            if local_layers:
                local_layer = local_layers[0]
            else:
                placeholder = self._layers[0].flatten(0, True) if self._layers \
                    else next(chain(*(collection._layers for collection, _ in blend_collections))).flatten(0, True)

                local_layer = Layer(placeholder.path, year, placeholder.interpretation, placeholder.units)
            
            other_layers = []
            for collection, blend_mode in blend_collections:
                for layer in filter(lambda layer: layer.year == year, collection._layers):
                    other_layers.extend([layer, blend_mode])

            if not other_layers:
                blended_collection.append(local_layer)
            else:
                blended_layer = local_layer.blend(*other_layers)
                blended_collection.append(blended_layer)

        return blended_collection

    def normalize(self):
        '''
        For collections of interpreted layers where pixel values are associated
        with an attribute table, normalize the pixel values across all of the
        layers so that the same pixel values always point to the same attribute
        values.

        Returns a new LayerCollection where the pixel values have been made
        consistent across all layers.
        '''
        interpreted = any((layer.has_interpretation for layer in self.layers))
        if not interpreted:
            return self

        with Pool(pool_workers) as pool:
            unique_values = sorted(set(chain(*(layer.interpretation.values() for layer in self.layers))))
            common_interpretation = {i: value for i, value in enumerate(unique_values, 1)}
            tasks = [pool.apply_async(layer.reclassify, (common_interpretation,)) for layer in self.layers]
            reclassified_layers = [task.get() for task in tasks]

            return LayerCollection(reclassified_layers, self._background_color, self._colorizer)

    def render(self, bounding_box=None, start_year=None, end_year=None, units=Units.TcPerHa):
        '''
        Renders the collection of layers into colorized Frame objects organized
        by year.

        Arguments:
        'bounding_box' -- optional bounding box Layer; rendered layers in this
            collection will be cropped to the bounding box's minimum spatial extent
            and nodata pixels. The bounding box also has its data values flattened
            to grey and becomes the background layer.
        'start_year' -- optional start year to render from - must be specified
            along with end_year.
        'end_year' -- optional end year to render to - must be specified along
            with start_year.
        'units' -- optional units to render the output in (default: tc/ha). Layers
            in the collection will be converted to these units if necessary.
        
        Returns a list of rendered Frame objects and a legend (dict) describing
        the colors.
        '''
        with Pool(pool_workers) as pool:
            layer_years = {layer.year for layer in self._layers}
            render_years = set(range(start_year, end_year + 1)) if start_year and end_year else layer_years
            working_layers = [layer for layer in self._layers if layer.year in render_years]

            pre_crop = bounding_box and bounding_box.px_area < working_layers[0].px_area
            if bounding_box and pre_crop:
                working_layers = pool.map(bounding_box.crop, working_layers)

            tasks = [pool.apply_async(layer.convert_units, (units,)) for layer in working_layers]
            working_layers = [task.get() for task in tasks]

            common_interpretation = None
            interpreted = any((layer.has_interpretation for layer in working_layers))
            if interpreted:
                # Interpreted layers where the pixel values have meaning, i.e. a disturbance type,
                # get their pixel values normalized across the whole collection.
                unique_values = sorted(set(chain(*(layer.interpretation.values() for layer in working_layers))))
                common_interpretation = {i: value for i, value in enumerate(unique_values, 1)}
                tasks = [pool.apply_async(layer.reclassify, (common_interpretation,)) for layer in working_layers]
                working_layers = [task.get() for task in tasks]

            # Merge the layers together by year if this is a fragmented collection of layers,
            # i.e. fire and harvest in separate files.
            layers_by_year = defaultdict(list)
            for layer in working_layers:
                layers_by_year[layer.year].append(layer)

            # Merge groups of layers by year.
            working_layers = list(map(self._merge_layers, layers_by_year.values()))
            if bounding_box and not pre_crop:
                working_layers = pool.map(bounding_box.crop, working_layers)

            legend = self._colorizer.create_legend(working_layers)

            # Render the merged layers.
            tasks = [pool.apply_async(layer.render, (legend,)) for layer in working_layers]
            rendered_layers = [task.get() for task in tasks]

            # Add the background to the rendered layers.
            background_layer = bounding_box or working_layers[0]
            background_frame = background_layer.flatten().render(
                {1: {"color": self._background_color}}, bounding_box=bounding_box, transparent=False)

            rendered_layers = [layer.composite(background_frame, True) for layer in rendered_layers]

            missing_years = render_years - layer_years
            rendered_layers.extend([
                Frame(year, background_frame.path, background_frame.scale)
                for year in missing_years])
        
            return rendered_layers, legend

    def _merge_layers(self, layers):
        if len(layers) == 1:
            return layers[0]

        output_path = TempFileManager.mktmp(suffix=".tif")
        gdal.SetCacheMax(gdal_memory_limit)
        gdal.Warp(output_path, [layer.path for layer in layers], creationOptions=gdal_creation_options)
        merged_layer = Layer(output_path, layers[0].year, layers[0].interpretation, layers[0].units)

        return merged_layer
