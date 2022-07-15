from plotly.colors import color_parser
from plotly.colors import unlabel_rgb
from catplotlib.util.loopingiterator import LoopingIterator

class Palette:

    def __init__(self, colors, *args, **kwargs):
        if any(("rgb(" in str(c) for c in colors)):
            colors = color_parser(colors, lambda c:
                f"#{''.join((hex(int(channel))[2:].ljust(2, '0') for channel in unlabel_rgb(c)))}")

        self._colors = colors
        self._iter = LoopingIterator(colors)

    def next(self):
        return next(self._iter)

    def copy(self):
        return self.__class__(self._colors)
