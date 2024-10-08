from catplotlib.util import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os
import cartopy.crs as ccrs
from pyproj.crs import CRS
from pyproj.enums import WktVersion
from mojadata.util import osr
from catplotlib.util import gdal
from matplotlib.colors import ListedColormap
from matplotlib.colors import BoundaryNorm
from cartopy.io import DownloadWarning
from tempfile import TemporaryDirectory
from catplotlib.util.config import gdal_memory_limit
from catplotlib.util.config import gdal_creation_options

import warnings
warnings.simplefilter(action="ignore", category=DownloadWarning)

def show_raster_location(path, zoom=50):
    if not os.path.exists(path):
        return

    with TemporaryDirectory() as working_dir:
        working_path = os.path.join(
            working_dir, f"{os.path.splitext(os.path.basename(path))[0]}.tif")

        crs = ccrs.Mercator.GOOGLE
        proj_crs = CRS.from_dict(crs.proj4_params)
        osr_crs = osr.SpatialReference()
        osr_crs.ImportFromWkt(proj_crs.to_wkt(WktVersion.WKT1_GDAL))

        gdal.SetCacheMax(gdal_memory_limit)
        gdal.Warp(working_path, path, dstSRS=osr_crs,
                  creationOptions=gdal_creation_options)

        ds = gdal.Open(working_path)
        gt = ds.GetGeoTransform()

        fig, ax = plt.subplots(subplot_kw={"projection": crs})
        fig2, ax2 = plt.subplots(subplot_kw={"projection": crs})

        extent = (
            gt[0], gt[0] + ds.RasterXSize * gt[1],
            gt[3] + ds.RasterYSize * gt[5], gt[3])

        x_padding = (crs.x_limits[1] - crs.x_limits[0]) / zoom
        y_padding = (crs.y_limits[1] - crs.x_limits[0]) / zoom

        ax.set_extent((
            max(crs.x_limits[0], extent[0] - x_padding),
            min(crs.x_limits[1], extent[1] + x_padding),
            max(crs.y_limits[0], extent[2] - y_padding),
            min(crs.y_limits[1], extent[3] + y_padding)),
            crs=crs)

        ax.add_patch(mpatches.Rectangle(
            xy=(extent[0], extent[2]),
            width=extent[1] - extent[0], height=extent[3] - extent[2],
            edgecolor="red", linewidth=2, fill=False, transform=crs, zorder=1))
        
        ax.natural_earth_shp(category="cultural", name="admin_0_countries",
                             edgecolor="black", zorder=-1)

        band = ds.GetRasterBand(1)
        data = ds.ReadAsArray()
        data[data != band.GetNoDataValue()] = 1
        data[data == band.GetNoDataValue()] = 0
        cmap = ListedColormap([[0, 0, 0, 0], [0, 0.5, 0, 1]])
        norm = BoundaryNorm([0, 1, 2], cmap.N)

        for plt_ax in (ax, ax2):
            plt_ax.imshow(data, extent=extent, origin="upper", transform=crs,
                          cmap=cmap, norm=norm, interpolation="none", zorder=2)

        plt.show()
        ds = None
