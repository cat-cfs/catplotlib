import json
import mojadata.boundingbox as moja
import pandas as pd
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

def load_gcbm_attributes_to_dataframe(layer_path):
    layer_metadata_path = layer_path.with_suffix(".json")
    layer_attribute_table = json.load(open(layer_metadata_path, "rb"))["attributes"]
    attributes = set(chain(*(item.keys() for item in layer_attribute_table.values())))
    
    transformed_attribute_values = defaultdict(list)
    for px, interpretation in layer_attribute_table.items():
        transformed_attribute_values["value"].append(int(px))
        for attr in attributes:
            transformed_attribute_values[attr].append(interpretation.get(attr, "null"))
            
    df = DataFrame(transformed_attribute_values).set_index("value")
    
    return df
    
def create_bounding_box(bounding_box_path, bounding_box_filter=None, pixel_size=0.001):
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
        moja_bbox.init()
        
    catplotlib_bbox = BoundingBox("bounding_box.tiff")
    
    return catplotlib_bbox

def get_area_by_gcbm_attributes(
    pattern, bounding_box_path=None, bounding_box_filter=None,
    output_path="area_by_gcbm_attributes.csv"
):
    TempFileManager.delete_on_exit()
    if output_path:
        output_path = Path(output_path)
        output_path.unlink(True)
    
    pattern = Path(pattern)
    layer_paths = list(pattern.parent.glob(pattern.name))
    
    if bounding_box_path:
        layer_resolution = Layer(str(layer_paths[0]), 0).info["geoTransform"][1]
        bounding_box = create_bounding_box(
            bounding_box_path, bounding_box_filter, layer_resolution
        )
    
    all_data = DataFrame()
    for layer_path in layer_paths:
        layer_attribute_table = load_gcbm_attributes_to_dataframe(layer_path)
        
        layer = (
            bounding_box.crop(Layer(str(layer_path), 0)) if bounding_box_path
            else Layer(str(layer_path), 0)
        )
        
        layer_data = (
            layer.summarize()
                 .join(layer_attribute_table)
                 .reset_index()
                 .drop("value", axis=1)
        )

        all_data = pd.concat((all_data, layer_data))
        all_data = (
            all_data.groupby([c for c in all_data.columns if c != "area"])
                .sum()
                .reset_index()
        )
    
    if output_path:
        all_data.to_csv(output_path, index=False)
    
    return all_data
