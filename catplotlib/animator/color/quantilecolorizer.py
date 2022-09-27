# Suppress deprecated API warning from older version of PySAL.
import warnings
warnings.simplefilter("ignore")

import gdal
import psutil
import numpy as np
import seaborn as sns
from enum import Enum
from pysal.esda.mapclassify import Quantiles
from catplotlib.animator.color.colorizer import Colorizer
from catplotlib.util.config import gdal_memory_limit

class Filter(Enum):

    Negative = -1
    Positive =  1


class QuantileColorizer(Colorizer):
    '''
    Creates a legend using quantiles - usually shows more activity in rendered
    maps than the standard Colorizer's equal bin size method. Accepts the standard
    Colorizer constructor arguments plus some CustomColorizer-specific settings.

    Arguments:
    'negative_palette' -- optional second color palette name for the value range
        below 0; if provided, value bins are split into above and below zero, with
        positive values using the colors from the 'palette' argument. By default,
        the entire value range (+/-) is binned and colorized together.
    '''

    def __init__(self, negative_palette=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._negative_palette = negative_palette

    def _create_value_legend(self, layers):
        if self._negative_palette:
            return self._create_split_value_legend(layers)
        else:
            return self._create_simple_value_legend(layers)

    def _create_simple_value_legend(self, layers):
        quantile_data = self._get_quantile_dataset(layers)
        quantiles = Quantiles(quantile_data, k=self._bins)
        bins = quantiles.bins
        colors = self._create_colors(self._palette, self._bins)

        legend = {}
        for i, upper_bound in enumerate(bins):
            if i == 0:
                legend[upper_bound] = {
                    "label": f"<= {self._format_value(upper_bound)}",
                    "color": next(colors)}
            else:
                lower_bound = bins[i - 1]
                legend[(lower_bound, upper_bound)] = {
                    "label": (
                        f"{self._format_value(lower_bound)} " +
                        _("to") +
                        f" {self._format_value(upper_bound)}"),
                    "color": next(colors)}
       
        return legend

    def _create_split_value_legend(self, layers):
        legend = {}
        k = self._bins // 2

        negative_data = self._get_quantile_dataset(layers, Filter.Negative)
        negative_quantiles = Quantiles(negative_data, k=k)
        negative_bins = list(negative_quantiles.bins)
        negative_colors = list(self._create_colors(self._negative_palette, k))
        negative_quantiles = None
        negative_data = None

        for i, upper_bound in enumerate(negative_bins):
            if i == 0:
                legend[upper_bound] = {
                    "label": f"<= {self._format_value(upper_bound)}",
                    "color": negative_colors[-i - 1]}
            else:
                upper_bound = 0 if i == k - 1 else upper_bound
                lower_bound = negative_bins[i - 1]
                legend[(lower_bound, upper_bound)] = {
                    "label": f"{self._format_value(lower_bound)} to {self._format_value(upper_bound)}",
                    "color": negative_colors[-i - 1]}

        positive_data = self._get_quantile_dataset(layers, Filter.Positive)
        positive_quantiles = Quantiles(positive_data, k=k)
        positive_bins = positive_quantiles.bins
        positive_colors = self._create_colors(self._palette, k)
        positive_quantiles = None
        positive_data = None

        for i, upper_bound in enumerate(positive_bins):
            lower_bound = 0 if i == 0 else positive_bins[i - 1]
            legend[(lower_bound, upper_bound)] = {
                "label": f"{self._format_value(lower_bound)} to {self._format_value(upper_bound)}",
                "color": next(positive_colors)}

        return legend

    def _get_quantile_dataset(self, layers, filter=None):
        # Cap the maximum amount of data to load to avoid running out of memory.
        data_points_per_layer = int(psutil.virtual_memory().available * 0.75 / (64 / 8) / len(layers) / 4)

        all_layer_data = np.empty(shape=(0, 0))
        for layer in layers:
            layer_data = self._load_layer_data(layer, filter)
            if layer_data.size > data_points_per_layer:
                # Keep the min/max values when trimming the dataset so that the
                # legend ranges are correct.
                data_bounds = [layer_data.min(), layer_data.max()]
                layer_data = np.random.choice(layer_data, data_points_per_layer)
                layer_data = np.append(layer_data, data_bounds)

            all_layer_data = np.append(all_layer_data, layer_data)

        return all_layer_data

    def _load_layer_data(self, layer, filter=None):
        raster = gdal.Open(layer.path)
        raster_data = raster.GetRasterBand(1).ReadAsArray()
        raster_data = raster_data.reshape(raster_data.size)
        raster_data = raster_data[
            (raster_data != layer.nodata_value) &
            (~np.isnan(raster_data)) &
            (raster_data != 0)
        ]

        raster_data = raster_data[raster_data <= 0] if filter == Filter.Negative \
                 else raster_data[raster_data  > 0] if filter == Filter.Positive \
                 else raster_data

        return raster_data
