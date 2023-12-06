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
from datetime import datetime
from myst_nb import glue
from catplotlib.reporting.util.templatehelper import *
from catplotlib.reporting.plot.basic import *
from catplotlib.spatial.display.raster import show_raster_location

%providers
providers = create_providers(provider_paths)
%store providers
%store provider_paths
```

# GCBM Results
```{code-cell} ipython3
:tags: ["remove-input"]
simulation_metadata(providers)
```

## Disturbances
```{code-cell} ipython3
:tags: ["remove-input", "full-width"]

for title, path in provider_paths.items():
    print(title)
    with connect(path) as gcbm_results_db:
        display(pd.read_sql_query(
            """
            SELECT DISTINCT disturbance_type AS "Disturbance Type", disturbance_code AS "Disturbance Code"
            FROM v_total_disturbed_areas
            GROUP BY disturbance_type, disturbance_code
            ORDER BY disturbance_code
            """, gcbm_results_db
        ))
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
%matplotlib inline

for title, path in provider_paths.items():
    print(title)
    with connect(path) as gcbm_results_db:
        fig, ax = plt.subplots(figsize=(13, 10))

        pools = pd.read_sql_query(
            """
            SELECT indicator, year, SUM(pool_tc) / 1e6 AS pool_mtc
            FROM v_pool_indicators
            WHERE year > 0
            GROUP BY indicator, year
            ORDER BY indicator, year
            """, gcbm_results_db
        ).pivot(index="year", columns="indicator", values="pool_mtc")

        pools.plot(title="Carbon stocks", xlabel="Year", ylabel="Mt C", ax=ax, style=[
            "-", ":", "--", "-.", "+", "^", ".", "o", "v"
        ])

        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
                  
        add_figure_id("01")
        plt.show()
        display_or_dump(
            pools.rename({
                "Merch/Other": "Merch / Other"
            }, axis=1).add_suffix(" (M tC)"),
            f"01_{title}_c_stocks", decimals=0
        )
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
%matplotlib inline

for title, path in provider_paths.items():
    print(title)
    with connect(path) as gcbm_results_db:
        fluxes = pd.read_sql_query(
            """
            SELECT indicator, year, SUM(flux_tc) / 1e6 AS flux_mtc
            FROM v_stock_change_indicators
            WHERE year > 0
                AND indicator IN ('NPP', 'Rh', 'NBP', 'NEP')
            GROUP BY indicator, year
            ORDER BY indicator, year
            """, gcbm_results_db
        ).pivot(index="year", columns="indicator", values="flux_mtc")

        fluxes.plot(
            title="Carbon fluxes", xlabel="Year", ylabel="Mt C",
            style=["-", "--", "-.", ":"]
        )

        add_figure_id("01")
        plt.show()
        display_or_dump(fluxes.add_suffix(" (M tC)"), f"01_{title}_c_fluxes", decimals=0)
```

## Fluxes
```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "NPP", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "NEP", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Rh", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "NBP", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "NEP", "NPP", "Rh", "NBP", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "All Production", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "CH4Production", units=Units.TcPerHa)
```

## Stocks
```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Total Biomass", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Aboveground Biomass", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Merch/Other", units=Units.TcPerHa)
```

### DOM
```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Deadwood", "Litter", "Soil Carbon", units=Units.TcPerHa)
```
