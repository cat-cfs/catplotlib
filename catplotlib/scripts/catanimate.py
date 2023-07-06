import os
import sys
import json
import logging
import site
from glob import glob
from argparse import ArgumentParser
from catplotlib.util import localization
from catplotlib.animator.util.disturbancelayerconfigurer import DisturbanceLayerConfigurer
from catplotlib.provider.sqlitegcbmresultsprovider import SqliteGcbmResultsProvider
from catplotlib.provider.spatialgcbmresultsprovider import SpatialGcbmResultsProvider
from catplotlib.animator.indicator.indicator import Indicator
from catplotlib.spatial.layer import Layer
from catplotlib.provider.units import Units
from catplotlib.animator.boxlayoutanimator import BoxLayoutAnimator
from catplotlib.spatial.boundingbox import BoundingBox
from catplotlib.animator.color.colorizer import Colorizer
from catplotlib.animator.color.quantilecolorizer import QuantileColorizer
from catplotlib.animator.color.customcolorizer import CustomColorizer
from catplotlib.util.tempfile import TempFileManager
from catplotlib.util.utmzones import find_best_projection

def find_units(units_str):
    try:
        return Units[units_str]
    except:
        return Units.Tc

def cli():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    TempFileManager.delete_on_exit()

    parser = ArgumentParser(description="Create GCBM results animations")
    parser.add_argument("output_path", type=os.path.abspath, help="Directory to write animations to")
    parser.add_argument("spatial_results", type=os.path.abspath, help="Path to GCBM spatial output")
    parser.add_argument("study_area", nargs="+", help="Path to study area file(s) for GCBM spatial input")
    parser.add_argument("--db_results", type=os.path.abspath, help="Path to compiled GCBM results database")
    parser.add_argument("--bounding_box", type=os.path.abspath, help="Bounding box defining animation area")
    parser.add_argument("--config", type=os.path.abspath, help="Path to animation config file", default="indicators.json")
    parser.add_argument("--disturbance_colors", type=os.path.abspath, help="Path to disturbance color config file")
    parser.add_argument("--filter_disturbances", action="store_true", help="Limit disturbances to types in color config file", default=False)
    parser.add_argument("--locale", help="Switch locale for generated animations")
    args = parser.parse_args()

    indicator_config_path = None
    for config_path in (
        args.config,
        os.path.join(site.USER_BASE, "Tools", "catplotlib", "catanimate", "indicators.json"),
        os.path.join(sys.prefix, "Tools", "catplotlib", "catanimate", "indicators.json"),
    ):
        if os.path.exists(config_path):
            indicator_config_path = config_path
            break

    if not indicator_config_path:
        sys.exit("Indicator configuration file not found.")

    for path in filter(lambda fn: fn, (*args.study_area, args.spatial_results, args.db_results)):
        if not os.path.exists(path):
            sys.exit(f"{path} not found.")
    
    if args.locale:
        localization.switch(args.locale)

    bounding_box_file = args.bounding_box
    if not bounding_box_file:
        # Try to find a suitable bounding box: the tiler bounding box is usually
        # the only tiff file in the study area directory without "moja" in its name;
        # if that isn't found, use the first tiff file in the study area dir.
        study_area_dir = os.path.dirname(args.study_area[0])
        bounding_box_candidates = glob(os.path.join(study_area_dir, "*.tif['', 'f']"))
        bounding_box_file = next(filter(lambda tiff: "moja" not in tiff, bounding_box_candidates), None)
        if not bounding_box_file:
            bounding_box_file = os.path.abspath(bounding_box_candidates[0])

    logging.info(f"Using bounding box: {bounding_box_file}")
    bounding_box = BoundingBox(bounding_box_file, find_best_projection(Layer(bounding_box_file, 0)))

    disturbance_colorizer = None
    disturbance_filter = []
    disturbance_substitutions = {}
    if args.disturbance_colors:
        dist_color_config = json.load(open(args.disturbance_colors, "rb"))
        colorizer_config = {
            (item.get("label"),) or tuple(item["disturbance_types"]):
                item["palette"] for item in dist_color_config}

        disturbance_colorizer = CustomColorizer(colorizer_config)
        for item in dist_color_config:
            label = item.get("label")
            if label:
                for dist_type in item["disturbance_types"]:
                    disturbance_substitutions[dist_type] = label

            if args.filter_disturbances:
                disturbance_filter.extend(item["disturbance_types"])

    disturbance_configurer = DisturbanceLayerConfigurer(disturbance_colorizer)
    disturbance_layers = None
    for study_area in args.study_area:
        study_area_disturbance_layers = disturbance_configurer.configure(
            os.path.abspath(study_area), disturbance_filter, disturbance_substitutions)

        if disturbance_layers is None:
            disturbance_layers = study_area_disturbance_layers
        else:
            disturbance_layers.merge(study_area_disturbance_layers)

    indicators = []
    for indicator_config in json.load(open(indicator_config_path, "rb")):
        graph_units = find_units(indicator_config["graph_units"]) if "graph_units" in indicator_config else Units.Tc
        map_units = find_units(indicator_config["map_units"]) if "map_units" in indicator_config else Units.TcPerHa

        output_file_pattern = indicator_config["file_pattern"]
        output_file_units = Units.TcPerHa
        if isinstance(output_file_pattern, list):
            output_file_pattern, output_file_units = output_file_pattern
            output_file_units = find_units(output_file_units)

        output_file_pattern = os.path.join(args.spatial_results, output_file_pattern)

        results_provider = SqliteGcbmResultsProvider(args.db_results) if args.db_results and not args.bounding_box \
            else SpatialGcbmResultsProvider((output_file_pattern, output_file_units))

        colorizer = None
        interpretation = indicator_config.get("interpretation")
        if interpretation:
            interpretation = {int(k): v for k, v in interpretation.items()}
            color_config = indicator_config.get("colors", [])
            colorizer_config = {tuple(item["values"]): item["palette"] for item in color_config}
            colorizer = CustomColorizer(colorizer_config, palette=indicator_config.get("palette"))
        else:
            use_quantiles = indicator_config.get("use_quantiles", True)
            colorizer = QuantileColorizer(
                palette=indicator_config.get("palette"),
                negative_palette=indicator_config.get("negative_palette")
            ) if use_quantiles else Colorizer(indicator_config.get("palette"))

        indicators.append(Indicator(
            indicator_config.get("database_indicator") or indicator_config.get("title"),
            (output_file_pattern, output_file_units),
            results_provider, {"indicator": indicator_config.get("database_indicator")},
            indicator_config.get("title"),
            graph_units, map_units,
            colorizer=colorizer,
            interpretation=interpretation))

    animator = BoxLayoutAnimator(disturbance_layers, indicators, args.output_path)
    animator.render(bounding_box)

if __name__ == "__main__":
    cli()
