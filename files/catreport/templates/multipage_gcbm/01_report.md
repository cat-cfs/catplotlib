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

bounding_box_path = r"..\..\layers\tiled\bounding_box.tif"

%providers

providers = create_providers(provider_paths)
%store providers
```

# Results Details
```{code-cell} ipython3
:tags: ["remove-input"]
simulation_metadata(providers)
show_raster_location(bounding_box_path)
```
