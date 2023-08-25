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
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "NPP", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Rh", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "NEP", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "NEP", "NPP", "Rh", units=Units.TcPerHa)
```

```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Total Litterfall", units=Units.TcPerHa)
```

## Stocks
```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Aboveground Biomass", units=Units.TcPerHa)
```
