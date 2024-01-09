import locale
import seaborn as sns

class Colorizer:
    '''
    Creates a legend and color scheme for a collection of layers.

    Arguments:
        'palette' -- the color palette to use. Can be the name of any seaborn palette
        (deep, muted, bright, pastel, dark, colorblind, hls, husl) or matplotlib
        colormap. To find matplotlib colormaps:
        from matplotlib import cm; dir(cm)
    '''

    def __init__(self, palette="hls", bins=6, **kwargs):
        self._palette = palette
        self._bins = bins

    def create_legend(self, layers):
        '''
        Creates a legend and color scheme for the specified group of layers.

        Arguments:
        'layers' -- list of Layer objects to create a legend and color scheme for.
        '''
        if not layers:
            return

        interpretation = layers[0].interpretation
        if interpretation:
            return self._create_interpreted_legend(layers, interpretation)
        
        return self._create_value_legend(layers)

    def _create_value_legend(self, layers):
        min_value = min((layer.min_max[0] for layer in layers)) - 0.5
        max_value = max((layer.min_max[1] for layer in layers)) + 0.5
        bin_size = (max_value - min_value) / self._bins
            
        colors = iter(self._create_colors(self._palette, self._bins))

        legend = {}
        for i in range(self._bins):
            if i == 0:
                value = min_value + bin_size
                legend[value] = {
                    "label": f"<= {self._format_value(value)}",
                    "color": next(colors)}
            elif i + 1 == self._bins:
                value = max_value - bin_size
                legend[value] = {
                    "label": f"> {self._format_value(value)}",
                    "color": next(colors)}
            else:
                range_min = min_value + i * bin_size
                range_max = min_value + (i + 1) * bin_size
                legend[(range_min, range_max)] = {
                    "label": (
                        f"{self._format_value(range_min)} " +
                        _("to") +
                        f" {self._format_value(range_max)}"),
                    "color": next(colors)}
       
        return legend

    def _create_interpreted_legend(self, layers, interpretation):
        colors = self._create_colors(self._palette, len(interpretation))
        colors_iter = iter(colors)

        legend = {}
        for pixel_value, interpreted_value in interpretation.items():
            legend[pixel_value] = {
                "label": interpreted_value,
                "color": next(colors_iter)}

        return legend

    def _format_value(self, value):
        return locale.format_string("%.2f", value) if isinstance(value, float) else f"{value}"

    def _create_colors(self, palette, n):
        rgb_pct_colors = sns.color_palette(palette, n)
        rgb_colors = [(int(r_pct * 255), int(g_pct * 255), int(b_pct * 255))
                      for r_pct, g_pct, b_pct in rgb_pct_colors]

        return rgb_colors
