import matplotlib.pyplot as plt
from catplotlib.reporting.style.symbols import Symbol
from catplotlib.reporting.style.dashes import Dash
from catplotlib.reporting.style.dashes import Dashes
from catplotlib.provider.units import Units

def plot_annual_indicators(fig, ax, provider, *indicators, legend_suffix="", units=None,
                           start_year=None, end_year=None):
    all_data = None
    styles = {}
    for indicator in indicators:
        indicator_data, indicator_styles = provider.get_annual_result(
            indicator, start_year=start_year, end_year=end_year, units=units)

        styles.update(indicator_styles)
        if all_data is None:
            all_data = indicator_data
        else:
            all_data = all_data.merge(indicator_data, on="year", how="outer")

    cols = [col for col in all_data.columns if col != "year"]
    x_values = all_data["year"]
    for col in cols:
        color = styles[col]["color"]
        marker = Symbol.as_matplotlib(styles[col]["symbol"])
        linestyle = Dash.as_matplotlib(styles[col]["dash"])
        ax.plot(x_values, all_data[col], label=f"{col}{legend_suffix}",
                color=color, marker=marker, linestyle=linestyle)

    fig.legend(bbox_to_anchor=(1, 1), loc="upper left")
    fig.tight_layout()

def basic_results_graph(providers, *indicators, quiet=True, units=Units.Tc,
                        start_year=None, end_year=None):
    fig, ax = plt.subplots()
    single_provider = not isinstance(providers, list) or len(providers) == 1
    if single_provider:
        provider = providers[0] if isinstance(providers, list) else providers
        plot_annual_indicators(fig, ax, provider, *indicators, units=units)
    else:
        for provider in providers:
            plot_annual_indicators(fig, ax, provider, *indicators, legend_suffix=f" ({provider.name})",
                                   units=units, start_year=start_year, end_year=end_year)
    
    ax.set_xlabel("Year")
    ax.set_ylabel(units.value[2])

    if not quiet:
        return fig

def basic_combo_graph(bar_provider, bar_indicator, line_providers, line_indicators,
                      quiet=True, bar_units=Units.Tc, line_units=Units.Blank):
    fig, ax = plt.subplots()
    for provider in line_providers:
        plot_annual_indicators(fig, ax, provider, *line_indicators,
                               legend_suffix=f" ({provider.name})",
                               units=line_units)
    
    ax.set_xlabel("Year")
    ax.set_ylabel(units.value[2])

    indicator_data, _ = bar_provider.get_annual_result(bar_indicator, units=units)
    ax.bar(indicator_data["year"], indicator_data[bar_indicator], label=bar_indicator)

    if not quiet:
        return fig
