import logging
import json
import sys
import csv
import pandas as pd
from pathlib import Path
from typing import Iterable
from argparse import ArgumentParser
from pandas import DataFrame
from concurrent.futures import ThreadPoolExecutor
from catplotlib.spatial.layer import Layer
from catplotlib.util.overlay import overlay
from catplotlib.util.layersummary import create_bounding_box
from catplotlib.util.tempfile import TempFileManager

def process_overlay_by(layers):
    overlay_result = overlay(layers)
    keep_columns = ["area", *(l for l in layers if l in overlay_result)]
    for layer_name, layer in layers.items():
        if layer.has_interpretation:
            for _, attributes in layer.interpretation.items():
                keep_columns.extend([
                    c for c in attributes
                    if c in overlay_result and c not in keep_columns
                ])
        else:
            keep_columns.extend([
                c for c in overlay_result
                if layer_name in c and c not in keep_columns
            ])

    overlay_result = overlay_result[keep_columns].groupby([
        c for c in keep_columns if "area" not in c
    ]).sum().reset_index()

    return overlay_result

def build_layer(layer_path):
    attribute_table = None
    
    json_metadata_path = layer_path.with_suffix(".json")
    csv_metadata_path = layer_path.with_suffix(".csv")
    if json_metadata_path.exists():
        attributes = json.load(open(json_metadata_path, "rb")).get("attributes")
        if attributes:
            attribute_table = {
                int(k): v for k, v in attributes.items()
            }
    elif csv_metadata_path.exists():
        attribute_table = {
            int(line[0]): line[1]
            for line in csv.reader(open(csv_metadata_path).readlines()[1:])
        }
    
    return Layer(str(layer_path), 0, attribute_table)

def do_overlay(
    layer_paths, by=None, output_path=None,
    bounding_box_path=None, bounding_box_filter=None, bounding_box_resolution=0.001
):
    layer_paths = [layer_paths] if not isinstance(layer_paths, Iterable) else list(layer_paths)
    if by is not None:
        by = [by] if not isinstance(by, Iterable) else list(by)

    bbox = None
    if bounding_box_path:
        bbox = create_bounding_box(bounding_box_path, bounding_box_filter, bounding_box_resolution)
        layers = {layer_path.stem: bbox.crop(build_layer(layer_path)) for layer_path in layer_paths}
        if by:
            by_layers = {layer_path.stem: bbox.crop(build_layer(layer_path)) for layer_path in by}
    else:
        layers = {layer_path.stem: build_layer(layer_path) for layer_path in layer_paths}
        if by:
            by_layers = {layer_path.stem: build_layer(layer_path) for layer_path in by}
    
    if by:
        with ThreadPoolExecutor() as pool:
            tasks = []
            for layer_name, layer in layers.items():
                overlay_layers = by_layers.copy()
                overlay_layers[layer_name] = layer
                tasks.append(pool.submit(process_overlay_by, overlay_layers))
        
            results = [task.result() for task in tasks]
    
        result = DataFrame()
        for layer_result in results:
            result = pd.concat([result, layer_result])
            result = result.groupby([
                c for c in result if "area" not in c
            ], dropna=False).sum().reset_index()
    else:
        result = overlay(layers)
        
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
    
    return result

def _find_layers(pattern):
    initial_path = "."
    if "\\" in pattern:
        pattern_root, pattern = pattern.split("\\", 1)
        initial_path = pattern_root + "\\"
        
    input_layers = list(Path(initial_path).glob(pattern))
    
    return input_layers

def cli():
    TempFileManager.delete_on_exit()

    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(message)s", datefmt="%m/%d %H:%M:%S")

    parser = ArgumentParser(description="Overlay layers and create a summary of area by attribute combinations.")
    parser.add_argument("output_path", type=Path, help="Path to csv file to write results to")
    parser.add_argument("layers", nargs="+", help="Paths to raster layers to overlay")
    parser.add_argument("--by", type=Path, nargs="*",
                        help="Optional layers to overlay each of the layers in the 'layers' list by to form a "
                             "long result (consolidated by common columns) instead of a wide one")
    parser.add_argument("--bounding_box", help="Optional bounding box to crop layers to")
    parser.add_argument("--bounding_box_filter", help="Filter for bounding box, if using a vector layer, in the format `attr:value`")
    parser.add_argument("--pixel_size", help="Resolution for bounding box", default=0.001)
    args = parser.parse_args()
    
    bbox_filter = None
    if args.bounding_box:
        bbox_filter_values = args.bounding_box_filter.split(":") if args.bounding_box_filter else None
        bbox_filter = {bbox_filter_values[0]: bbox_filter_values[1]} if bbox_filter_values else None
    
    layers = []
    for pattern in args.layers:
        layers.extend(_find_layers(pattern))

    do_overlay(layers, args.by, args.output_path, args.bounding_box, bbox_filter, args.pixel_size)

if __name__ == "__main__":
    cli()
