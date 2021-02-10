import utm
import gdal

utm_zone_projections = {
     7: "EPSG:3154",
     8: "EPSG:3155",
     9: "EPSG:3156",
    10: "EPSG:3157",
    11: "EPSG:2955",
    12: "EPSG:2956",
    13: "EPSG:2957",
    14: "EPSG:3158",
    15: "EPSG:3159",
    16: "EPSG:3160",
    17: "EPSG:2958",
    18: "EPSG:2959",
    19: "EPSG:2960",
    20: "EPSG:2961",
    21: "EPSG:2962",
    22: "EPSG:3761"
}

def find_best_projection(layer):
    '''
    Finds the best equal-area projection for a layer by the location of its
    center point.

    Arguments:
    'layer' -- the layer to find the best projection for.

    Returns the most suitable EPSG projection string.
    '''
    # Find layer center point.
    src = gdal.Open(layer.path)
    ulx, xres, xskew, uly, yskew, yres  = src.GetGeoTransform()
    center_x = ulx + src.RasterXSize * xres / 2
    center_y = uly + src.RasterYSize * yres / 2
    
    # Get UTM zone intersecting with center point.
    utm_zone = utm.latlon_to_zone_number(center_y, center_x)

    return utm_zone_projections.get(utm_zone)
