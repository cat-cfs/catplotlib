from enum import Enum
from catplotlib.util.loopingiterator import LoopingIterator

class Symbol(Enum):
                  # Plotly            Matplotlib
    Circle        = "circle",         "o"
    Square        = "square",         "s"
    Diamond       = "diamond",        "D"
    Cross         = "cross",          "P"
    X             = "x",              "X"
    TriangleUp    = "triangle-up",    "^"
    TriangleDown  = "triangle-down",  "v"
    TriangleLeft  = "triangle-left",  "<"
    TriangleRight = "triangle-right", ">"
    Pentagon      = "pentagon",       "p"
    Hexagon       = "hexagon",        "h"
    Star          = "star",           "*"

    @staticmethod
    def as_plotly(symbol):
        return symbol.value[0]

    @staticmethod
    def as_matplotlib(symbol):
        return symbol.value[1]


class Symbols:

    def __init__(self, symbols=None):
        symbols = symbols or [s for s in Symbol]
        self._symbols = LoopingIterator(symbols)

    def next(self):
        return next(self._symbols)
