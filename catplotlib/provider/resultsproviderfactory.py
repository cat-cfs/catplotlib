from catplotlib.provider.resultsprovider import ResultsProvider
from catplotlib.provider.sqlitegcbmresultsprovider import SqliteGcbmResultsProvider
from catplotlib.provider.duckdbgcbmresultsprovider import DuckDbGcbmResultsProvider

class ResultsProviderFactory:

    def get_results_provider(self, paths, *args, **kwargs) -> ResultsProvider:
        
        if not isinstance(paths, list):
            paths = [paths]

        if all([path.endswith('.db') for path in paths]):
            return SqliteGcbmResultsProvider(paths, *args, **kwargs)
        elif all([path.endswith('.duckdb') for path in paths]):
            return DuckDbGcbmResultsProvider(paths, *args, **kwargs)
        else:
            raise NotImplementedError(f"Ensure all Database path extensions are 'db' for sqlite or 'duckdb' for duckdb: {paths}")


