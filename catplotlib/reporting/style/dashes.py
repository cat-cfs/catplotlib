from enum import Enum
from catplotlib.util.loopingiterator import LoopingIterator

class Dash(Enum):
                # Plotly         Matplotlib
    Solid       = "solid",       "solid"
    Dot         = "dot",         "dotted"
    Dashed      = "dash",        "dashed"
    LongDash    = "longdash",    (0, (5, 10))
    DashDot     = "dashdot",     "dashdot"
    LongDashDot = "longdashdot", (0, (3, 10, 1, 10))

    @staticmethod
    def as_plotly(dash):
        return dash.value[0]

    @staticmethod
    def as_matplotlib(dash):
        return dash.value[1]


class Dashes:

    def __init__(self, dashes=None):
        dashes = dashes or [d for d in Dash]
        self._dashes = LoopingIterator(dashes)

    def next(self):
        return next(self._dashes)
