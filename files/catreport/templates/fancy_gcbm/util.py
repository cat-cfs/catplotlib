import pandas as pd
import matplotlib.pyplot as plt
import plotly.io as pio   
from report_config import inline_data_tables
from df2img import plot_dataframe
from itertools import islice
from contextlib import contextmanager
from sqlalchemy import create_engine
pio.kaleido.scope.mathjax = None

def display_or_dump(df, name, index=True, decimals=2):
    pd.set_option("display.precision", decimals)
    if inline_data_tables:
        print(name)
        plot_dataframe(df.round(decimals), print_index=index, plotly_renderer="pdf",
            fig_size=(max(200, 6 * len(" ".join(df.columns))), 26 * df.shape[0]))
    else:
        filename = f"{name}.csv"
        df.round(decimals).to_csv(filename, index=index)
        print(f"Data: {filename}")

def chunk(it, size):
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())

_fig_num = 1
def add_figure_id(page_num, ax=None):
    global _fig_num
    plt.tight_layout()
    if ax:
        ax.text(0, -0.1, f"figure {page_num}.{_fig_num}", transform=ax.transAxes)
    else:
        plt.figtext(0, 0, f"figure {page_num}.{_fig_num}")
    
    _fig_num += 1
