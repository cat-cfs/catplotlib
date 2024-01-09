import logging
import json
import sys
import csv
from pathlib import Path
from argparse import ArgumentParser
from catplotlib.spatial.layer import Layer
from catplotlib.util.overlay import overlay
from catplotlib.util.layersummary import create_bounding_box
from catplotlib.util.tempfile import TempFileManager

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

def cli():
    TempFileManager.delete_on_exit()

    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(message)s", datefmt="%m/%d %H:%M:%S")

    parser = ArgumentParser(description="Overlay layers and create a summary of area by attribute combinations.")
    parser.add_argument("output_path", type=Path, help="Path to csv file to write results to")
    parser.add_argument("layers", type=Path, nargs="+", help="Paths to raster layers to overlay")
    parser.add_argument("--bounding_box", help="Optional bounding box to crop layers to")
    parser.add_argument("--bounding_box_filter", help="Filter for bounding box, if using a vector layer, in the format `attr:value`")
    parser.add_argument("--pixel_size", help="Resolution for bounding box", default=0.001)
    args = parser.parse_args()
    
    layers = {}
    bbox = None
    if args.bounding_box:
        bbox_filter_values = args.bounding_box_filter.split(":") if args.bounding_box_filter else None
        bbox_filter = {bbox_filter_values[0]: bbox_filter_values[1]} if bbox_filter_values else None
        bbox = create_bounding_box(args.bounding_box, bbox_filter, args.pixel_size)
        layers = {layer_path.stem: bbox.crop(build_layer(layer_path)) for layer_path in args.layers}
    else:
        layers = {layer_path.stem: build_layer(layer_path) for layer_path in args.layers}
    
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay(layers).to_csv(args.output_path, index=False)

if __name__ == "__main__":
    cli()
