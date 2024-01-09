import logging
import json
import sys
import csv
from pathlib import Path
from argparse import ArgumentParser
from catplotlib.spatial.layer import Layer
from catplotlib.util.overlay import overlay
from catplotlib.util.layersummary import get_area_by_gcbm_attributes
from catplotlib.util.tempfile import TempFileManager

def cli():
    TempFileManager.delete_on_exit()

    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(message)s", datefmt="%m/%d %H:%M:%S")

    parser = ArgumentParser(description="Summarize layers by attribute combinations and area.")
    parser.add_argument("pattern", help="Layer pattern to summarize")
    parser.add_argument("--output_path", help="Path to csv file to write results to")
    parser.add_argument("--bounding_box", help="Optional bounding box to crop layers to")
    parser.add_argument("--bounding_box_filter", help="Filter for bounding box, if using a vector layer, in the format `attr:value`")
    args = parser.parse_args()
    
    result = get_area_by_gcbm_attributes(
        args.pattern, args.bounding_box, args.bounding_box_filter, args.output_path
    )
    
    if not args.output_path:
        print(result)

if __name__ == "__main__":
    cli()
