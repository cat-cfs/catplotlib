import matplotlib
matplotlib.use('Agg')

from catplotlib.util.config import *

from mojadata.util import gdal
gdal.SetConfigOption("GDAL_SWATH_SIZE",              str(gdal_memory_limit))
gdal.SetConfigOption("VSI_CACHE",                    "TRUE")
gdal.SetConfigOption("VSI_CACHE_SIZE",               str(int(gdal_memory_limit / pool_workers)))
gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
gdal.SetConfigOption("GDAL_PAM_ENABLED",             "NO")
gdal.SetConfigOption("GDAL_GEOREF_SOURCES",          "INTERNAL,NONE")
gdal.SetConfigOption("GTIFF_DIRECT_IO",              "YES")
gdal.SetConfigOption("GDAL_MAX_DATASET_POOL_SIZE",   "50000")
