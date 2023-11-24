import logging
import pandas as pd

def overlay(layers, chunk_size=5000):
    '''
    Overlays a collection of layers that already have the same projection, extent,
    and resolution. They can have different attribute tables (or no attribute table at all),
    and the result is a summary of the area in hectares of the unique combinations of pixel
    and/or attribute values in space through the whole stack.

    Arguments:
    'layers' -- a dict of layer name to catplotlib Layer. Layers can be interpreted or not,
        and both the pixel value and interpretation are included in the results as columns
        named "{layer name}_px" and "{layer name}"

    Returns a DataFrame containing the area summary.
    '''
    layer_readers = {
        layer_name: layer.read(chunk_size)
        for layer_name, layer in layers.items()
    }
    
    n_layers = len(layer_readers)
    chunk_n = 0

    pixel_areas = pd.DataFrame()
    while True:
        chunk_n += 1
        all_chunk_data = None
        for i, (layer_name, reader) in enumerate(layer_readers.items(), 1):
            try:
                chunk_data = next(reader)
            except StopIteration:
                break
            
            if i == 1:
                logging.info(f"Processing chunk {chunk_n}...")

            logging.info(f"  layer {i} of {n_layers}")

            chunk_data = chunk_data.rename({
                "value": f"{layer_name}_px",
                "interpretation": f"{layer_name}"
            }, axis=1)
            
            if all_chunk_data is None:
                all_chunk_data = chunk_data
            else:
                all_chunk_data = all_chunk_data.join(
                    chunk_data[[c for c in chunk_data.columns if c != "area"]]
                )
    
        if all_chunk_data is None:
            break
        
        pixel_areas = pd.concat([
            pixel_areas, all_chunk_data
        ]).fillna("").groupby([
            c for c in set(list(all_chunk_data.columns) + list(pixel_areas.columns))
            if c != "area"
        ]).sum().reset_index()

    return pixel_areas
