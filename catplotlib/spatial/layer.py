import json
import logging
import subprocess
import numpy as np
import pandas as pd
from pathlib import Path
from pandas import DataFrame
from enum import Enum
from string import ascii_uppercase
from catplotlib.util import gdal
from mojadata.util.gdal_calc import Calc
from mojadata.util.gdalhelper import GDALHelper
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
            value = GDALHelper.float32_range[0] if (
                dt == "float32" or dt == "float" or dt == str(gdal.GDT_Float32)
                or dt == "float64" or dt == str(gdal.GDT_Float64)
            ) else GDALHelper.int32_range[0]

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
            simple_conversion_calc = " ".join((
                f"(A.astype(numpy.float64) * {unit_conversion})",
                f"* (A != {nodata_value})",
                f"+ ((A == {nodata_value}) * {nodata_value})"))
        elif not self.is_lat_lon:
            per_ha_conversion_op = "*" if current_per_ha else "/"
            _, pixel_size, *_ = self.info["geoTransform"]
            pixel_size_m2 = float(pixel_size) ** 2
            per_ha_modifier = pixel_size_m2 / one_hectare if current_per_ha != new_per_ha else 1
            simple_conversion_calc = " ".join((
                f"(A.astype(numpy.float64) * {unit_conversion} {per_ha_conversion_op} {per_ha_modifier})",
                f"* (A != {nodata_value})",
                f"+ ((A == {nodata_value}) * {nodata_value})"))

        if simple_conversion_calc:
            Calc(simple_conversion_calc, output_path, nodata_value, quiet=True,
                 creation_options=gdal_creation_options, overwrite=True, A=self.path)

            return Layer(output_path, self._year, self._interpretation, units, cache=self._cache)

        area_raster_path = self.get_area_raster()
        per_ha_conversion_op = "*" if current_per_ha else "/"
        calc = " ".join((
            f"(A.astype(numpy.float64) * {unit_conversion} {per_ha_conversion_op} B)",
            f"* (A != {nodata_value})",
            f"+ ((A == {nodata_value}) * {nodata_value})"))

        Calc(calc, output_path, nodata_value, quiet=True, creation_options=gdal_creation_options,
             overwrite=True, A=self.path, B=area_raster_path)
        
        return Layer(output_path, self._year, self._interpretation, units, cache=self._cache)

    def aggregate(self, units=None, area_only=False):
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
        band = raster.GetRasterBand(1)
        nodata_value = self.nodata_value
        
        total_value = 0
        total_area = 0
        area_band = None
        for chunk in self._chunk():
            raster_data = band.ReadAsArray(*chunk).astype("float")

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
        nodata_value = self.nodata_value
        pixel_areas = None
        for chunk in self.read():
            if pixel_areas is None or pixel_areas.empty:
                pixel_areas = (
                    chunk[chunk != nodata_value]
                ).groupby([c for c in chunk.columns if c != "area"]).sum().reset_index()
            else:
                pixel_areas = pd.concat(
                    [pixel_areas, chunk[chunk != nodata_value]]
                ).groupby([c for c in chunk.columns if c != "area"]).sum().reset_index()
    
        return pixel_areas
    
    def read(self, chunk_size=5000):
        '''
        Read this layer in flattened chunks along with the attribute table (if applicable)
        and pixel area to help with overlays and summaries.
        
        Yields each chunk of data from the raster as a flattened DataFrame joined to per-
        pixel area, columns: value (pixel value), interpretation (if applicable), area (hectares).
        '''
        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        one_hectare = 100 ** 2
        
        area_band = None
        for chunk in self._chunk(chunk_size):
            raster_data = DataFrame(band.ReadAsArray(*chunk).flatten(), columns=["value"])
            if self.has_interpretation:
                raster_data = raster_data.join(DataFrame(
                    self._interpretation.values(), self._interpretation.keys(),
                    columns=["interpretation"]
                ), on="value").fillna("")

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
    
            yield raster_data
    
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
        orig_ndv = self.nodata_value
        if ((self.interpretation and self.interpretation.items() <= new_interpretation.items())
            and nodata_value == orig_ndv
        ):
            logging.debug(f"Attribute table already matches, skipping reclassify for {self._path}")
            return self

        gdal.SetCacheMax(gdal_memory_limit)
        logging.debug(f"Reclassifying {self._path}")

        output_path = TempFileManager.mktmp(suffix=".tif")
        inverse_new_interpretation = {v: k for k, v in new_interpretation.items()}

        px_calcs = (
            f"((A == {original_px}) * {inverse_new_interpretation.get(original_interp, nodata_value)})"
            for original_px, original_interp in self._interpretation.items()
        )

        calc = "+".join((
            f"((A == {orig_ndv}) * {nodata_value})",
            f"(isin(A, {list(new_interpretation.keys())}, invert=True) * {nodata_value})",
            *px_calcs
        ))

        Calc(calc, output_path, nodata_value, quiet=True, creation_options=gdal_creation_options,
             overwrite=True, hideNoData=False, A=self._path)

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
        nodata_value = self.nodata_value
        raster = gdal.Open(self._path)
        band = raster.GetRasterBand(1)
        raster_data = band.ReadAsArray()
        if self.has_interpretation:
            raster_data[np.isin(raster_data, list(self._interpretation.keys()), invert=True)] = nodata_value
        
        raster_data[raster_data != nodata_value] = flattened_value
        output_path = TempFileManager.mktmp(suffix=".tif")
        self._save_as(raster_data, nodata_value, output_path)
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
        nodata_value = self.nodata_value
        blend_layers = {
            ascii_uppercase[i]: (layer.convert_units(self._units), blend_mode)
            for i, (layer, blend_mode) in enumerate(zip(layers[::2], layers[1::2]), 1)
        }

        calc = f"(A * (A != {nodata_value}) "
        calc += " ".join((
            f"{blend_mode.value} ({layer_key} * ({layer_key} != {layer.nodata_value}))"
            for layer_key, (layer, blend_mode) in blend_layers.items()))

        calc += f") + (((A == {nodata_value}) * "
        calc += " * ".join((
            f"({layer_key} == {layer.nodata_value})"
            for layer_key, (layer, blend_mode) in blend_layers.items()))

        calc += f") * {nodata_value})"
        
        calc_args = {
            layer_key: layer.path
            for layer_key, (layer, blend_mode) in blend_layers.items()
        }

        logging.debug(f"Blending {calc_args} using: {calc}")
        output_path = TempFileManager.mktmp(suffix=".tif")
        gdal.SetCacheMax(gdal_memory_limit)
        Calc(calc, output_path, nodata_value, quiet=True, creation_options=gdal_creation_options,
             overwrite=True, hideNoData=True, A=self.path, **calc_args)

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

    def _chunk(self, chunk_size=5000):
        '''Chunks this layer up for reading or writing.'''
        width, height = self.info["size"]

        y_chunk_starts = list(range(0, height, chunk_size))
        y_chunk_ends = [y - 1 for y in (y_chunk_starts[1:] + [height])]
        y_chunks = list(zip(y_chunk_starts, y_chunk_ends))
        
        x_chunk_starts = list(range(0, width, chunk_size))
        x_chunk_ends = [x - 1 for x in (x_chunk_starts[1:] + [width])]
        x_chunks = list(zip(x_chunk_starts, x_chunk_ends))

        for i, (y_px_start, y_px_end) in enumerate(y_chunks):
            for j, (x_px_start, x_px_end) in enumerate(x_chunks):
                y_size = y_px_end - y_px_start + 1
                x_size = x_px_end - x_px_start + 1

                yield (x_px_start, y_px_start, x_size, y_size)

    def _save_as(self, data, nodata_value, output_path):
        gdal.SetCacheMax(gdal_memory_limit)
        driver = gdal.GetDriverByName("GTiff")
        original_raster = gdal.Open(self._path)
        new_raster = driver.CreateCopy(output_path, original_raster, strict=0,
                                       options=gdal_creation_options)

        band = new_raster.GetRasterBand(1)
        band.SetNoDataValue(nodata_value)
        band.WriteArray(data)
