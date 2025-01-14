import locale
import numpy as np
from contextlib import contextmanager
from catplotlib.util import matplotlib
from matplotlib import image as mpimg
from matplotlib import pyplot as plt
from matplotlib import gridspec
from matplotlib.ticker import MaxNLocator
from catplotlib.animator.plot.resultsplot import ResultsPlot
from catplotlib.spatial.display.frame import Frame
from catplotlib.util.tempfile import TempFileManager

class BasicResultsPlot(ResultsPlot):

    def __init__(self, title, provider, indicator, units):
        self._title = title
        self._provider = provider
        self._indicator = indicator
        self._units = units

    def render(self, start_year=None, end_year=None, provider_filter=None, **kwargs):
        '''
        Renders the configured plot into a graph.

        Arguments:
        Any accepted by GCBMResultsProvider and subclasses.

        Returns a list of Frames, one for each year of output.
        '''
        indicator = (provider_filter or {}).get("indicator", self._indicator)
        indicator_data = self._provider.get_annual_result(
            self._indicator, start_year, end_year, self._units, **kwargs)
        
        value_key = next((key for key in indicator_data.keys() if str(key).lower() != "year"))
        years = sorted(indicator_data.year.tolist())
        values = indicator_data[value_key]

        frames = []
        for i, year in enumerate(years):
            with self._figure(figsize=(10, 5)) as fig:
                y_label = f"{self._title} ({_(self._units.value[2])})"
                plt.xlabel(_("Years"), fontweight="bold", fontsize=14)
                plt.ylabel(y_label, fontweight="bold", fontsize=14)
                plt.axhline(0, color="darkgray")
                plt.plot(years, values, marker="o", linestyle="--", color="navy")
                
                # Mark the current year.
                plt.plot(year, indicator_data[indicator_data["year"] == year][value_key],
                         marker="o", linestyle="--", color="b", markersize=15, zorder=3)

                axis_min = min(values) - 0.1
                if not np.isfinite(axis_min):
                    axis_min = 0

                axis_max = max(values) + 0.1
                if not np.isfinite(axis_max):
                    axis_max = 0

                plt.axis([None, None, axis_min, axis_max])
                plt.tick_params(axis="both", labelsize=14)
                plt.xticks(fontsize=12, fontweight="bold")
                plt.yticks(fontsize=12, fontweight="bold")

                # Remove scientific notation.
                ax = plt.gca()
                ax.get_yaxis().get_major_formatter().set_useOffset(False)
                ax.set_yticklabels([
                    locale.format_string("%.2f", value)
                    for value in ax.get_yticks()])

                # Ensure integer tick labels.
                ax.get_xaxis().set_major_locator(MaxNLocator(integer=True))

                # Shade underneath the value series behind the current year.
                shaded_years = np.array(years)
                shaded_values = np.array(values).copy()
                shaded_values[shaded_years > year] = np.nan
                plt.fill_between(shaded_years, shaded_values, facecolor="gainsboro", zorder=1)

                # Add a vertical line at the current year.
                pos = year - 0.2 if i == len(years) - 1 else year + 0.2
                plt.axvspan(year, pos, facecolor="g", alpha=0.5, zorder=2)

                out_file = TempFileManager.mktmp(suffix=".png")
                fig.savefig(out_file, bbox_inches="tight", dpi=300)
                frames.append(Frame(year, out_file))

        return frames

    @contextmanager
    def _figure(self, *args, **kwargs):
        fig = plt.figure(*args, **kwargs)
        try:
            yield fig
        finally:
            plt.close(fig)
            plt.clf()
