import json
import logging
import pandas as pd
import mojadata.boundingbox as moja
from multiprocessing import Pool
from pandas import DataFrame
from pathlib import Path
from itertools import chain
from collections import defaultdict
from mojadata.cleanup import cleanup
from mojadata.layer.rasterlayer import RasterLayer
from mojadata.layer.vectorlayer import VectorLayer
from mojadata.layer.attribute import Attribute
from mojadata.layer.filter.valuefilter import ValueFilter
from catplotlib.spatial.layer import Layer
from catplotlib.spatial.boundingbox import BoundingBox
from catplotlib.util.cache import get_cache

def load_gcbm_attributes_to_dataframe(layer_path):
    '''
    Loads a GCBM-format tiled layer attribute table into a DataFrame in a format
    suitable for joining to raster data by pixel value.

    Arguments:
    'layer_path' -- the path to a tiled GCBM layer (.tiff)

    Returns the layer's attribute table as a DataFrame indexed by pixel value, or
    an empty DataFrame if the layer has no attribute table.
    '''
    layer_metadata_path = layer_path.with_suffix(".json")
    if not layer_metadata_path.exists():
        return DataFrame({"value": []}).set_index("value")
    
    layer_attribute_table = json.load(open(layer_metadata_path, "rb")).get("attributes")
    if not layer_attribute_table:    
        return DataFrame({"value": []}).set_index("value")

    attributes = (
        set(chain(*(item.keys() for item in layer_attribute_table.values())))
        if isinstance(next(iter(layer_attribute_table.values())), dict)
        else {layer_path.stem}
    )
    
    transformed_attribute_values = defaultdict(list)
    for px, interpretation in layer_attribute_table.items():
        transformed_attribute_values["value"].append(int(px))
        for attr in attributes:
            transformed_attribute_values[attr].append(
                interpretation.get(attr, "null") if isinstance(interpretation, dict)
                else interpretation
            )
            
    df = DataFrame(transformed_attribute_values).set_index("value")
    
    return df
    
def create_bounding_box(bounding_box_path, bounding_box_filter=None, pixel_size=0.001, cache=None):
    '''
    Creates a catplotlib bounding box from a raster or vector layer with an optional
    attribute filter, if using a vector layer.

    Arguments:
    'bounding_box_path' -- path to the raster or vector layer to use as the bounding box
    'bounding_box_filter' -- single-entry dict of layer attribute to filter value
    'pixel_size' -- resolution for the new bounding box, default 0.001 (~1ha)
    'cache' -- catplotlib cache, if calling from another script

    Returns the new catplotlib-format BoundingBox.
    '''
    bounding_box_path = Path(bounding_box_path).absolute()
    layer_args = {"name": "bbox", "path": str(bounding_box_path)}
    if bounding_box_path.suffix in (".tif", ".tiff"):
        moja_bbox = moja.BoundingBox(RasterLayer(**layer_args), pixel_size=pixel_size)
    elif bounding_box_path.suffix == ".shp":
        if bounding_box_filter:
            attr_name, attr_value = next(iter(bounding_box_filter.items()))
            layer_args["attributes"] = Attribute(attr_name, filter=ValueFilter(attr_value))
        
        moja_bbox = moja.BoundingBox(VectorLayer(**layer_args), pixel_size=pixel_size)
    else:
        raise RuntimeError("Unsupported bounding box type")

    with cleanup():
        try:
            moja_bbox.init()
        except:
            # Empty bounding box.
            return None
    
    final_bbox_path = next(Path().glob("bounding_box.ti*"))
    catplotlib_bbox = BoundingBox(str(final_bbox_path), cache=cache)
    
    return catplotlib_bbox

def _process_layer(layer_path, bounding_box=None, cache=None):
    layer_attribute_table = load_gcbm_attributes_to_dataframe(layer_path)
        
    layer = (
        bounding_box.crop(Layer(str(layer_path), 0, cache=cache)) if bounding_box
        else Layer(str(layer_path), 0, cache=cache)
    )
        
    if not Path(layer.path).exists():
        return DataFrame()

    layer_data = (
        layer.summarize()
            .join(layer_attribute_table)
            .reset_index()
            .drop("value", axis=1)
    )

    return layer_data        

def get_area_by_gcbm_attributes(
    pattern, bounding_box_path=None, bounding_box_filter=None,
    output_path="area_by_gcbm_attributes.csv"
):
    '''
    Summarize a stack of rasters by area in hectares and unique combinations of
    pixel and/or attribute values in each layer - NOT an overlay, but can be used,
    for example, to summarize a stack of GCBM disturbance layers into a table of
    area by disturbance type and year.
    
    Will detect and load the tiler attribute table for each layer if present.

    Arguments:
    'pattern' -- layer pattern to search for
    'bounding_box_path' -- optional bounding box path to crop the summary by
    'bounding_box_filter' -- optional attribute filter to apply to the bounding box,
        if using a vector layer; expects a dict with a single entry of attribute name
        to the value to filter by
    'output_path' -- optional path to a csv file to write the results to, or None to
        skip writing to a file
        
    Returns a DataFrame containing the area summary.
    '''
    cache = get_cache()    

    if output_path:
        output_path = Path(output_path)
        output_path.unlink(True)
    
    initial_path = "."
    if "\\" in pattern:
        pattern_root, pattern = pattern.split("\\", 1)
        initial_path = pattern_root + "\\"
        
    layer_paths = list(Path(initial_path).glob(pattern))
    if not layer_paths:
        return DataFrame()
    
    bounding_box = None
    if bounding_box_path:
        layer_resolution = Layer(str(layer_paths[0]), 0, cache=cache).info["geoTransform"][1]
        bounding_box = create_bounding_box(
            bounding_box_path, bounding_box_filter, layer_resolution
        )
        
        if bounding_box is None:
            # Empty bounding box, no data to retrieve.
            return DataFrame()
    
    all_data = DataFrame()
    with Pool() as pool:
        tasks = []
        for layer_path in layer_paths:
            tasks.append(pool.apply_async(
                _process_layer,
                (layer_path, bounding_box, cache)
            ))
        
        pool.close()
        pool.join()
        
        for result in tasks:
            all_data = pd.concat((all_data, result.get()))
            all_data = (
                all_data.groupby([c for c in all_data.columns if c != "area"])
                    .sum()
                    .reset_index()
            )
    
    if output_path:
        all_data.to_csv(output_path, index=False)
    
    return all_data
