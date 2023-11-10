import json
import mojadata.boundingbox as moja
import pandas as pd
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
from catplotlib.util.tempfile import TempFileManager
from catplotlib.util.cache import get_cache

def load_gcbm_attributes_to_dataframe(layer_path):
    layer_metadata_path = layer_path.with_suffix(".json")
    if not layer_metadata_path.exists():
        return DataFrame({"value": []}).set_index("value")
    
    layer_attribute_table = json.load(open(layer_metadata_path, "rb"))["attributes"]
    attributes = set(chain(*(item.keys() for item in layer_attribute_table.values())))
    
    transformed_attribute_values = defaultdict(list)
    for px, interpretation in layer_attribute_table.items():
        transformed_attribute_values["value"].append(int(px))
        for attr in attributes:
            transformed_attribute_values[attr].append(interpretation.get(attr, "null"))
            
    df = DataFrame(transformed_attribute_values).set_index("value")
    
    return df
    
def create_bounding_box(bounding_box_path, bounding_box_filter=None, pixel_size=0.001, cache=None):
    bounding_box_path = Path(bounding_box_path).absolute()
    layer_args = ["bbox", str(bounding_box_path)]
    if bounding_box_path.suffix in (".tif", ".tiff"):
        moja_bbox = moja.BoundingBox(RasterLayer(*layer_args), pixel_size=pixel_size)
    elif bounding_box_path.suffix == ".shp":
        if bounding_box_filter:
            attr_name, attr_value = next(iter(bounding_box_filter.items()))
            layer_args.append(Attribute(attr_name, filter=ValueFilter(attr_value)))
        
        moja_bbox = moja.BoundingBox(VectorLayer(*layer_args), pixel_size=pixel_size)
    else:
        raise RuntimeError("Unsupported bounding box type")

    with cleanup():
        try:
            moja_bbox.init()
        except:
            # Empty bounding box.
            return None
        
    catplotlib_bbox = BoundingBox("bounding_box.tiff", cache=cache)
    
    return catplotlib_bbox

def process_layer(layer_path, bounding_box=None, cache=None):
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
    cache = get_cache()    

    if output_path:
        output_path = Path(output_path)
        output_path.unlink(True)
    
    pattern = Path(pattern)
    layer_paths = list(pattern.parent.glob(pattern.name))
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
                process_layer,
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
