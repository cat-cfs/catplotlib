import psutil
from multiprocessing import cpu_count

gdal_threads = min(cpu_count(), 4)
pool_workers = cpu_count()
memory_limit_scale = int(cpu_count() / 10) or 1
catplotlib_memory_limit = int(psutil.virtual_memory().available * 0.75 / memory_limit_scale)
process_memory_limit = int(catplotlib_memory_limit / pool_workers)
gdal_memory_limit = int(process_memory_limit / gdal_threads)
gdal_creation_options = ["BIGTIFF=YES", "TILED=YES", "COMPRESS=ZSTD", "ZSTD_LEVEL=1", f"NUM_THREADS={gdal_threads}"]
