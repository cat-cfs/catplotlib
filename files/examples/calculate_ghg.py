import os
import sys
import logging
from glob import glob
from pathlib import Path
from aenum import extend_enum
from multiprocessing import Pool
from argparse import ArgumentParser
from catplotlib.util import gdal
from catplotlib.spatial.layer import Layer
from catplotlib.spatial.layer import BlendMode
from catplotlib.spatial.layercollection import LayerCollection
from catplotlib.provider.units import Units
from catplotlib.util.config import gdal_creation_options
from catplotlib.provider.spatialgcbmresultsprovider import SpatialGcbmResultsProvider
from catplotlib.util.tempfile import TempFileManager


def find_layers(pattern, units=None):
    logging.info(f"Finding layers for pattern: {pattern}")
    units = units or Units.TcPerHa

    layers = []
    for layer_path in glob(pattern):
        year = Path(layer_path).stem.rsplit("_", 1)[1]
        layers.append(Layer(layer_path, year, units=units))

    if not layers:
        logging.info(f"No spatial output found for pattern: {pattern}")

    return LayerCollection(layers)


def read_raster(path):
    raster = gdal.Open(path)
    band = raster.GetRasterBand(1)
    data = band.ReadAsArray()

    return raster, band, data
    
    
def save_to_copy(original_raster, data, output_path):
    logging.info(f"Writing {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    driver = gdal.GetDriverByName("GTiff")
    copy = driver.CreateCopy(output_path, original_raster, strict=0, options=gdal_creation_options)
    band = copy.GetRasterBand(1)
    band.WriteArray(data)
    band.FlushCache()


def generate_n2o_layers(dist_co2_pattern, dist_ch4_pattern, output_path=None):
    output_path = output_path or os.path.dirname(dist_co2_pattern)
    logging.info(f"Generating N2O layers in {output_path}")

    disturbance_co2_layers = find_layers(dist_co2_pattern)
    disturbance_ch4_layers = find_layers(dist_ch4_pattern)

    for ch4_layer in disturbance_ch4_layers.layers:
        year = ch4_layer.year
        n2o_raster_path = os.path.join(output_path, f"Disturbance_N2O_Emission_{year}.tif")
        if os.path.exists(n2o_raster_path):
            logging.info(f"  Found existing layer: {n2o_raster_path} - skipping")
            continue
        
        matching_co2_layers = list(filter(lambda l: l.year == year, disturbance_co2_layers.layers))
        if not matching_co2_layers:
            logging.info(f"  No matching CO2 layer found for {ch4_layer.path} - skipping")
            continue
        
        co2_layer = matching_co2_layers[0]
        co2_raster, co2_band, co2_data = read_raster(co2_layer.path)
        ch4_raster, ch4_band, ch4_data = read_raster(ch4_layer.path)
        ch4_data[co2_data == co2_band.GetNoDataValue()] = ch4_band.GetNoDataValue()
        ch4_data[(ch4_data != ch4_band.GetNoDataValue()) & (ch4_data > 0)] = \
            co2_data[(ch4_data != ch4_band.GetNoDataValue()) & (ch4_data > 0)] * 0.00017
            
        save_to_copy(ch4_raster, ch4_data, n2o_raster_path)


def convert_to_co2e_per_ha(layer_collection, conversion_units):
    return layer_collection.convert_units(conversion_units) \
                           .convert_units(Units.Tco2ePerHa, area_only=True)


def add_co2e_units():
    for name, value in (
        ("Tco2e",         (False,                 1.0, "tCO2e")),
        ("Tco2ePerHa",    (True,                  1.0, "tCO2e")),
        ("COtco2ePerHa",  (True,          44.0 / 12.0, "tCO2e")),
        ("CO2tco2ePerHa", (True,          44.0 / 12.0, "tCO2e")),
        ("CH4tco2ePerHa", (True,   16.0 / 12.0 * 25.0, "tCO2e")),
        ("N2Otco2ePerHa", (True,  44.0 / 12.0 * 298.0, "tCO2e")),
    ):
        extend_enum(Units, name, value)


def init_pool():
    add_co2e_units()
    gdal.PushErrorHandler("CPLQuietErrorHandler")


def create_ghg_layers(file_patterns, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    add_co2e_units()
    generate_n2o_layers(file_patterns["dist_co2_pattern"], file_patterns["dist_ch4_pattern"], output_path)
    npp_layers = convert_to_co2e_per_ha(find_layers(file_patterns["npp_pattern"]), Units.CO2tco2ePerHa)
    with Pool(initializer=init_pool) as pool:
        tasks = [
            pool.apply_async(convert_to_co2e_per_ha, (layers, co2e_conversion_units))
            for layers, co2e_conversion_units in (
                (find_layers(file_patterns["dist_co_pattern"]), Units.COtco2ePerHa),
                (find_layers(file_patterns["dist_co2_pattern"]), Units.CO2tco2ePerHa),
                (find_layers(file_patterns["dist_ch4_pattern"]), Units.CH4tco2ePerHa),
                (find_layers(rf"{output_path}\disturbance_n2o_emission*.tif"), Units.N2Otco2ePerHa),
                (find_layers(file_patterns["decay_co_pattern"]), Units.COtco2ePerHa),
                (find_layers(file_patterns["decay_co2_pattern"]), Units.CO2tco2ePerHa),
                (find_layers(file_patterns["decay_ch4_pattern"]), Units.CH4tco2ePerHa),
            )
        ]
        
        emissions_layers = [task.get() for task in tasks]
    
    logging.info("Calculating GHG balance")
    ghg_balance_layers = emissions_layers.pop()
    for emissions in emissions_layers:
        ghg_balance_layers = ghg_balance_layers.blend(emissions, BlendMode.Add)
    
    ghg_balance_layers = ghg_balance_layers.blend(npp_layers, BlendMode.Subtract)
    ghg_balance_layers.save_copy(output_path, "ghg_tco2e_per_ha")
    

if __name__ == "__main__":
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    TempFileManager.delete_on_exit()
    
    parser = ArgumentParser(description="Generate GHG balance from GCBM spatial output")
    parser.add_argument("output_path", type=os.path.abspath, help="Path to generate GHG output files in")
    
    parser.add_argument("--npp_pattern", default="npp*.tif", type=os.path.abspath,
                        help="File pattern for NPP")

    parser.add_argument("--dist_co_pattern", default="disturbance_co_emission*.tif",
                        type=os.path.abspath, help="File pattern for disturbance CO emissions")

    parser.add_argument("--dist_co2_pattern", default="disturbance_co2_emission*.tif",
                        type=os.path.abspath, help="File pattern for disturbance CO2 emissions")

    parser.add_argument("--dist_ch4_pattern", default="disturbance_ch4_emission*.tif",
                        type=os.path.abspath, help="File pattern for disturbance CH4 emissions")

    parser.add_argument("--decay_co_pattern", default="annual_process_co_emission*.tif",
                        type=os.path.abspath, help="File pattern for annual process CO emissions")

    parser.add_argument("--decay_co2_pattern", default="annual_process_co2_emission*.tif",
                        type=os.path.abspath, help="File pattern for annual process CO2 emissions")

    parser.add_argument("--decay_ch4_pattern", default="annual_process_ch4_emission*.tif",
                        type=os.path.abspath, help="File pattern for annual process CH4 emissions")

    args = parser.parse_args()
    
    file_patterns = {
        "npp_pattern": args.npp_pattern,
        "dist_co_pattern": args.dist_co_pattern,
        "dist_co2_pattern": args.dist_co2_pattern,
        "dist_ch4_pattern": args.dist_ch4_pattern,
        "decay_co_pattern": args.decay_co_pattern,
        "decay_co2_pattern": args.decay_co2_pattern,
        "decay_ch4_pattern": args.decay_ch4_pattern
    }

    create_ghg_layers(file_patterns, args.output_path)
