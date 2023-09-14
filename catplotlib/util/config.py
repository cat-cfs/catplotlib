import psutil
from multiprocessing import cpu_count

max_threads = int(max(cpu_count(), 4))
gdal_threads = 4
pool_workers = max_threads
memory_limit_scale = int(max_threads / 10) or 1
catplotlib_memory_limit = int(psutil.virtual_memory().available * 0.75 / memory_limit_scale)
process_memory_limit = int(catplotlib_memory_limit / pool_workers)
gdal_memory_limit = int(process_memory_limit / gdal_threads)
gdal_creation_options = ["BIGTIFF=YES", "TILED=YES", "COMPRESS=ZSTD", "ZSTD_LEVEL=1", f"NUM_THREADS={gdal_threads}"]
