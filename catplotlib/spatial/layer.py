import gdal
import json
import logging
import os
import subprocess
import math
import numpy as np
from itertools import chain
from enum import Enum
from string import ascii_uppercase
from osgeo.scripts import gdal_calc
from geopy.distance import distance
from catplotlib.util.config import gdal_creation_options
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.tempfile import TempFileManager
from catplotlib.spatial.display.frame import Frame
from catplotlib.provider.units import Units
from catplotlib.util.cache import get_cache

class BlendMode(Enum):
    
    Add      = "+"
    Subtract = "-"


class Layer:
    '''
    Holds information about a layer to include in an animation. A layer applies
    to a single year, and the optional interpretation maps raster values to a
    single attribute value. If an interpretation is provided, any pixels not
    included are considered nodata.

    Arguments:
    'path' -- path to the layer file
    'year' -- the year the layer applies to
    'interpretation' -- optional attribute table for the raster; should be a
        dictionary of pixel value to interpretation, i.e. {1: "Wildfire"}
    'units' -- the units the layer's pixel values are in
    '''

    def __init__(self, path, year, interpretation=None, units=Units.TcPerHa, cache=None):
        self._path = path
        self._year = int(year)
        self._interpretation = interpretation
        self._units = units
        self._info = None
        self._cache = cache or get_cache()
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
    def min_max(self):
        '''Gets this layer's minimum and maximum pixel values.'''
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
        value = self.info["bands"][0]["noDataValue"]
        dt = str(self.data_type).lower()
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
            origin_x, pixel_size, _, origin_y, *_ = self.info["geoTransform"]
            pixel_size_m = distance((origin_y, origin_x), (origin_y, origin_x + pixel_size)).m

        return pixel_size_m

    @property
    def units(self):
        '''Gets this layer's units.'''
        return self._units

    def get_histogram(self, min_value, max_value, buckets):
        '''Computes a histogram for this layer.'''
        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        
        return band.GetHistogram(min=min_value, max=max_value, buckets=buckets)

    def convert_units(self, units):
        '''
        Converts this layer's values into new units - both scale and area type
        (per hectare or absolute).

        Arguments:
        'units' -- a new Units enum value to convert to

        Returns a copy of this layer in the new units as a new Layer object.
        '''
        if self._units == Units.Blank:
            return self

        gdal.SetCacheMax(gdal_memory_limit)
        current_per_ha, current_units_tc, current_units_name = self._units.value
        new_per_ha, new_units_tc, new_units_name = units.value
        unit_conversion = current_units_tc / new_units_tc

        if current_per_ha == new_per_ha and unit_conversion == 1:
            self._units = units
            return self

        output_path = TempFileManager.mktmp(suffix=".tif")
        one_hectare = 100 ** 2

        simple_conversion_calc = None
        if current_per_ha == new_per_ha:
            simple_conversion_calc = " ".join((
                f"(A.astype(numpy.float64) * {unit_conversion})",
                f"* (A != {self.nodata_value})",
                f"+ ((A == {self.nodata_value}) * {self.nodata_value})"))
        elif "metre" in self.info["coordinateSystem"]["wkt"]:
            per_ha_conversion_op = "*" if current_per_ha else "/"
            _, pixel_size, *_ = self.info["geoTransform"]
            pixel_size_m2 = float(pixel_size) ** 2
            per_ha_modifier = pixel_size_m2 / one_hectare if current_per_ha != new_per_ha else 1
            simple_conversion_calc = " ".join((
                f"(A.astype(numpy.float64) * {unit_conversion} {per_ha_conversion_op} {per_ha_modifier})",
                f"* (A != {self.nodata_value})",
                f"+ ((A == {self.nodata_value}) * {self.nodata_value})"))

        if simple_conversion_calc:
            gdal_calc.Calc(simple_conversion_calc, output_path, self.nodata_value, quiet=True,
                           creation_options=gdal_creation_options,
                           overwrite=True, A=self.path)

            return Layer(output_path, self._year, self._interpretation, units, cache=self._cache)

        area_raster_path = self.get_area_raster()
        per_ha_conversion_op = "*" if current_per_ha else "/"
        calc = " ".join((
            f"(A.astype(numpy.float64) * {unit_conversion} {per_ha_conversion_op} B)",
            f"* (A != {self.nodata_value})",
            f"+ ((A == {self.nodata_value}) * {self.nodata_value})"))

        gdal_calc.Calc(calc, output_path, self.nodata_value, quiet=True,
                       creation_options=gdal_creation_options,
                       overwrite=True, A=self.path, B=area_raster_path)
        
        return Layer(output_path, self._year, self._interpretation, units, cache=self._cache)

    def aggregate(self, units=None):
        '''
        Aggregates this layer's non-nodata pixels into either the sum (for a layer of absolute
        values), or the average per-hectare value (for a layer of per-hectare values). If 'units'
        is specified, the layer's native units are converted to the target units before the above
        rule is applied.

        Arguments:
        'units' -- a new Units enum value to convert to

        Returns the sum or the average per-hectare value of the non-nodata pixels.
        '''
        gdal.SetCacheMax(gdal_memory_limit)
        current_per_ha, current_units_tc, current_units_name = self._units.value
        new_per_ha, new_units_tc, new_units_name = units.value if units else self._units.value
        unit_conversion = current_units_tc / new_units_tc
        one_hectare = 100 ** 2

        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        raster_data = band.ReadAsArray()
        nodata_value = self.nodata_value

        # First need to convert pixel values to absolute (as opposed to per hectare), in the correct
        # units (tc/ktc/mtc), and determine the total area of non-nodata pixels.
        if "metre" in self.info["coordinateSystem"]["wkt"]:
            _, pixel_size, *_ = self.info["geoTransform"]
            pixel_size_m2 = float(pixel_size) ** 2
            per_ha_modifier = pixel_size_m2 / one_hectare if current_per_ha else 1
            raster_data[raster_data != nodata_value] *= unit_conversion * per_ha_modifier
            total_area = len(raster_data[raster_data != nodata_value]) * pixel_size_m2 / one_hectare
        else:
            raster_data[raster_data != nodata_value] *= unit_conversion

            area_raster_path = self.get_area_raster()
            area_raster = gdal.Open(area_raster_path)
            area_band = area_raster.GetRasterBand(1)
            area_data = area_band.ReadAsArray()
            total_area = area_data[raster_data != nodata_value].sum()

            if current_per_ha:
                raster_data[raster_data != nodata_value] *= area_data[raster_data != nodata_value]

        raster_data[raster_data == nodata_value] = 0
        total_value = raster_data.sum() / (total_area if new_per_ha else 1)

        return total_value

    def chunk(self, chunk_size=5):
        '''
        Chunks this layer up into blocks, returning the corner coordinates in
        lat/lon and the x/y pixel offset suitable for writing.

        Arguments:
        'chunk_size' -- the maximum chunk size in lat/lon, yielding chunks of
            chunk_size^2

        Returns (xmin, xmax, ymin, ymax), (x_pixel_offset, y_pixel_offset)
        '''
        bounds = self.info["cornerCoordinates"]
        xmin, ymin = bounds["upperLeft"]
        xmax, ymax = bounds["lowerRight"]

        whole_xmin = math.ceil(xmin)
        whole_ymin = math.floor(ymin)
        whole_xmax = math.floor(xmax)
        whole_ymax = math.ceil(ymax)

        geotransform = self.info["geoTransform"]
        resolution = geotransform[1]

        if abs(xmax - xmin) <= chunk_size:
            x_segments = [xmin, xmax]
        else:
            x_segments = [xmin] + list(range(
                whole_xmin, whole_xmax,
                chunk_size if whole_xmin < whole_xmax else -chunk_size)) + [xmax]

        if abs(ymax - ymin) <= chunk_size:
            y_segments = [ymin, ymax]
        else:
            y_segments = [ymin] + list(range(
                whole_ymin, whole_ymax,
                chunk_size if whole_ymin < whole_ymax else -chunk_size)) + [ymax]

        for chunk_y_idx in range(len(y_segments) - 1):
            chunk_y_min = y_segments[chunk_y_idx]
            chunk_y_max = y_segments[chunk_y_idx + 1]
            y_px_offset = int(abs(chunk_y_min - ymin) / resolution)
            for chunk_x_idx in range(len(x_segments) - 1):
                chunk_x_min = x_segments[chunk_x_idx]
                chunk_x_max = x_segments[chunk_x_idx + 1]
                x_px_offset = int(abs(chunk_x_min - xmin) / resolution)
                
                yield (chunk_x_min, chunk_x_max, chunk_y_min, chunk_y_max), (x_px_offset, y_px_offset)

    def area_grid(self, xmin, xmax, ymin, ymax, resolution):
        '''
        Returns a grid for the specified extent and resolution in degrees lat/lon
        where each pixel's value is its area in hectares.

        Arguments:
        'xmin' -- top-left corner x coordinate
        'xmax' -- bottom-right corner x coordinate
        'ymin' -- top-left corner y coordinate
        'ymax' -- bottom-right corner y coordinate
        'resolution' -- pixel resolution in degrees
        '''
        m_per_hectare = 100 ** 2
        n_lats = int(abs(xmax - xmin) / resolution)
        pi = 3.141592653590
        lats = np.arange(ymin, ymax, resolution * (-1 if ymin > ymax else 1))
        earth_diameter_m_per_deg = 2.0 * pi * 6378137.0 / 360.0
        area = np.abs(np.ones(n_lats)[:, None] * resolution**2 * earth_diameter_m_per_deg**2
                      * np.cos(lats[:-1] * pi / 180.0) / m_per_hectare)
        
        return area.T

    def get_area_raster(self):
        '''
        Generates and caches an area raster for this layer's spatial extent and
        resolution.

        Returns the path to the area raster.
        '''
        geotransform = self.info["geoTransform"]
        resolution = geotransform[1]
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
            area_raster = driver.CreateCopy(area_raster_path, original_raster, strict=0,
                                            options=gdal_creation_options)

            band = area_raster.GetRasterBand(1)
            for extent, px_offset in self.chunk():
                band.WriteArray(self.area_grid(*extent, resolution), *px_offset)

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
        gdal.SetCacheMax(gdal_memory_limit)
        logging.debug(f"Reclassifying {self._path}")
        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        raster_data = band.ReadAsArray()

        uninterpreted_values = np.isin(raster_data, list(self._interpretation.keys()), invert=True)
        raster_data[uninterpreted_values] = nodata_value
        
        # Guard against conflicts between original and reclassified pixel values
        # before updating anything.
        collision_offset = max(chain(self._interpretation.keys(), new_interpretation.keys()), default=0) + 1
        raster_data[raster_data != nodata_value] += collision_offset

        inverse_new_interpretation = {v: k for k, v in new_interpretation.items()}
        for original_pixel_value, interpreted_value in self._interpretation.items():
            new_pixel_value = inverse_new_interpretation[interpreted_value] \
                if interpreted_value in inverse_new_interpretation \
                else nodata_value

            if new_pixel_value == nodata_value:
                logging.info(f"  No new pixel value for {interpreted_value}: setting to nodata ({nodata_value})")

            raster_data[raster_data == original_pixel_value + collision_offset] = new_pixel_value

        output_path = TempFileManager.mktmp(suffix=".tif")
        self._save_as(raster_data, nodata_value, output_path)
        reclassified_layer = Layer(output_path, self._year, new_interpretation, self._units, cache=self._cache)

        return reclassified_layer

    def flatten(self, flattened_value=1, preserve_units=False):
        '''
        Flattens a copy of this layer: all non-nodata pixels become the target value.

        Arguments:
        'flattened_value' -- the value to set all data pixels to.
        'preserve_units' -- preserve the units (Units.TcPerHa, etc.) of this layer in
            the flattened copy - otherwise set to Units.Blank.

        Returns a new flattened Layer object.
        '''
        gdal.SetCacheMax(gdal_memory_limit)
        logging.debug(f"Flattening {self._path}")
        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        raster_data = band.ReadAsArray()
        raster_data[raster_data != self.nodata_value] = flattened_value
        output_path = TempFileManager.mktmp(suffix=".tif")
        self._save_as(raster_data, self.nodata_value, output_path)
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
                                  self._units, cache=self._cache)

        return reprojected_layer

    def blend(self, *layers):
        '''
        Blends this layer's values with one or more others.

        Arguments:
        'layers' -- one or more other layers to blend paired with the blend mode, i.e.
            some_layer.blend(layer_a, BlendMode.Add, layer_b, BlendMode.Subtract)
        '''
        blend_layers = {
            ascii_uppercase[i]: (layer.convert_units(self._units), blend_mode)
            for i, (layer, blend_mode) in enumerate(zip(layers[::2], layers[1::2]), 1)
        }

        calc = "(A "
        calc += " ".join((
            f"{blend_mode.value} {layer_key}"
            for layer_key, (layer, blend_mode) in blend_layers.items()))

        calc += f") * (A != {self.nodata_value}) * "
        calc += " * ".join((
            f"({layer_key} != {layer.nodata_value})"
            for layer_key, (layer, blend_mode) in blend_layers.items()))

        calc_args = {
            layer_key: layer.path
            for layer_key, (layer, blend_mode) in blend_layers.items()
        }

        logging.debug(f"Blending {calc_args} using: {calc}")
        output_path = TempFileManager.mktmp(suffix=".tif")
        gdal.SetCacheMax(gdal_memory_limit)
        gdal_calc.Calc(calc, output_path, self.nodata_value, quiet=True,
                       creation_options=gdal_creation_options,
                       overwrite=True, A=self.path, **calc_args)

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

    def _save_as(self, data, nodata_value, output_path):
        gdal.SetCacheMax(gdal_memory_limit)
        driver = gdal.GetDriverByName("GTiff")
        original_raster = gdal.Open(self._path)
        new_raster = driver.CreateCopy(output_path, original_raster, strict=0,
                                       options=gdal_creation_options)

        band = new_raster.GetRasterBand(1)
        band.SetNoDataValue(nodata_value)
        band.WriteArray(data)
