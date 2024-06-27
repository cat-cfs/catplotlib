import logging
import os
import json
import sqlite3
from glob import glob
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

    def configure(self, study_area_path, dist_type_filter=None, dist_type_substitutions=None,
                  search_prefix=None, min_year=None, max_year=None):
        '''
        Scans the specified study area JSON file for disturbance layers and returns
        a LayerCollection containing them.

        Arguments:
        'study_area_path' -- the path to the study area file to scan.
        'dist_type_filter' -- only include disturbance types in this list (default: all).
        'dist_type_substitutions' -- optional dictionary of original disturbance type names
            to new names.
        'search_prefix' -- only include disturbance layers with name matching this prefix.
        'min_year' -- only include disturbance layers with year greater than or equal to this.
        'max_year' -- only include disturbance layers with year less than or equal to this.
        '''
        if not os.path.exists(study_area_path):
            raise IOError(f"{study_area_path} not found.")

        dist_type_substitutions = dist_type_substitutions or {}

        study_area = json.load(open(study_area_path, "rb"))
        layers = study_area["layers"]
        disturbance_layers = [layer for layer in study_area["layers"]
                              if "disturbance" in layer.get("tags", [])
                              and layer["name"].startswith(search_prefix or "")]
        
        layer_collection = LayerCollection(colorizer=self._colorizer,
                                           background_color=self._background_color)

        study_area_dir = os.path.dirname(study_area_path)
        for layer in disturbance_layers:
            layer_tifs = glob(os.path.join(study_area_dir, f"{layer['name']}_moja.tif*"))
            layer_tif = layer_tifs[0] if layer_tifs else ""

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
                    int(raster_value): dist_type_substitutions.get(
                        attr["disturbance_type"], attr["disturbance_type"])
                    for raster_value, attr in layer_attribute_table.items()
                    if attr["year"] == year
                    and (int(attr["year"]) >= min_year if min_year else True)
                    and (int(attr["year"]) <= max_year if max_year else True)
                    and (attr["disturbance_type"] in dist_type_filter if dist_type_filter else True)}

                if interpretation:
                    layer_collection.append(Layer(layer_tif, year, interpretation, Units.Blank))

        return layer_collection

    def configure_output(self, spatial_results, db_results, dist_type_filter=None,
                         dist_type_substitutions=None, min_year=None, max_year=None,
                         simulation_start_year=None):
        '''
        Uses output of GCBM's optional disturbance monitor module for the disturbances in the
        animation.

        Arguments:
        'spatial_results' -- the path to the simulation's spatial output directory.
        'db_results' -- the path to the simulation's compiled results database.
        'dist_type_filter' -- only include disturbance types in this list (default: all).
        'dist_type_substitutions' -- optional dictionary of original disturbance type names
            to new names.
        'min_year' -- only include disturbance layers with year greater than or equal to this.
        'max_year' -- only include disturbance layers with year less than or equal to this.
        'simulation_start_year' -- the simulation start year, if using multiband output.
        '''
        if not db_results or not os.path.exists(db_results):
            raise IOError(f"Compiled results database not specified or not found.")

        conn = sqlite3.connect(db_results)

        dist_type_substitutions = dist_type_substitutions or {}
        layer_attribute_table = {
            int(k): dist_type_substitutions.get(v, v) for (k, v) in conn.execute(
                """
                SELECT DISTINCT disturbance_code, disturbance_type
                FROM v_total_disturbed_areas
                """
            ) if (v in dist_type_filter if dist_type_filter else True)
        }
        
        layer_collection = LayerCollection(colorizer=self._colorizer,
                                           background_color=self._background_color)

        for layer in filter(
            lambda fn: os.path.splitext(fn)[1] in (".tif", ".tiff"),
            glob(os.path.join(spatial_results, "current_disturbance*.ti*"))
        ):
            logging.info(f"Processing {layer}.")
            if not Layer(layer).is_multiband:
                year = int(os.path.splitext(os.path.basename(layer))[0].rsplit("_", 1)[1])
                if not (
                    (year >= min_year if min_year else True)
                    and (year <= max_year if max_year else True)
                ):
                    continue

                layer_collection.append(Layer(layer, year, layer_attribute_table, Units.Blank))
            else:
                for sublayer in Layer(
                    layer, interpretation=layer_attribute_table, units=Units.Blank,
                    simulation_start_year=simulation_start_year
                ).unpack():
                    if not (
                        (sublayer.year >= min_year if min_year else True)
                        and (sublayer.year <= max_year if max_year else True)
                    ):
                        continue

                    layer_collection.append(sublayer)

        return layer_collection

    def _find_first(self, *paths):
        for path in paths:
            if os.path.exists(path):
                return path

        return None
