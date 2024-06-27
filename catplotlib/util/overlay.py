import logging
import pandas as pd
from pathlib import Path
from catplotlib.util import gdal

def overlay(layers, chunk_size=5000, output_path=None):
    '''
    Overlays a collection of layers that already have the same projection, extent,
    and resolution. They can have different attribute tables (or no attribute table at all),
    and the result is a summary of the area in hectares of the unique combinations of pixel
    and/or attribute values in space through the whole stack.

    Arguments:
    'layers' -- a dict of layer name to catplotlib Layer. Layers can be interpreted or not,
        and both the pixel value and interpretation are included in the results as columns
        named "{layer name}_px" and "{layer name}"
    'output_path' -- optional path to a tif file to create where the pixel value corresponds
        to the unique combinations of attributes in the layers ("overlay_id" in the dataframe)

    Returns a DataFrame containing the area summary.
    '''
    output_band = None
    if output_path:
        output_path = Path(output_path)
        output_path.unlink(True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        next(iter(layers.values())).blank_copy(str(output_path), data_type=gdal.GDT_Int32, nodata_value=0)
        output_layer = gdal.Open(str(output_path), gdal.GA_Update)
        output_band = output_layer.GetRasterBand(1)
        key_columns = [f"{layer_name}_px" for layer_name in layers.keys()]
        overlay_id_lookup = pd.DataFrame({
            "overlay_id": [0],
            **{f"{layer_name}_px": [layer.nodata_value] for layer_name, layer in layers.items()}
        }).set_index(key_columns)

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
                chunk, chunk_data = next(reader)
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
                    chunk_data[[c for c in chunk_data.columns if c != "area"]],
                    rsuffix=f"_{layer_name}"
                )
    
        if all_chunk_data is None:
            break
        
        if output_band is not None:
            current_chunk_uniques = all_chunk_data[key_columns].drop_duplicates().set_index(key_columns)
            all_uniques = current_chunk_uniques.merge(
                overlay_id_lookup, indicator=True, left_index=True, right_index=True, how="outer"
            )
                
            next_id = overlay_id_lookup["overlay_id"].max() + 1
            new_lookup_rows = all_uniques[all_uniques["_merge"] == "left_only"].drop(all_uniques.columns, axis=1)
            new_lookup_rows.insert(0, "overlay_id", range(next_id, next_id + len(new_lookup_rows)))
            overlay_id_lookup = pd.concat([overlay_id_lookup, new_lookup_rows]).reset_index().set_index(key_columns)

            all_chunk_data = all_chunk_data.join(overlay_id_lookup, on=key_columns)
            x_px_start, y_px_start, x_size, y_size = chunk
            output_band.WriteArray(
                all_chunk_data["overlay_id"].values.reshape(y_size, x_size),
                x_px_start, y_px_start
            )

        pixel_areas = pd.concat([
            pixel_areas, all_chunk_data
        ]).fillna("").groupby([
            c for c in set(list(all_chunk_data.columns) + list(pixel_areas.columns))
            if c != "area"
        ], dropna=False).sum().reset_index()

    if output_band is not None:
        output_band.FlushCache()
        output_band = None
        output_layer = None
        attribute_table_path = output_path.parent.joinpath(f"{output_path.stem}_attributes.csv")
        pixel_areas.drop("area", axis=1, errors="ignore").to_csv(attribute_table_path, index=False)

    pixel_areas.drop("overlay_id", inplace=True, errors="ignore")
    
    return pixel_areas
