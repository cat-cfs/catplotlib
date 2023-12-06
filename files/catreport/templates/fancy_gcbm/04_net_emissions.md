---
jupytext:
  formats: md:myst
  text_representation:
    extension: .md
    format_name: myst
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

```{code-cell} ipython3
:tags: ["remove-cell"]

from report_config import *
from util import *

%store -r providers
%store -r provider_paths
```

### Net emissions

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
%matplotlib inline

def format_axes(*axes):
    for ax in axes:
        min_x, max_x = ax.get_xlim()
        label_x = min_x + (max_x - min_x) / 2

        min_y = min((min(l.get_ydata()) for l in ax.lines))
        max_y = max((max(l.get_ydata()) for l in ax.lines))
        y_buffer = (max_y - min_y) * 0.1
        ax.set_ylim((min_y - y_buffer, max_y + y_buffer))

        bbox = {"ec": "black", "fc": "lightgray", "alpha": 0.5}

        if min_y < 0:
            ax.text(0.5, 0.03, "sink", ha="center", va="bottom", bbox=bbox, transform=ax.transAxes)
            
        if max_y > 0:
            ax.text(0.5, 0.97, "source", ha="center", va="top", bbox=bbox, transform=ax.transAxes)

        ax.axhline(y=0, color="red", lw=2, linestyle="dashed")
        ax.legend(loc="upper left")

gcbm_net_emissions_sql = (
    f"""
    SELECT
        stock.year,
        (((COALESCE(stock.nep_tc, 0) - COALESCE(flux.co2_tc, 0) - COALESCE(flux.co_tc, 0)) * -{co2e_multiplier})
            + COALESCE(flux.ch4_tc, 0) * {ch4_multiplier}
            + COALESCE(flux.n2o_tc, 0) * {co2e_multiplier} * {n2o_gwp}
        ) / 1e6 AS net_emissions_mtco2e
    FROM (
        SELECT year, SUM(flux_tc) AS nep_tc
        FROM v_stock_change_indicators
        WHERE indicator = 'NEP'
        GROUP BY year
    ) AS stock
    LEFT JOIN (
        SELECT
            year,
            SUM(co_tc) AS co_tc,
            SUM(co2_tc) AS co2_tc,
            SUM(ch4_tc) AS ch4_tc,
            SUM(CASE WHEN ch4_tc = 0 THEN 0 ELSE co2_tc * {n2o_fraction} END) AS n2o_tc
        FROM (
            SELECT
                year,
                disturbance_type,
                SUM(CASE WHEN indicator = 'COProduction' THEN flux_tc ELSE 0 END) AS co_tc,
                SUM(CASE WHEN indicator = 'CO2Production' THEN flux_tc ELSE 0 END) AS co2_tc,
                SUM(CASE WHEN indicator = 'CH4Production' THEN flux_tc ELSE 0 END) AS ch4_tc
            FROM v_flux_indicators
            WHERE indicator IN ('NEP', 'COProduction', 'CO2Production', 'CH4Production')
            GROUP BY
                year,
                disturbance_type
        )
        GROUP BY year
    ) AS flux
        ON stock.year = flux.year
    """
)

markers = [".", "o", ""]

ax_carbon = None
ax_cumulative = None
data_table = pd.DataFrame({"year": []}).set_index("year")
for i, (title, path) in enumerate(provider_paths.items()):
    with connect(path) as gcbm_results_db:
        net_emissions = pd.read_sql_query(gcbm_net_emissions_sql, gcbm_results_db)

    marker = markers[i % len(markers)]

    df_carbon = (
        net_emissions[["year", "net_emissions_mtco2e"]]
        .set_index("year")
        .fillna(0)
    )
    
    ax_carbon = df_carbon.rename(columns={"net_emissions_mtco2e": title}).plot(
        title=f"Net emissions excluding HWP",
        xlabel="Year", ylabel="Mt CO2e / yr", ax=ax_carbon, marker=marker
    )

    df_cumulative = (
        net_emissions[["year", "net_emissions_mtco2e"]]
        .set_index("year")
        .fillna(0)
        .cumsum()
    )
    
    ax_cumulative = df_cumulative.rename(columns={"net_emissions_mtco2e": title}).plot(
        title=f"Cumulative net emissions excluding HWP",
        xlabel="Year", ylabel="Mt CO2e", ax=ax_cumulative, marker=marker
    )

    for (df, column, name) in (
        (df_carbon, "net_emissions_mtco2e", f"{title} Net Emissions (Mt CO2e)"),
        (df_cumulative, "net_emissions_mtco2e", f"{title} Cumulative Net Emissions (Mt CO2e)")
    ):
        data_table = data_table.join(df[[column]].rename(columns={column: name}), how="outer")

format_axes(ax_carbon, ax_cumulative)

add_figure_id("04", ax_carbon)
add_figure_id("04", ax_cumulative)
plt.show()

display_or_dump(data_table.rename_axis("Year"), f"04_net_emissions")
```
