from catplotlib.provider.units import Units

class ResultsProvider:
    '''
    Base class for retrieving non-spatial GCBM results. Subclass to support different
    database types, i.e. SQLite.
    '''
    
    def __init__(self, name=None, *args, **kwargs):
        self._name = name or "Simulation results"
    
    @property
    def name(self):
        '''The datasource name.'''
        return self._name

    @property
    def path(self):
        '''The datasource path (or connection details, file pattern, etc.)'''
        raise NotImplementedError()

    @property
    def simulation_years(self):
        '''The start and end year of the simulation.'''
        raise NotImplementedError()

    @property
    def simulation_area(self):
        '''The simulated area, in hectares.'''
        raise NotImplementedError()

    def has_indicator(self, indicator):
        '''Check if this provider has the specified indicator.'''
        raise NotImplementedError()

    def get_annual_result(self, indicator, start_year=None, end_year=None, units=Units.Tc, **kwargs):
        '''
        Gets an ordered collection of annual results for a particular indicator,
        optionally dividing the values by the specified units.

        Arguments:
        'indicator' -- the indicator to retrieve.
        'start_year' -- use along with end_year to limit the time period of the results.
        'end_year' -- use along with start_year to limit the time period of the results.
        'units' -- optional units to convert the result values to.

        Additional arguments vary by subclass.

        Returns a dataframe of simulation year and indicator value(s) along with styling
        information.
        '''
        raise NotImplementedError()
