from catplotlib.util.loopingiterator import LoopingIterator

class Palette:

    def __init__(self, colors, *args, **kwargs):
        self._colors = LoopingIterator(colors)

    def next(self):
        return self._colors.next()
