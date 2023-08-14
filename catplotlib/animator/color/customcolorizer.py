import seaborn as sns
from collections import OrderedDict
from catplotlib.animator.color.colorizer import Colorizer

class CustomColorizer(Colorizer):
    '''
    Colorizes a set of layers based on a user-provided color scheme. Accepts the
    standard Colorizer constructor arguments plus some CustomColorizer-specific
    settings.

    Arguments:
    'custom_colors' -- a dictionary of tuples of interpreted value to the name of
        a color palette to group the interpreted values by.
    'value_colorizer' -- optional alternative colorizer to use for creating legend
        for layers with no interpretation; if not provided, uses the default method.
    '''

    def __init__(self, custom_colors, value_colorizer=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value_colorizer = value_colorizer
        self._custom_colors = custom_colors

    def _create_value_legend(self, layers):
        if self._value_colorizer:
            return self._value_colorizer.create_legend(layers)

        return super()._create_value_legend(layers)

    def _create_interpreted_legend(self, layers, interpretation):
        color_map = {}
        for interpreted_values, palette in self._custom_colors.items():
            if isinstance(interpreted_values, str):
                interpreted_values = (interpreted_values,)

            colors = self._create_colors(palette, len(interpreted_values))
            colors_iter = iter(colors)
            for value in interpreted_values:
                color_map[value] = next(colors_iter)

        uncustomized_values = set(interpretation.values()) - set(color_map.keys())
        if uncustomized_values:
            colors = self._create_colors(self._palette, len(uncustomized_values))
            colors_iter = iter(colors)
            for value in uncustomized_values:
                color_map[value] = next(colors_iter)

        inverted_original_interpretation = {v: k for k, v in interpretation.items()}

        legend = OrderedDict()
        for interpreted_value, color in color_map.items():
            pixel_value = inverted_original_interpretation.get(interpreted_value)
            if not pixel_value:
                continue

            legend[pixel_value] = {
                "label": interpreted_value,
                "color": color}

        return legend
