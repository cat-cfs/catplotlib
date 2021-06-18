from plotly.express.colors import qualitative as plotly_colors
from catplotlib.reporting.style.palette import Palette
from catplotlib.reporting.style.symbols import Symbols
from catplotlib.reporting.style.dashes import Dashes

class StyleManager:

    def __init__(self, palette=None, symbols=None, dashes=None):
        self._palette = palette or Palette(plotly_colors.Plotly)
        self._symbols = symbols or Symbols()
        self._dashes = dashes or Dashes()
        self._cache = {}

    def style(self, data):
        if data is None or data.empty:
            return

        styles = {
            col: {
                "color":  self._cache.get(col, {}).get("color") or self._palette.next(),
                "symbol": self._cache.get(col, {}).get("symbol") or self._symbols.next(),
                "dash":   self._cache.get(col, {}).get("dash") or self._dashes.next()
            } for col in data.columns if col != "year"
        }

        self._cache.update(styles)

        return styles
