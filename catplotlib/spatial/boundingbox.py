import numpy as np
from multiprocessing import Pool
from catplotlib.util import gdal
from mojadata.util.gdalhelper import GDALHelper
from catplotlib.spatial.layer import Layer
from catplotlib.spatial.layercollection import LayerCollection
from catplotlib.util.config import gdal_creation_options
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.tempfile import TempFileManager

class BoundingBox(Layer):
    '''
    A type of Layer that can crop other Layer objects to its minimum spatial extent
    and nodata pixels.

    Arguments:
    'path' -- path to a raster file to use as a bounding box.
    'projection' -- projection to override the bounding box layer's with.
    'crop_to_data' -- crop the bounding box extent to the non-nodata pixels (default: True).
    '''

    def __init__(self, path, projection=None, crop_to_data=True, **kwargs):
        super().__init__(path, 0, **kwargs)
        self._min_pixel_bounds = None
        self._min_geographic_bounds = None
        self._initialized = False
        self._projection = projection
        self._crop_to_data = crop_to_data
    
    @property
    def min_pixel_bounds(self):
        '''
        The minimum pixel bounds of the bounding box: the minimum box surrounding
        the non-nodata pixels in the layer.
        '''
        if not self._min_pixel_bounds:
            raster_data = gdal.Open(self._path).ReadAsArray()
            x_min = raster_data.shape[1]
            x_max = 0
            y_min = 0
            y_max = 0
            for i, row in enumerate(raster_data):
                x_index = np.where(row != self.nodata_value)[0] # First non-null value per row.
                if len(x_index) == 0:
                    continue

                x_index_min = np.min(x_index)
                x_index_max = np.max(x_index)
                y_min = i           if y_min == 0          else y_min
                x_min = x_index_min if x_index_min < x_min else x_min
                x_max = x_index_max if x_index_max > x_max else x_max
                y_max = i

            self._min_pixel_bounds = [x_min - 1, x_max + 1, y_min - 1, y_max + 1]

        return self._min_pixel_bounds

    @property
    def min_geographic_bounds(self):
        '''
        The minimum spatial extent of the bounding box: the minimum box surrounding
        the non-nodata pixels in the layer.
        '''
        if not self._min_geographic_bounds:
            x_min, x_max, y_min, y_max = self.min_pixel_bounds
            origin_x, x_size, _, origin_y, _, y_size, *_ = gdal.Open(self._path).GetGeoTransform()
       
            all_geog_x = (origin_x + x_min * x_size, origin_x + x_max * x_size)
            all_geog_y = (origin_y + y_min * y_size, origin_y + y_max * y_size)
            
            self._min_geographic_bounds = [
                min(all_geog_x), min(all_geog_y),
                max(all_geog_x), max(all_geog_y)
            ]

        return self._min_geographic_bounds

    def init(self):
        '''
        Explicitly initializes the bounding box instead of waiting for it to happen
        as needed - can be useful for avoiding redundant initialization steps in
        multiprocessing.
        '''
        if not self._initialized:
            self._init()

    def crop(self, layer, crop_to_data=True):
        '''
        Crops a Layer or LayerCollection to the minimum spatial extent and nodata
        pixels of this bounding box.

        Arguments:
        'layer' -- the layer to crop.

        Returns a new cropped Layer object.
        '''
        if isinstance(layer, LayerCollection):
            with Pool() as pool:
                tasks = []
                for original_layer in layer.layers:
                    tasks.append(pool.apply_async(
                        self._crop,
                        (original_layer, crop_to_data)
                    ))
        
                pool.close()
                pool.join()
        
                return LayerCollection([result.get() for result in tasks])
        else:
            return self._crop(layer, crop_to_data)

    def _crop(self, layer, crop_to_data=True):
        if not self._initialized:
            self._init()

        # Clip to bounding box geographical area.
        tmp_path = TempFileManager.mktmp(suffix=".tif")
        width, height = self.info["size"]
        gdal.SetCacheMax(gdal_memory_limit)
        gdal.Warp(tmp_path, layer.path, dstSRS=self._get_srs(), creationOptions=gdal_creation_options,
                  width=width, height=height,
                  outputBounds=(self.info["cornerCoordinates"]["upperLeft"][0],
                                self.info["cornerCoordinates"]["lowerRight"][1],
                                self.info["cornerCoordinates"]["lowerRight"][0],
                                self.info["cornerCoordinates"]["upperLeft"][1]))
        
        if not crop_to_data:
            return Layer(tmp_path, layer.year, layer.interpretation, layer.units, self._cache)

        # Clip to bounding box nodata mask.
        calc_fn = lambda A: A[0] * (A[1] != self.nodata_value + ((A[1] == self.nodata_value) * layer.nodata_value))
        output_path = TempFileManager.mktmp(suffix=".tif")
        GDALHelper.calc([tmp_path, self.path], output_path, calc_fn )

        cropped_layer = Layer(output_path, layer.year, layer.interpretation, layer.units, self._cache)

        return cropped_layer

    def _init(self):
        source_path = self._path
        if self.is_multiband:
            source_path = TempFileManager.mktmp(suffix=".tif")
            gdal.Translate(source_path, self._path, bandList=[1],
                           creationOptions=gdal_creation_options)

        bbox_path = TempFileManager.mktmp(no_manual_cleanup=True, suffix=".tif")
        gdal.SetCacheMax(gdal_memory_limit)
        gdal.Warp(bbox_path, source_path,
                  dstSRS=self._projection or self._get_srs(),
                  creationOptions=gdal_creation_options)

        # Warp again to fix projection issues - sometimes will be flipped vertically
        # from the original.
        final_bbox_path = TempFileManager.mktmp(no_manual_cleanup=True, suffix=".tif")
        gdal.Warp(
            final_bbox_path, bbox_path, creationOptions=gdal_creation_options,
            outputBounds=(
                BoundingBox(bbox_path, cache=self._cache).min_geographic_bounds
                if self._crop_to_data
                else None
            )
        )

        self._path = final_bbox_path
        self._min_geographic_bounds = None
        self._min_pixel_bounds = None
        self._info = None
        self._initialized = True

    def _get_srs(self):
        layer_data = gdal.Open(self._path)
        srs = layer_data.GetProjection()

        return srs
