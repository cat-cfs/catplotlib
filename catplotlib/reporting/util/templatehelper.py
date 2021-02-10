from textwrap import wrap
from IPython.display import display
from IPython.display import Markdown
from catplotlib.reporting.provider.stylingresultsprovider import StylingResultsProvider
from catplotlib.reporting.style.stylemanager import StyleManager
from catplotlib.reporting.style.dashes import Dash
from catplotlib.reporting.style.dashes import Dashes

def wrap_string(s, n=60, spacer="&#8203;"):
    return spacer.join(wrap(s, n))

def create_providers(paths, style_manager=None, rotate_linestyles=True):
    all_dashes = Dashes([d for d in Dash])
    providers = []
    for label, path in paths.items():
        results_style_manager = style_manager or (
            StyleManager() if not rotate_linestyles
            else StyleManager(dashes=Dashes([all_dashes.next()])))

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
