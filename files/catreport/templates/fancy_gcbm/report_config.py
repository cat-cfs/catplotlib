import pandas as pd
import matplotlib as mpl
import warnings

warnings.filterwarnings("ignore")
mpl.rcParams["figure.dpi"] = 300

# True = include data tables in PDF; False = write data tables for graphs to
# csv files and include filenames in PDF.
inline_data_tables = False

wildfire_dist_codes = [1]
harvest_dist_codes = [4, 195, 196]

n2o_fraction = 0.00017
n2o_gwp = 298.0
n2o_multiplier = n2o_fraction * n2o_gwp
co2e_multiplier = 44.0 / 12.0
ch4_multiplier = 16.0 / 12.0 * 25.0
