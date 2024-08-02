import os
import sqlite3
import logging
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

    def __init__(self, paths, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._paths = [paths] if isinstance(paths, str) else paths
        for path in self._paths:
            if not os.path.exists(path):
                raise IOError(f"{path} not found.")

    @property
    def path(self):
        '''See ResultsProvider.path.'''
        return self._paths

    @property
    def simulation_years(self):
        '''See GcbmResultsProvider.simulation_years.'''
        min_year = 9999
        max_year = 0
        for path in self._paths:
            conn = sqlite3.connect(path)
            years = conn.execute("SELECT MIN(year), MAX(year) from v_flux_indicators WHERE year > 0").fetchone()
            min_year = min(years[0], min_year)
            max_year = max(years[1], max_year)

        return min_year, max_year

    @property
    def simulation_area(self):
        '''See ResultsProvider.simulation_area.'''
        area = 0
        for path in self._paths:
            conn = sqlite3.connect(path)
            area += conn.execute(
                """
                SELECT SUM(area) FROM v_age_indicators
                WHERE year = (SELECT MAX(year) FROM v_age_indicators)
                """).fetchone()[0]

        return area

    def has_indicator(self, indicator):
        '''See ResultsProvider.has_indicator'''
        return self.find_indicator_table(indicator)[0] is not None

    def get_annual_result(self, indicator, start_year=None, end_year=None, units=Units.Tc, **kwargs):
        '''See GcbmResultsProvider.get_annual_result.'''
        table, value_col = self.find_indicator_table(indicator)
        if not table:
            return

        per_ha, units_tc, _ = units.value
        area = self.simulation_area if per_ha else 1
        if not start_year or not end_year:
            start_year, end_year = self.simulation_years

        df = pd.DataFrame(columns=["year", indicator])
        for path in self._paths:
            logging.info(f"Reading database results from {path}")
            conn = sqlite3.connect(path)
            df = pd.concat((df, pd.read_sql_query(
                f"""
                SELECT
                    years.year AS year,
                    COALESCE(SUM(i.{value_col}), 0) AS "{indicator}"
                FROM (SELECT DISTINCT year FROM v_age_indicators ORDER BY year) AS years
                LEFT JOIN {table} i
                    ON years.year = i.year
                WHERE i.indicator = '{indicator}'
                    AND years.year > 0
                    AND (years.year BETWEEN {start_year} AND {end_year})
                GROUP BY years.year
                ORDER BY years.year
                """, conn)
            )).groupby("year").sum().reset_index()
        
        df[indicator] *= units_tc / area

        return df

    def find_indicator_table(self, indicator):
        conn = sqlite3.connect(self._paths[0])
        for table, value_col in SqliteGcbmResultsProvider.results_tables.items():
            if conn.execute(f"SELECT 1 FROM {table} WHERE LOWER(indicator) = LOWER(?) LIMIT 1", [indicator]).fetchone():
                return table, value_col

        return None, None
