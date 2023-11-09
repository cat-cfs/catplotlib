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
from catplotlib.animator.indicator.spatialindicator import SpatialIndicator
from catplotlib.spatial.layer import Layer
from catplotlib.provider.units import Units
from catplotlib.animator.boxlayoutanimator import BoxLayoutAnimator
from catplotlib.spatial.boundingbox import BoundingBox
from catplotlib.animator.color.colorizer import Colorizer
from catplotlib.animator.color.quantilecolorizer import QuantileColorizer
from catplotlib.animator.color.customcolorizer import CustomColorizer
from catplotlib.util.config import gdal_creation_options
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.tempfile import TempFileManager
from catplotlib.util.utmzones import find_best_projection
from catplotlib.util import gdal

class Simulation:

    def __init__(self, study_areas, spatial_output_path, db_output_path=None, bounding_box=None):
        self.study_areas = [study_areas] if isinstance(study_areas, str) else study_areas
        self.db_output_path = db_output_path
        self.spatial_output_path = spatial_output_path
        self.bounding_box = bounding_box

        for path in filter(lambda fn: fn, (
            *self.study_areas, self.spatial_output_path, self.db_output_path
        )):
            if path and not os.path.exists(path):
                raise IOError(f"{path} not found.")

def find_units(units_str):
    try:
        return Units[units_str]
    except:
        return Units.Tc

def load_indicators(simulations, indicator_config_path=None, use_db_results=True):
    for config_path in (
        indicator_config_path,
        os.path.join(site.USER_BASE, "Tools", "catplotlib", "catanimate", "indicators.json"),
        os.path.join(sys.prefix, "Tools", "catplotlib", "catanimate", "indicators.json"),
    ):
        if os.path.exists(config_path):
            indicator_config_path = config_path
            break

    if not indicator_config_path:
        sys.exit("Indicator configuration file not found.")

    indicators = []
    for indicator_config in json.load(open(indicator_config_path, "rb")):
        graph_units = find_units(indicator_config["graph_units"]) if "graph_units" in indicator_config else Units.Tc
        map_units = find_units(indicator_config["map_units"]) if "map_units" in indicator_config else Units.TcPerHa

        output_file_pattern = indicator_config["file_pattern"]
        output_file_units = Units.TcPerHa
        if isinstance(output_file_pattern, list):
            output_file_pattern, output_file_units = output_file_pattern
            output_file_units = find_units(output_file_units)

        output_file_patterns = (
            [os.path.join(simulations[0].spatial_output_path, output_file_pattern)] if len(simulations) == 1
            else [os.path.join(sim.spatial_output_path, output_file_pattern) for sim in simulations]
        )

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

        has_db_results = False
        if use_db_results:
            results_provider = SqliteGcbmResultsProvider([s.db_output_path for s in simulations])
            has_db_results = results_provider.has_indicator(indicator_config.get("database_indicator"))
            if has_db_results:
                indicators.append(Indicator(
                    indicator_config.get("database_indicator") or indicator_config.get("title"),
                    (output_file_patterns, output_file_units),
                    results_provider, {"indicator": indicator_config.get("database_indicator")},
                    indicator_config.get("title"),
                    graph_units, map_units,
                    colorizer=colorizer,
                    interpretation=interpretation))
        
        if not use_db_results or not has_db_results:
            indicators.append(SpatialIndicator(
                indicator_config.get("database_indicator") or indicator_config.get("title"),
                (output_file_patterns, output_file_units),
                indicator_config.get("title"),
                graph_units, map_units,
                colorizer=colorizer))
    
    return indicators

def create_bounding_box(simulations, bounding_box_path=None):
    if bounding_box_path and os.path.exists(bounding_box_path):
        logging.info(f"Using bounding box: {bounding_box_path}")
        return BoundingBox(bounding_box_path, find_best_projection(Layer(bounding_box_path, 0)))
    
    # Try to find a suitable bounding box: the tiler bounding box is usually
    # the only tiff file in the study area directory without "moja" in its name;
    # if that isn't found, use the first tiff file in the study area dir.
    logging.info("Searching for bounding box.")

    bounding_box_files = []
    for sim in simulations:
        if sim.bounding_box:
            logging.info(f"Using configured bounding box: {os.path.abspath(sim.bounding_box)}.")
            bounding_box_files.append(os.path.abspath(sim.bounding_box))
            continue

        study_area_dir = os.path.dirname(sim.study_areas[0])
        
        if bounding_box_path:
            bounding_box_file_by_pattern = os.path.join(study_area_dir, bounding_box_path)
            logging.info(f"Using bounding box by configured pattern: {bounding_box_file_by_pattern}.")
            if os.path.exists(bounding_box_file_by_pattern):
                bounding_box_files.append(os.path.abspath(bounding_box_file_by_pattern))
        else:
            bounding_box_candidates = glob(os.path.join(study_area_dir, "*.tif['', 'f']"))
            bounding_box_file = next(filter(lambda tiff: "moja" not in tiff, bounding_box_candidates), None)
            if not bounding_box_file:
                bounding_box_file = os.path.abspath(bounding_box_candidates[0])

            logging.info(f"Found bounding box: {os.path.abspath(bounding_box_file)}.")
            bounding_box_files.append(os.path.abspath(bounding_box_file))

    if len(bounding_box_files) == 1:
        bounding_box_path = bounding_box_files[0]
        logging.info(f"Using bounding box: {bounding_box_path}.")
        return BoundingBox(bounding_box_path, find_best_projection(Layer(bounding_box_path, 0)))

    # Bounding box is a combination of multiple simulations covering different areas.
    bounding_box_path = TempFileManager.mktmp(suffix=".tif", no_manual_cleanup=True)
    gdal.SetCacheMax(gdal_memory_limit)
    gdal.Warp(bounding_box_path,
              [Layer(layer_path, 0).flatten().path for layer_path in bounding_box_files],
              creationOptions=gdal_creation_options)

    return BoundingBox(bounding_box_path, find_best_projection(Layer(bounding_box_path, 0)))

def load_disturbances(simulations, disturbance_colors_path=None, filter_disturbances=False):
    disturbance_colorizer = None
    disturbance_filter = []
    disturbance_substitutions = {}
    if disturbance_colors_path:
        dist_color_config = json.load(open(disturbance_colors_path, "rb"))
        colorizer_config = {
            (item.get("label"),) or tuple(item["disturbance_types"]):
                item["palette"] for item in dist_color_config
        }

        disturbance_colorizer = CustomColorizer(colorizer_config)
        for item in dist_color_config:
            label = item.get("label")
            if label:
                for dist_type in item["disturbance_types"]:
                    disturbance_substitutions[dist_type] = label

            if filter_disturbances:
                disturbance_filter.extend(item["disturbance_types"])

    disturbance_configurer = DisturbanceLayerConfigurer(disturbance_colorizer)
    disturbance_layers = None
    if len(glob(os.path.join(simulations[0].spatial_output_path, "current_disturbance*.ti*[!.]"))):
        # Use GCBM's record of which disturbance events happened.
        logging.info("Using output disturbances.")
        for sim in simulations:
            sim_disturbance_layers = disturbance_configurer.configure_output(
                sim.spatial_output_path, sim.db_output_path, disturbance_filter, disturbance_substitutions)

            if disturbance_layers is None:
                disturbance_layers = sim_disturbance_layers
            else:
                disturbance_layers.merge(sim_disturbance_layers)
    else:
        logging.info("Using input disturbances.")
        for sim in simulations:
            for study_area in sim.study_areas:
                study_area_disturbance_layers = disturbance_configurer.configure(
                    os.path.abspath(study_area), disturbance_filter, disturbance_substitutions)

                if disturbance_layers is None:
                    disturbance_layers = study_area_disturbance_layers
                else:
                    disturbance_layers.merge(study_area_disturbance_layers)

    return disturbance_layers

def load_spatial_results_config(spatial_results_config_path):
    return [
        Simulation(item["study_area"], item["spatial_results"], item.get("db_results"), item.get("bounding_box"))
        for item in json.load(open(spatial_results_config_path, "rb"))
    ]

def cli():
    parser = ArgumentParser(description="Create GCBM results animations")
    parser.add_argument("output_path", type=os.path.abspath, help="Directory to write animations to")
    parser.add_argument("--spatial_results_config", type=os.path.abspath, help=(
        "Path to JSON file describing GCBM spatial output instead of using "
        "spatial_results, study_area, and db_results args"))
    parser.add_argument("--spatial_results", type=os.path.abspath, help="Path to GCBM spatial output")
    parser.add_argument("--study_area", nargs="*", help="Path to study area file(s) for GCBM spatial input")
    parser.add_argument("--db_results", type=os.path.abspath, help="Path to compiled GCBM results database")
    parser.add_argument("--bounding_box", help="Bounding box defining animation area")
    parser.add_argument("--config", type=os.path.abspath, default="indicators.json",
                        help="Path to animation config file")
    parser.add_argument("--disturbance_colors", type=os.path.abspath,
                        help="Path to disturbance color config file")
    parser.add_argument("--filter_disturbances", action="store_true", default=False,
                        help="Limit disturbances to types in color config file")
    parser.add_argument("--locale", help="Switch locale for generated animations")
    parser.add_argument("--start_year", type=int, help="Start year of the animation (detected if not provided)")
    parser.add_argument("--end_year", type=int, help="End year of the animation (detected if not provided)")
    parser.add_argument("--save_frames", action="store_true", default=False, help="Save animation frames")
    args = parser.parse_args()

    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    TempFileManager.delete_on_exit()

    if args.locale:
        localization.switch(args.locale)

    simulations = (
        [Simulation(args.study_area, args.spatial_results, args.db_results)] if args.spatial_results
        else load_spatial_results_config(args.spatial_results_config)
    )

    use_db_results = not args.bounding_box and (
        args.db_results
        or all((s.db_output_path for s in simulations))
    )

    bounding_box = create_bounding_box(simulations, args.bounding_box)
    bounding_box.init()
    
    indicators = load_indicators(simulations, args.config, use_db_results)
    disturbances = load_disturbances(simulations, args.disturbance_colors, args.filter_disturbances)
    animator = BoxLayoutAnimator(disturbances, indicators, args.output_path)
    animator.render(bounding_box, start_year=args.start_year, end_year=args.end_year,
                    save_frames=args.save_frames)

if __name__ == "__main__":
    cli()
