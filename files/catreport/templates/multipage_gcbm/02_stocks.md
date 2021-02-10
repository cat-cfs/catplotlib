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
from catplotlib.reporting.plot.basic import *
from catplotlib.provider.units import Units
%store -r providers
```

# Stocks

## Aboveground Biomass
```{code-cell} ipython3
:tags: ["remove-input", "full-width"]
basic_results_graph(providers, "Aboveground Biomass", units=Units.TcPerHa)
```
