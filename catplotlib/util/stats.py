import logging
import warnings
import numpy as np
from pathlib import Path
from multiprocessing import Pool
from catplotlib.util.config import gdal_memory_limit
from mojadata.util import gdal
from catplotlib.spatial.layer import Layer
from catplotlib.spatial.boundingbox import BoundingBox
from catplotlib.util.cache import get_cache

def _find_layers(pattern, pattern_filter_fn=None):
    initial_path = "."
    if "\\" in pattern:
        pattern_root, pattern = pattern.split("\\", 1)
        initial_path = pattern_root + "\\"
        
    pattern_filter_fn = pattern_filter_fn or (lambda p: True)
    input_layers = [p for p in Path(initial_path).glob(pattern) if pattern_filter_fn(p)]
    
    return input_layers

def _normalize_layers(layer_paths, cache):
    bounding_box = BoundingBox(str(layer_paths[0]), cache=cache)
    normalized_input_layers = []
    with Pool() as pool:
        tasks = []
        for layer_path in layer_paths:
            for layer in Layer(layer_path).unpack():
                tasks.append(pool.apply_async(bounding_box.crop, (layer, False)))
        
        pool.close()
        pool.join()
        
        for result in tasks:
            normalized_input_layers.append(result.get().path)

    return normalized_input_layers

def calculate_stack_stat(
    pattern, output_path, numpy_fn, *numpy_args, pattern_filter_fn=None, chunk_size=5000,
    **numpy_kwargs
):
    '''
    Performs a numpy operation per pixel (in space) on a stack of rasters and writes the
    result to a single new raster - for example, the per-pixel 95th percentile value.

    Arguments:
    'pattern' -- the file pattern to search for
    'output_path' -- the path to the output raster to create
    'numpy_fn' -- a stack-compatible numpy function to use, i.e. sum, percentile, nanpercentile
    'numpy_args' -- positional args to pass to the numpy function
    'pattern_filter_fn' -- an additional filter function to determine if each layer
        found by the search pattern should be included or not; must be a function that
        takes a single arg, a file path, and returns True or False
    'chunk_size' -- the size of the chunks to process
    'numpy_kwargs' -- keyword args to pass to the numpy function
    '''
    logging.info(f"Processing {pattern}...")

    gdal.SetCacheMax(gdal_memory_limit)
    cache = get_cache()
    Path(output_path).unlink(True)
    
    input_layers = _find_layers(pattern, pattern_filter_fn)
    if not input_layers:
        logging.error("  no layers found")
        return

    logging.info("  normalizing layers to same extent and resolution")
    normalized_input_layers = _normalize_layers(input_layers, cache)
    n_layers = len(normalized_input_layers)
    logging.info(f"  processing {n_layers} normalized layers")

    output_template = Layer(str(normalized_input_layers[0]), 0, cache=cache)
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
            chunk_data = band.ReadAsArray(*chunk).astype(float)
            chunk_data[chunk_data == band.GetNoDataValue()] = np.nan
            all_chunk_data.append(chunk_data)
            
        numpy_args = numpy_args or []
        numpy_kwargs = numpy_kwargs or {}
        numpy_kwargs.update({"axis": 0})
        stacked_data = np.stack(all_chunk_data)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            calculated_data = numpy_fn(stacked_data, *numpy_args, **numpy_kwargs)

        nodata_mask = np.all(np.stack([np.isnan(chunk_data) for chunk_data in all_chunk_data]), axis=0)
        calculated_data[nodata_mask] = ndv

        out_band.WriteArray(calculated_data, chunk[0], chunk[1])
