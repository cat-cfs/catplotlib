class LoopingIterator:

    def __init__(self, values):
        self._values = values
        self._iter = iter(values)
    
    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._iter)
        except StopIteration:
            self._iter = iter(self._values)
            return next(self._iter)
