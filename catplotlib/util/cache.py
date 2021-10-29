from multiprocessing import Manager
from multiprocessing import Lock

class Cache:
    
    def __init__(self, lock, storage):
        self.lock = lock
        self.storage = storage

def get_cache():
    if "catplotlib_manager" not in globals():
        global catplotlib_manager
        catplotlib_manager = Manager()
    
    if "catplotlib_cache" not in globals():
        global catplotlib_cache
        catplotlib_cache = Cache(catplotlib_manager.Lock(), catplotlib_manager.dict())
    
    return catplotlib_cache
