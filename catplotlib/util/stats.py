import logging
import warnings
import numpy as np
from pathlib import Path
from catplotlib.util.config import gdal_memory_limit
from mojadata.util import gdal
from mojadata.util.gdalhelper import GDALHelper
from catplotlib.spatial.layer import Layer
from catplotlib.spatial.boundingbox import BoundingBox

def _find_layers(pattern, pattern_filter_fn=None):
    initial_path = "."
    if "\\" in pattern:
        pattern_root, pattern = pattern.split("\\", 1)
        initial_path = pattern_root + "\\"
        
    pattern_filter_fn = pattern_filter_fn or (lambda p: True)
    input_layers = [p for p in Path(initial_path).glob(pattern) if pattern_filter_fn(p)]
    
    return input_layers

def _normalize_layers(layer_paths):
    n_original_layers = len(layer_paths)
    bounding_box = BoundingBox(str(layer_paths[0]))
    normalized_input_layers = []
    for i, path in enumerate(layer_paths, 1):
        logging.info(f"    layer {i} / {n_original_layers}")
        normalized_layer = bounding_box.crop(Layer(str(path), 0), False)
        normalized_input_layers.append(normalized_layer.path)

    return normalized_input_layers

def calculate_stack_stat(
    pattern, output_path, numpy_fn, *numpy_args, pattern_filter_fn=None, chunk_size=5000,
    **numpy_kwargs
):
    logging.info(f"Processing {pattern}...")
    gdal.SetCacheMax(gdal_memory_limit)
    Path(output_path).unlink(True)
    
    input_layers = _find_layers(pattern, pattern_filter_fn)
    logging.info("  normalizing layers to same extent and resolution")
    normalized_input_layers = _normalize_layers(input_layers)
    n_layers = len(normalized_input_layers)
    logging.info(f"  processing {n_layers} normalized layers")

    output_template = Layer(str(normalized_input_layers[0]), 0)
    output_template.blank_copy(str(output_path))
    ndv = output_template.nodata_value
    output_raster = gdal.Open(str(output_path), gdal.GA_Update)
    out_band = output_raster.GetRasterBand(1)
    out_band.SetNoDataValue(ndv)

    chunks = list(output_template._chunk(chunk_size))
    n_chunks = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        logging.info(f"  chunk {i} / {n_chunks}")
        all_chunk_data = []
        for j, layer_path in enumerate(normalized_input_layers, 1):
            logging.info(f"    layer {j} / {n_layers}")
            ds = gdal.Open(str(layer_path))
            band = ds.GetRasterBand(1)
            chunk_data = band.ReadAsArray(*chunk)
            chunk_data[chunk_data == band.GetNoDataValue()] = np.nan
            all_chunk_data.append(chunk_data)
            
        numpy_args = numpy_args or []
        numpy_kwargs = numpy_kwargs or {}
        numpy_kwargs.update({"axis": 0})
        stacked_data = np.stack(all_chunk_data)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            percentile_data = numpy_fn(stacked_data, *numpy_args, **numpy_kwargs)

        nodata_mask = np.all(np.stack([np.isnan(chunk_data) for chunk_data in all_chunk_data]), axis=0)
        percentile_data[nodata_mask] = ndv

        out_band.WriteArray(percentile_data, chunk[0], chunk[1])
