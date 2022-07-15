import psutil
from multiprocessing import cpu_count

gdal_memory_limit = int(psutil.virtual_memory().total * 0.75 / cpu_count())
gdal_creation_options = ["BIGTIFF=YES", "TILED=YES", "COMPRESS=ZSTD", "ZSTD_LEVEL=1", "NUM_THREADS=ALL_CPUS"]
