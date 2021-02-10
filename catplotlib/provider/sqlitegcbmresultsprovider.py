import os
import sqlite3
import pandas as pd
from collections import OrderedDict
from catplotlib.provider.resultsprovider import ResultsProvider
from catplotlib.provider.units import Units

class SqliteGcbmResultsProvider(ResultsProvider):
    '''
    Retrieves non-spatial annual results from a SQLite GCBM results database.

    Arguments:
    'path' -- path to SQLite GCBM results database.
    '''

    results_tables = {
        "v_flux_indicator_aggregates": "flux_tc",
        "v_flux_indicators"          : "flux_tc",
        "v_pool_indicators"          : "pool_tc",
        "v_stock_change_indicators"  : "flux_tc",
    }

    def __init__(self, path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not os.path.exists(path):
            raise IOError(f"{path} not found.")

        self._path = path

    @property
    def path(self):
        '''See ResultsProvider.path.'''
        return self._path

    @property
    def simulation_years(self):
        '''See GcbmResultsProvider.simulation_years.'''
        conn = sqlite3.connect(self._path)
        years = conn.execute("SELECT MIN(year), MAX(year) from v_age_indicators").fetchone()

        return years

    @property
    def simulation_area(self):
        '''See ResultsProvider.simulation_area.'''
        conn = sqlite3.connect(self._path)
        area = conn.execute(
            """
            SELECT SUM(area) FROM v_age_indicators
            WHERE year = (SELECT MIN(year) FROM v_age_indicators)
            """).fetchone()[0]

        return area

    def get_annual_result(self, indicator, start_year=None, end_year=None, units=Units.Tc, **kwargs):
        '''See GcbmResultsProvider.get_annual_result.'''
        table, value_col = self._find_indicator_table(indicator)
        per_ha, units_tc, _ = units.value
        area = self.simulation_area if per_ha else 1
        if not start_year or not end_year:
            start_year, end_year = self.simulation_years

        conn = sqlite3.connect(self._path)
        df = pd.read_sql_query(
            f"""
            SELECT
                years.year AS year,
                COALESCE(SUM(i.{value_col}), 0) / {units_tc} / {area} AS "{indicator}"
            FROM (SELECT DISTINCT year FROM v_age_indicators ORDER BY year) AS years
            LEFT JOIN {table} i
                ON years.year = i.year
            WHERE i.indicator = '{indicator}'
                AND (years.year BETWEEN {start_year} AND {end_year})
            GROUP BY years.year
            ORDER BY years.year
            """, conn)

        return df

    def _find_indicator_table(self, indicator):
        conn = sqlite3.connect(self._path)
        for table, value_col in SqliteGcbmResultsProvider.results_tables.items():
            if conn.execute(f"SELECT 1 FROM {table} WHERE indicator = ?", [indicator]).fetchone():
                return table, value_col

        return None, None
