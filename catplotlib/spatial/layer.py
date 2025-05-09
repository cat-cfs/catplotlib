import os
import json
import logging
import subprocess
import shutil
import numpy as np
import pandas as pd
from io import UnsupportedOperation
from pathlib import Path
from pandas import DataFrame
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from catplotlib.util import gdal
from mojadata.util.gdalhelper import GDALHelper
from geopy.distance import distance
from catplotlib.util.config import pool_workers
from catplotlib.util.config import gdal_creation_options
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.tempfile import TempFileManager
from catplotlib.spatial.display.frame import Frame
from catplotlib.provider.units import Units
from catplotlib.util.cache import get_cache

class BlendMode(Enum):
    
    Add      = lambda a, fn1, fn2: (fn1(a[0]) + fn2(a[1:]))
    Subtract = lambda a, fn1, fn2: (- fn1(a[0]) + fn2(a[1:]))


class Layer:
    '''
    Holds information about a layer to include in an animation. A layer applies
    to a single year, and the optional interpretation maps raster values to a
    single attribute value. If an interpretation is provided, any pixels not
    included are considered nodata.

    Arguments:
    'path' -- path to the layer file.
    'year' -- the year the layer applies to.
    'interpretation' -- optional attribute table for the raster; should be a
        dictionary of pixel value to interpretation, i.e. {1: "Wildfire"}.
    'units' -- the units the layer's pixel values are in.
    'simulation_start_year' -- if this is a multiband layer, the year that band 1
        (timestep 1) corresponds to.
    '''

    def __init__(
        self, path, year=None, interpretation=None, units=Units.TcPerHa, cache=None,
        simulation_start_year=None
    ):
        self._path = str(Path(path).absolute())
        self._year = int(year) if year is not None else "multiband" if simulation_start_year is not None else -1
        self._interpretation = interpretation
        self._units = units
        self._info = None
        self._cache = cache or get_cache()
        self._simulation_start_year = simulation_start_year
        self._min = None
        self._max = None

    @property
    def interpretation(self):
        '''Gets the layer interpretation: dict of pixel value to string.'''
        return self._interpretation

    @property
    def has_interpretation(self):
        '''
        Checks if the layer has an interpretation (pixel values have meaning
        other than their literal numeric value).
        '''
        return self._interpretation is not None

    @property
    def path(self):
        '''Gets the layer's file path.'''
        return self._path

    @property
    def year(self):
        '''Gets the year the layer applies to.'''
        return self._year

    @property
    def info(self):
        '''Gets this layer's GDAL info dictionary, including min/max values.'''
        if not self._info:
            self._info = json.loads(gdal.Info(
                self._path, format="json", deserialize=False, computeMinMax=False).replace("nan", "0"))
        
        return self._info
    
    @property
    def n_bands(self):
        '''Gets the number of bands in this layer.'''
        return len(self.info.get("bands", []))

    @property
    def is_multiband(self):
        return self.n_bands > 1

    @property
    def is_lat_lon(self):
        ds = gdal.Open(self.path)
        srs = ds.GetSpatialRef()
        is_lat_lon = srs.EPSGTreatsAsLatLong() == 1
        
        return is_lat_lon

    @property
    def px_area(self):
        '''Gets this layer's area in pixels (simple x-pixels by y-pixels).'''
        ds = gdal.Open(self._path)
        band = ds.GetRasterBand(1)
        px_area = band.XSize * band.YSize
        
        return px_area

    @property
    def min_max(self):
        '''Gets this layer's minimum and maximum pixel values.'''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        if self._min is not None and self._max is not None:
            return self._min, self._max

        info = json.loads(gdal.Info(
            self._path, format="json", deserialize=False, computeMinMax=True).replace("nan", "0"))
        
        if not info or "computedMin" not in info["bands"][0]:
            self._min = 0
            self._max = 0
        else:
            self._min = info["bands"][0]["computedMin"]
            self._max = info["bands"][0]["computedMax"]

        return self._min, self._max

    @property
    def data_type(self):
        '''Gets this layer's data type.'''
        return self.info["bands"][0]["type"]

    @property
    def nodata_value(self):
        '''Gets this layer's nodata value in its correct Python type.'''
        dt = str(self.data_type).lower()
        value = self.info["bands"][0].get("noDataValue")
        if value is None or str(value).lower() == "nan":
            value = (
                GDALHelper.float32_range[0] if (
                    dt == "float32" or dt == "float" or dt == str(gdal.GDT_Float32)
                    or dt == "float64" or dt == str(gdal.GDT_Float64))
                else GDALHelper.byte_range[0] if dt == "byte"
                else GDALHelper.int32_range[0]
            )

        if (dt == "float32" or dt == "float" or dt == str(gdal.GDT_Float32)
            or dt == "float64" or dt == str(gdal.GDT_Float64)
        ):
            return float(value)
        else:
            return int(value)

    @property
    def scale(self):
        '''Gets this layer's pixel size in metres.'''
        metres = "metre" in self.info["coordinateSystem"]["wkt"]
        if metres:
            pixel_size_m = abs(float(self.info["geoTransform"][1]))
        else:
            bounds = self.info["cornerCoordinates"]
            center_x = (bounds["lowerRight"][0] - bounds["upperLeft"][0]) / 2
            center_y = (bounds["lowerRight"][1] - bounds["upperLeft"][1]) / 2
            _, px_width, *_ = self.info["geoTransform"]
            pixel_size_m = distance((center_y, center_x), (center_y, center_x + px_width)).m

        return pixel_size_m

    @property
    def units(self):
        '''Gets this layer's units.'''
        return self._units

    def get_histogram(self, min_value, max_value, buckets):
        '''Computes a histogram for this layer.'''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        
        return band.GetHistogram(min=min_value, max=max_value, buckets=buckets)

    def convert_units(self, units, area_only=False):
        '''
        Converts this layer's values into new units - both scale and area type
        (per hectare or absolute).

        Arguments:
        'units' -- a new Units enum value to convert to
        'area_only' -- only perform per-hectare <-> per-pixel conversion

        Returns a copy of this layer in the new units as a new Layer object.
        '''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        if self._units == Units.Blank:
            return self

        gdal.SetCacheMax(gdal_memory_limit)
        current_per_ha, current_units_tc, current_units_name = self._units.value
        new_per_ha, new_units_tc, new_units_name = units.value
        unit_conversion = 1.0 if area_only else new_units_tc / current_units_tc

        if current_per_ha == new_per_ha and unit_conversion == 1:
            self._units = units
            return self

        output_path = TempFileManager.mktmp(suffix=".tif")
        one_hectare = 100 ** 2
        nodata_value = self.nodata_value
        simple_conversion_calc = None
        if current_per_ha == new_per_ha:
            simple_conversion_calc = (
                lambda A: 
                    A.astype(np.float64) * unit_conversion
                    * (A != nodata_value)
                    + ((A == nodata_value) * nodata_value)
                                      )
            
        elif not self.is_lat_lon:
            per_ha_conversion_op = 1 if current_per_ha else -1
            _, pixel_size, *_ = self.info["geoTransform"]
            pixel_size_m2 = float(pixel_size) ** 2
            per_ha_modifier = pixel_size_m2 / one_hectare if current_per_ha != new_per_ha else 1
            simple_conversion_calc = (
                lambda A: 
                    (A.astype(np.float64) * unit_conversion * per_ha_modifier**per_ha_conversion_op)
                    * (A != nodata_value)
                    + ((A == nodata_value) * nodata_value)
                                      )

        if simple_conversion_calc:
            GDALHelper.calc(self.path, output_path, simple_conversion_calc)

            return Layer(output_path, self._year, self._interpretation, units, cache=self._cache)

        area_raster_path = self.get_area_raster()
        per_ha_conversion_op = 1 if current_per_ha else -1
        calc_fn = (
            lambda A:
                (A[0].astype(np.float64) * unit_conversion * A[1]**per_ha_conversion_op)
                * (A[0] != nodata_value)
                + ((A[0] == nodata_value) * nodata_value) 
        )
                
        GDALHelper.calc([self.path, area_raster_path], output_path, calc_fn)
        
        return Layer(output_path, self._year, self._interpretation, units, cache=self._cache)

    def aggregate(self, units=None, area_only=False, band=1):
        '''
        Aggregates this layer's non-nodata pixels into either the sum (for a layer of absolute
        values), or the average per-hectare value (for a layer of per-hectare values). If 'units'
        is specified, the layer's native units are converted to the target units before the above
        rule is applied.

        Arguments:
        'units' -- a new Units enum value to convert to
        'area_only' -- only perform per-hectare <-> per-pixel conversion

        Returns the sum or the average per-hectare value of the non-nodata pixels.
        '''
        gdal.SetCacheMax(gdal_memory_limit)
        current_per_ha, current_units_tc, current_units_name = self._units.value
        new_per_ha, new_units_tc, new_units_name = units.value if units else self._units.value
        unit_conversion = 1.0 if area_only else new_units_tc / current_units_tc
        one_hectare = 100 ** 2

        raster = gdal.Open(self._path)
        raster_band = raster.GetRasterBand(band)
        nodata_value = self.nodata_value
        
        total_value = 0
        total_area = 0
        area_band = None
        for chunk in self._chunk():
            raster_data = raster_band.ReadAsArray(*chunk).astype("float")

            # First need to convert pixel values to absolute (as opposed to per hectare), in the correct
            # units (tc/ktc/mtc), and determine the total area of non-nodata pixels.
            if not self.is_lat_lon:
                _, pixel_size, *_ = self.info["geoTransform"]
                pixel_size_m2 = float(pixel_size) ** 2
                per_ha_modifier = pixel_size_m2 / one_hectare if current_per_ha else 1
                raster_data[raster_data != nodata_value] *= unit_conversion * per_ha_modifier
                total_area += len(raster_data[raster_data != nodata_value]) * pixel_size_m2 / one_hectare
            else:
                if not area_band:
                    area_raster_path = self.get_area_raster()
                    area_raster = gdal.Open(area_raster_path)
                    area_band = area_raster.GetRasterBand(1)

                raster_data[raster_data != nodata_value] *= unit_conversion
                area_data = area_band.ReadAsArray(*chunk)
                total_area += area_data[raster_data != nodata_value].sum()

                if current_per_ha:
                    raster_data[raster_data != nodata_value] *= area_data[raster_data != nodata_value]

            total_value += raster_data[(raster_data != nodata_value) & (~np.isnan(raster_data))].sum()
            
        return total_value / (total_area if new_per_ha else 1)

    def summarize(self):
        '''
        Returns a summary of this layer's area in hectares by unique pixel value.
        '''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        nodata_value = self.nodata_value
        pixel_areas = None
        for _, chunk in self.read():
            if pixel_areas is None or pixel_areas.empty:
                pixel_areas = (
                    chunk[chunk["value"] != nodata_value]
                ).groupby([c for c in chunk.columns if c != "area"]).sum().reset_index()
            else:
                pixel_areas = pd.concat(
                    [pixel_areas, chunk[chunk["value"] != nodata_value]]
                ).groupby([c for c in chunk.columns if c != "area"]).sum().reset_index()
    
        pixel_areas = pixel_areas.set_index("value")
        
        return pixel_areas
    
    def read(self, chunk_size=5000, include_area=True):
        '''
        Read this layer in flattened chunks along with the attribute table (if applicable)
        and pixel area to help with overlays and summaries.
        
        Yields each chunk of data from the raster as a flattened DataFrame joined to per-
        pixel area, columns: value (pixel value), interpretation (if applicable), area (hectares).
        '''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        ndv = band.GetNoDataValue()
        one_hectare = 100 ** 2
        
        area_band = None
        for chunk in self._chunk(chunk_size):
            raster_data = DataFrame(
                np.nan_to_num(band.ReadAsArray(*chunk).flatten(), nan=ndv, posinf=ndv, neginf=ndv),
                columns=["value"]
            )
            
            if self.has_interpretation:
                columns = (
                    None if isinstance(next(iter(self._interpretation.values())), dict)
                    else ["interpretation"]
                )
                
                raster_data = raster_data.join(DataFrame(
                    self._interpretation.values(), self._interpretation.keys(),
                    columns=columns
                ), on="value").fillna("")

            if include_area:
                if not self.is_lat_lon:
                    _, pixel_size, *_ = self.info["geoTransform"]
                    pixel_size_m2 = float(pixel_size) ** 2
                    raster_data["area"] = pixel_size_m2 / one_hectare
                else:
                    if not area_band:
                        area_raster_path = self.get_area_raster()
                        area_raster = gdal.Open(area_raster_path)
                        area_band = area_raster.GetRasterBand(1)
                
                    area_data = DataFrame(area_band.ReadAsArray(*chunk).flatten(), columns=["area"])
                    raster_data = raster_data.join(area_data)
    
            yield chunk, raster_data
    
    def area_grid(self, chunk_size=5000):
        '''
        Returns a grid for this layer where each pixel's value is its area in
        hectares.

        Arguments:
        'chunk_size' -- the maximum chunk size in pixels, yielding chunks of
            chunk_size^2

        Yields data and pixel offsets for writing with GDAL.
        '''
        m_per_hectare = 100 ** 2
        pi = 3.141592653590
        earth_diameter_m_per_deg = 2.0 * pi * 6378137.0 / 360.0

        bounds = self.info["cornerCoordinates"]
        xmin, ymin = bounds["upperLeft"]
        xmax, ymax = bounds["lowerRight"]

        resolution = self.info["geoTransform"][1]
        x_res = resolution if xmin < xmax else -resolution
        y_res = resolution if ymin < ymax else -resolution

        for x_px_start, y_px_start, x_size, y_size in self._chunk(chunk_size):
            chunk_y_min = ymin + y_px_start * y_res
            chunk_y_max = chunk_y_min + y_size * y_res
            lats = np.arange(chunk_y_min, chunk_y_max, y_res)[:y_size]
            area = np.abs(
                  np.ones(x_size)[:, None] * resolution**2 * earth_diameter_m_per_deg**2
                * np.cos(lats * pi / 180.0) / m_per_hectare)
        
            yield area.T, (x_px_start, y_px_start)

    def get_area_raster(self):
        '''
        Generates and caches an area raster for this layer's spatial extent and
        resolution.

        Returns the path to the area raster.
        '''
        geotransform = self.info["geoTransform"]
        cache_key = str(geotransform)
        area_raster_path = self._cache.storage.get(cache_key)
        if area_raster_path:
            return area_raster_path

        with self._cache.lock:
            area_raster_path = self._cache.storage.get(cache_key)
            if area_raster_path:
                return area_raster_path

            gdal.SetCacheMax(gdal_memory_limit)
            driver = gdal.GetDriverByName("GTiff")
            original_raster = gdal.Open(self._path)
            area_raster_path = TempFileManager.mktmp(no_manual_cleanup=True)
            area_raster = driver.Create(
                area_raster_path, original_raster.RasterXSize, original_raster.RasterYSize, 1,
                gdal.GDT_Float32, gdal_creation_options)

            area_raster.SetGeoTransform(original_raster.GetGeoTransform())
            area_raster.SetProjection(original_raster.GetProjection())
            band = area_raster.GetRasterBand(1)
            band.SetNoDataValue(self.nodata_value)
            for data, px_offset in self.area_grid():
                band.WriteArray(data, *px_offset)

            band.FlushCache()
            band = None
            area_raster = None
            self._cache.storage[cache_key] = area_raster_path
            
            return area_raster_path
        
    def reclassify(self, new_interpretation, nodata_value=0):
        '''
        Reclassifies a copy of this layer's pixel values according to a new interpretation.
        Any old interpretations not assigned a new pixel value will be set to nodata;
        for example, if the layer's original interpretation is {1: "Fire", 2: "Clearcut"},
        and the new interpretation is {3: "Fire"}, the original value 1 pixels will
        become 3, and the original value 2 pixels will become nodata.

        Arguments:
        'new_interpretation' -- dictionary of pixel value to interpreted value.
        'nodata_value' -- the new nodata pixel value.
        
        Returns a new reclassified Layer object.
        '''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        orig_ndv = self.nodata_value
        if ((self.interpretation and self.interpretation.items() <= new_interpretation.items())
            and nodata_value == orig_ndv
        ):
            logging.debug(f"Attribute table already matches, skipping reclassify for {self._path}")
            return self

        gdal.SetCacheMax(gdal_memory_limit)
        logging.debug(f"Reclassifying {self._path}")

        if isinstance(next(iter(new_interpretation.values())), dict):
            reclass_keys = list(next(iter(new_interpretation.values())).keys())
            reclass_data = {c: [] for c in reclass_keys}
            reclass_data["reclass_value"] = []
            for reclass_value, reclass_interpretation in new_interpretation.items():
                reclass_data["reclass_value"].append(reclass_value)
                for c in reclass_keys:
                    reclass_data[c].append(reclass_interpretation[c])

            reclass_lookup = DataFrame(reclass_data).set_index(reclass_keys)
        else:
            reclass_keys = ["interpretation"]
            reclass_lookup = DataFrame(
                new_interpretation.keys(), new_interpretation.values(), columns=["reclass_value"]
            )

        output_ndv = nodata_value if nodata_value is not None else orig_ndv
        output_path = self.blank_copy(nodata_value=output_ndv)
        output_layer = gdal.Open(str(output_path), gdal.GA_Update)
        output_band = output_layer.GetRasterBand(1)
        for i, (chunk, chunk_data) in enumerate(self.read(include_area=False), 1):
            logging.debug(f"  chunk {i}")
            reclass_chunk_data = chunk_data.join(reclass_lookup, on=reclass_keys).fillna(output_ndv)            
            x_px_start, y_px_start, x_size, y_size = chunk
            output_band.WriteArray(
                reclass_chunk_data["reclass_value"].values.reshape(y_size, x_size),
                x_px_start, y_px_start
            )

        output_band.FlushCache()
        output_band = None
        output_layer = None

        reclassified_layer = Layer(output_path, self._year, new_interpretation, self._units, cache=self._cache)

        return reclassified_layer

    def flatten(self, flattened_value=1, preserve_units=False):
        '''
        Flattens a copy of this layer: all non-nodata pixels become the target value.
        If this layer has an interpretation, only the pixel values included in the
        attribute table are flattened, and the others become nodata.

        Arguments:
        'flattened_value' -- the value to set all data pixels to.
        'preserve_units' -- preserve the units (Units.TcPerHa, etc.) of this layer in
            the flattened copy - otherwise set to Units.Blank.

        Returns a new flattened Layer object.
        '''
        gdal.SetCacheMax(gdal_memory_limit)
        logging.debug(f"Flattening {self._path}")

        output_path = self.blank_copy()
        output_raster = gdal.Open(output_path, gdal.GA_Update)
        output_band = output_raster.GetRasterBand(1)

        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        nodata_value = self.nodata_value

        for chunk in self._chunk():
            raster_data = band.ReadAsArray(*chunk)
            if self.has_interpretation:
                raster_data[np.isin(raster_data, list(self._interpretation.keys()), invert=True)] = nodata_value
        
            raster_data[raster_data != nodata_value] = flattened_value
            output_band.WriteArray(raster_data, *chunk[:2])
    
        flattened_layer = Layer(output_path, self.year,
                                units=self._units if preserve_units else Units.Blank,
                                cache=self._cache)

        return flattened_layer

    def reproject(self, projection):
        '''
        Reprojects this layer to the specified projection.

        Arguments:
        'projection' -- the new projection, i.e. NAD83.
        '''
        output_path = TempFileManager.mktmp(suffix=".tif")
        gdal.SetCacheMax(gdal_memory_limit)
        gdal.Warp(output_path, self._path, dstSRS=projection, creationOptions=gdal_creation_options)

        reprojected_layer = Layer(output_path, self._year, self._interpretation,
                                  self._units, cache=self._cache,
                                  simulation_start_year=self._simulation_start_year)

        return reprojected_layer
    
    def _build_blend_function(self, layers):    
        no_data = self.nodata_value
        no_data_next = layers[0].nodata_value
        return lambda A: A[0] * (A[0] != no_data) + self._build_blend_function_helper(layers, no_data_next)(A[1:])
    
    def _build_blend_function_helper(self, layers, no_data):
        if not layers:
            return lambda A: 0
        else:
            no_data_next = layers[0].nodata_value
            return lambda A: layers[1](A, lambda layer: layer * (layer != no_data), 
                                       self._build_blend_function_helper(layers[2:], no_data_next))
        
    def _build_no_data_layer(self, layers):
        no_data = self.nodata_value
        no_data_next = layers[0].nodata_value
        return lambda A: no_data * ((A[0] == no_data) * self._build_no_data_helper(layers, no_data_next)(A[1:])) 
    
    def _build_no_data_helper(self, layers, no_data):
        if not layers:
            return lambda A: 1
        else:
            no_data_next = layers[0].nodata_value
            return lambda A: (A[0] == no_data) * (self._build_no_data_helper(layers[2:], no_data_next)(A[1:]))
        

    def blend(self, *layers):
        '''
        Blends this layer's values with one or more others.

        Arguments:
        'layers' -- one or more other layers to blend paired with the blend mode, i.e.
            some_layer.blend(layer_a, BlendMode.Add, layer_b, BlendMode.Subtract)
        '''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        blend_fn = self._build_blend_function(layers) 
        no_data_fn = self._build_no_data_layer(layers)
        
        calc_fn = lambda A: blend_fn(A) +  no_data_fn(A)
        
        output_path = TempFileManager.mktmp(suffix=".tif")
        gdal.SetCacheMax(gdal_memory_limit)
        
        GDALHelper.calc([self.path] + [layer.path for layer in layers[::2]], output_path, calc_fn=calc_fn)

        return Layer(output_path, self._year, self._interpretation, self._units, cache=self._cache)

    def render(self, legend, bounding_box=None, transparent=True):
        '''
        Renders this layer into a colorized Frame according to the specified legend.

        Arguments:
        'legend' -- dictionary of pixel value (or tuple of min/max value range) to
            dictionary containing the color tuple (R, G, B) and label for the entry.
        'bounding_box' -- optional bounding box Layer; this layer will be cropped
            to the bounding box's minimum spatial extent and nodata pixels.
        'transparent' -- whether or not nodata and 0-value pixels should be
            transparent in the rendered Frame.
        
        Returns this layer as a colorized Frame object.
        '''
        if self.is_multiband:
            raise UnsupportedOperation("unsupported for multiband layers")

        with open(TempFileManager.mktmp(suffix=".txt"), "w") as color_table:
            color_table_path = color_table.name
            color_table.write(f"nv 255,255,255,{0 if transparent else 255}\n")
            color_table.write(f"0 255,255,255,{0 if transparent else 255}\n")

            near_zero_value = None
            near_zero_color = None
            for value, entry in legend.items():
                color_str = ",".join((f"{v}" for v in entry["color"]))
                if isinstance(value, tuple):
                    range_min, range_max = value
                    if range_min is not None:
                        color_table.write(f"{range_min} {color_str},255\n")
                    if range_max is not None:
                        color_table.write(f"{range_max} {color_str},255\n")
                    if (    range_min is not None and range_min < 0
                        and range_max is not None and range_max > 0
                    ):
                        near_zero_value = 0
                        near_zero_color = color_str
                    else:
                        min_val = min((abs(range_min), abs(range_max)))
                        if near_zero_value is None or min_val < near_zero_value:
                            near_zero_value = min_val
                            near_zero_color = color_str
                else:
                    color_table.write(f"{value} {color_str},255\n")
                    if near_zero_value is None or abs(value) < near_zero_value:
                        near_zero_value = abs(value)
                        near_zero_color = color_str
            
            # Guard the color entry closest to 0 against the 0/nodata color.
            color_table.write(f"{-1e-3} {near_zero_color},255\n{1e-3} {near_zero_color},255\n")

        working_layer = self if not bounding_box else bounding_box.crop(self)
        rendered_layer_path = TempFileManager.mktmp(suffix=".png")
        subprocess.run([
            "gdaldem",
            "color-relief",
            working_layer.path,
            color_table.name,
            rendered_layer_path,
            "-q",
            "-alpha",
            "-nearest_color_entry"])

        return Frame(self._year, rendered_layer_path, self.scale)

    def blank_copy(self, output_path=None, data_type=None, nodata_value=None):
        '''
        Creates a blank (all nodata) copy of this layer with the same projection,
        resolution, and extent.

        Arguments:
        'output_path' -- path to the new layer to create, or omit to create a
            temporary layer.
        
        Returns the path to the blank copy.
        '''
        gdal.SetCacheMax(gdal_memory_limit)

        if not output_path:
            output_path = TempFileManager.mktmp(suffix=".tif")
        
        source_path = self._path
        if self.is_multiband:
            source_path = TempFileManager.mktmp(suffix=".tif")
            gdal.Translate(source_path, self._path, bandList=[1],
                           creationOptions=gdal_creation_options)

        driver = gdal.GetDriverByName("GTiff")
        original_raster = gdal.Open(source_path)
        new_raster = driver.CreateCopy(output_path, original_raster, strict=0,
                                       options=gdal_creation_options)
        
        if data_type is not None:
            transform_path = TempFileManager.mktmp(suffix=".tif")
            new_raster = None
            gdal.Translate(transform_path, output_path, outputType=data_type, creationOptions=gdal_creation_options)
            os.unlink(output_path)
            shutil.copyfile(transform_path, output_path)
            new_raster = gdal.Open(output_path, gdal.GA_Update)

        del original_raster
        nodata_value = nodata_value if nodata_value is not None else self.nodata_value
        band = new_raster.GetRasterBand(1)
        band.SetNoDataValue(nodata_value)
        for chunk in self._chunk():
            x_px_start, y_px_start, x_size, y_size = chunk
            band.WriteArray(np.full((y_size, x_size), nodata_value), x_px_start, y_px_start)

        return output_path

    def unpack(self, output_path=None, bands=None):
        '''
        If this is a multiband layer, unpacks this layer into separate single-band
        layers by year (or timestep, if start_year was not specified in the constructor).
        
        Arguments:
        'output_path' -- path to store the unpacked layers in, or omit to create
            them in a temporary directory that will be cleaned up on exit.
        'bands' -- a list of bands to unpack; can be either band numbers or years if
            simulation_start_year was specified in this layer's constructor.
        
        Returns a list of single-band layers by year or timestep.
        '''
        if not self.is_multiband:
            return [self]

        if output_path:
            Path(output_path).mkdir(parents=True, exist_ok=True)
        
        if bands:
            if self._simulation_start_year and all((band > 1000 for band in bands)):
                # Bands specified as years
                max_band = self._simulation_start_year + self.n_bands - 1
                bands = [band - self._simulation_start_year + 1 for band in bands if band <= max_band]
        else:
            bands = range(1, self.n_bands + 1)

        with ThreadPoolExecutor(pool_workers) as pool:
            tasks = []
            for band in bands:
                tasks.append(pool.submit(self._extract_band, band, output_path))
            
            unpacked_layers = [task.result() for task in tasks]
            
        return unpacked_layers
        
    def _extract_band(self, band, output_path=None):
        year = (self._simulation_start_year + band - 1) if self._simulation_start_year else band

        original_path = Path(self._path)
        if output_path:
            band_output_path = str(Path(output_path).joinpath(
                f"{original_path.stem}_{year}{original_path.suffix}"))
        else:
            band_output_path = TempFileManager.mktmp(suffix=original_path.suffix)
            
        gdal.SetCacheMax(gdal_memory_limit)
        gdal.Translate(band_output_path, self._path, bandList=[band],
                       creationOptions=gdal_creation_options)
        
        extracted_layer = Layer(band_output_path, year, self.interpretation, self.units, self._cache)
        
        return extracted_layer

    def _chunk(self, chunk_size=5000):
        '''Chunks this layer up for reading or writing.'''
        width, height = self.info["size"]

        y_chunk_starts = list(range(0, height, chunk_size))
        y_chunk_ends = [y - 1 for y in (y_chunk_starts[1:] + [height])]
        y_chunks = list(zip(y_chunk_starts, y_chunk_ends))
        
        x_chunk_starts = list(range(0, width, chunk_size))
        x_chunk_ends = [x - 1 for x in (x_chunk_starts[1:] + [width])]
        x_chunks = list(zip(x_chunk_starts, x_chunk_ends))

        for y_px_start, y_px_end in y_chunks:
            for x_px_start, x_px_end in x_chunks:
                y_size = y_px_end - y_px_start + 1
                x_size = x_px_end - x_px_start + 1

                yield (x_px_start, y_px_start, x_size, y_size)
