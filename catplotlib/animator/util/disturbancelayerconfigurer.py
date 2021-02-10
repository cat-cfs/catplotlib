import os
import json
from catplotlib.animator.color.colorizer import Colorizer
from catplotlib.spatial.layer import Layer
from catplotlib.provider.units import Units
from catplotlib.spatial.layercollection import LayerCollection

class DisturbanceLayerConfigurer:
    '''
    Scans a study_area.json file for disturbance layers, collecting the final
    *_moja.tif files along with their tiled metadata (disturbance type and year),
    splitting them into multiple instances if more than one year is present in a
    file.

    Arguments:
    'colorizer' -- a Colorizer to create the map legend with - defaults to
        basic Colorizer which bins values into equal-sized buckets.
    'background_color' -- RGB tuple for the background color.
    '''
    def __init__(self, colorizer=None, background_color=(224, 224, 224)):
        self._colorizer = colorizer or Colorizer()
        self._background_color = background_color

    def configure(self, study_area_path, dist_type_filter=None):
        '''
        Scans the specified study area JSON file for disturbance layers and returns
        a LayerCollection containing them.

        Arguments:
        'study_area_path' -- the path to the study area file to scan.
        'dist_type_filter' -- only include disturbance types in this list (default: all).
        '''
        if not os.path.exists(study_area_path):
            raise IOError(f"{study_area_path} not found.")

        study_area = json.load(open(study_area_path, "rb"))
        layers = study_area["layers"]
        disturbance_layers = [layer for layer in study_area["layers"]
                              if "disturbance" in layer.get("tags", [])]
        
        layer_collection = LayerCollection(colorizer=self._colorizer,
                                           background_color=self._background_color)

        study_area_dir = os.path.dirname(study_area_path)
        for layer in disturbance_layers:
            layer_tif = os.path.join(study_area_dir, f"{layer['name']}_moja.tiff")
            layer_metadata_file = self._find_first(
                os.path.join(study_area_dir, f"{layer['name']}_moja", f"{layer['name']}_moja.json"),
                os.path.join(study_area_dir, f"{layer['name']}_moja.json"))

            if not os.path.exists(layer_tif) or not layer_metadata_file:
                continue

            layer_attribute_table = json.load(open(layer_metadata_file, "rb")).get("attributes")
            if not layer_attribute_table:
                continue
            
            # If the layer contains multiple years, split it up by year.
            disturbance_years = {attr["year"] for attr in layer_attribute_table.values()}
            for year in disturbance_years:
                interpretation = {
                    int(raster_value): attr["disturbance_type"]
                    for raster_value, attr in layer_attribute_table.items()
                    if attr["year"] == year
                    and (attr["disturbance_type"] in dist_type_filter if dist_type_filter else True)}

                if interpretation:
                    layer_collection.append(Layer(layer_tif, year, interpretation, Units.Blank))

        return layer_collection

    def _find_first(self, *paths):
        for path in paths:
            if os.path.exists(path):
                return path

        return None
