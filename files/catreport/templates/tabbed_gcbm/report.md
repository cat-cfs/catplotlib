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
import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)

from myst_nb import glue
from catplotlib.reporting.util.templatehelper import *
from catplotlib.reporting.plot.basic import *
from catplotlib.spatial.display.raster import show_raster_location
from catplotlib.provider.units import Units

%matplotlib inline

bounding_box_path = r"..\..\layers\tiled\bounding_box.tif"

%providers

providers = create_providers(provider_paths)
```

# GCBM Results
```{code-cell} ipython3
:tags: ["remove-input"]
simulation_metadata(providers)
show_raster_location(bounding_box_path)
```

## Fluxes

```{code-cell} ipython3
:tags: ["remove-cell"]
glue("npp", basic_results_graph(providers, "NPP", units=Units.TcPerHa, display=False), display=False)
glue("rh", basic_results_graph(providers, "Rh", units=Units.TcPerHa, display=False), display=False)
glue("nep", basic_results_graph(providers, "NEP", units=Units.TcPerHa, display=False), display=False)
glue("nep_npp_rh", basic_results_graph(providers, "NEP", "NPP", "Rh", units=Units.TcPerHa, display=False), display=False)
glue("litterfall", basic_results_graph(providers, "Total Litterfall", units=Units.TcPerHa, display=False), display=False)
```

````{tabbed} NPP
```{glue:} npp
```
````

````{tabbed} Rh
```{glue:} rh
```
````

````{tabbed} NEP
```{glue:} nep
```
````

````{tabbed} All
```{glue:} nep_npp_rh
```
````

````{tabbed} Litterfall
```{glue:} litterfall
```
````

## Stocks

```{code-cell} ipython3
:tags: ["remove-cell"]
glue("ag_bio", basic_results_graph(providers, "Aboveground Biomass", units=Units.TcPerHa, display=False), display=False)
```

````{tabbed} Aboveground Biomass
```{glue:} ag_bio
```
````
