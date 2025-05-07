from catplotlib.provider.resultsprovider import ResultsProvider
from catplotlib.provider.resultsproviderfactory import ResultsProviderFactory
from catplotlib.provider.units import Units
from catplotlib.reporting.style.stylemanager import StyleManager

class StylingResultsProvider(ResultsProvider):
    '''
    Retrieves annual results and applies styling information to them.

    Arguments:
    'path' -- path to SQLite GCBM results database.
    'provider' -- another provider type, as an alternative to providing a path.
    '''

    def __init__(self, path=None, provider=None, style_manager=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (path or provider):
            raise RuntimeError("Must provide either a path or provider.")

        self._style_manager = style_manager or StyleManager()

        if not provider:
            provider = ResultsProviderFactory().get_results_provider(path, *args, **kwargs)

        self._provider = provider

    @property
    def path(self):
        '''See ResultsProvider.path.'''
        return self._provider.path

    @property
    def simulation_years(self):
        '''See ResultsProvider.simulation_years.'''
        return self._provider.simulation_years

    @property
    def simulation_area(self):
        '''See ResultsProvider.simulation_area.'''
        return self._provider.simulation_area

    def get_annual_result(self, indicator, start_year=None, end_year=None, units=Units.Tc, **kwargs):
        '''See ResultsProvider.get_annual_result.'''
        results = self._provider.get_annual_result(indicator, start_year, end_year, units, **kwargs)
        return results, self._style_manager.style(results)
