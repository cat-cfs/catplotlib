class LoopingIterator:

    def __init__(self, values):
        self._values = values
        self._iter = iter(values)

    def next(self):
        try:
            return next(self._iter)
        except StopIteration:
            self._iter = iter(self._values)
            return next(self._iter)
