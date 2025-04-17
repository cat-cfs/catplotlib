import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from catplotlib.provider.resultsproviderfactory import ResultsProviderFactory
from catplotlib.provider.sqlitegcbmresultsprovider import SqliteGcbmResultsProvider
from catplotlib.provider.duckdbgcbmresultsprovider import DuckDbGcbmResultsProvider

class ResultsProviderFactoryTest(unittest.TestCase):

    def test_non_list_input(self):
        with TemporaryDirectory() as temp_dir:
            db = Path(temp_dir, 'test.db')
            db.touch()
            provider = ResultsProviderFactory().get_results_provider(str(db))
            assert isinstance(provider, SqliteGcbmResultsProvider)
    
    def test_sqlite(self):
        with TemporaryDirectory() as temp_dir:
            db = Path(temp_dir, 'test.db')
            db.touch()
            provider = ResultsProviderFactory().get_results_provider([str(db)])
            assert isinstance(provider, SqliteGcbmResultsProvider)

    def test_duckdb(self):
        with TemporaryDirectory() as temp_dir:
            db = Path(temp_dir, 'test.duckdb')
            db.touch()
            provider = ResultsProviderFactory().get_results_provider([str(db)])
            assert isinstance(provider, DuckDbGcbmResultsProvider)
            assert not isinstance(provider, SqliteGcbmResultsProvider)

    def test_mismatch(self):
       with TemporaryDirectory() as temp_dir:
            db_sqlite = Path(temp_dir, 'test.db')
            db_duckdb = Path(temp_dir, 'test.duckdb')
            db_sqlite.touch()
            db_duckdb.touch()
            try:
                provider = ResultsProviderFactory().get_results_provider([str(db_sqlite), str(db_duckdb)])
            except Exception as e:
                assert isinstance(e, NotImplementedError) 

    
        