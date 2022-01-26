from textwrap import wrap
from IPython.display import display
from IPython.display import Markdown
from plotly.express.colors import qualitative as plotly_colors
from catplotlib.reporting.provider.stylingresultsprovider import StylingResultsProvider
from catplotlib.reporting.style.stylemanager import StyleManager
from catplotlib.reporting.style.dashes import Dashes
from catplotlib.reporting.style.palette import Palette
from catplotlib.reporting.style.symbols import Symbols

def wrap_string(s, n=60, spacer="&#8203;"):
    return spacer.join(wrap(s, n))

def create_providers(paths, rotate_linestyles=True, rotate_colors=True, rotate_symbols=True, palette=None):
    static_dashes = Dashes()
    static_colors = palette or Palette(plotly_colors.Plotly)
    static_symbols = Symbols()

    providers = []
    for label, path in paths.items():
        static_dash = Dashes([static_dashes.next()]) if not rotate_linestyles else None
        static_color = Palette([static_colors.next()]) if not rotate_colors else static_colors.copy()
        static_symbol = Symbols([static_symbols.next()]) if not rotate_symbols else None
        results_style_manager = StyleManager(static_color, static_symbol, static_dash)
        providers.append(StylingResultsProvider(path, style_manager=results_style_manager, name=label))

    return providers

def simulation_metadata(providers):
    align = "style='text-align:left;'"
    db_table = f"<table><tr><th {align}>Project</th><th {align}>Path</th></tr>"
    for i, provider in enumerate(providers):
        if i == 0:
            start_year, end_year = provider.simulation_years
            display(Markdown(
                f"""<table
                    ><tr><th {align}>Start year</th><th {align}>End year</th><th {align}>Area</th
                    ><tr><td {align}>{start_year}</td><td {align}>{end_year}</td
                    ><td {align}>{round(provider.simulation_area)} ha</td></tr
                    ></table>"""))

        db_table += f"<tr><td {align}'>{provider.name}</td>" \
            + f"<td style='word-break:break-all;text-align:left;'>{provider.path}</td></tr>"

    db_table += "</table>"
    display(Markdown(db_table))
