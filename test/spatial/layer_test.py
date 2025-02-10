import unittest
import os 
import shutil
from catplotlib.spatial.layer import Layer, BlendMode
from catplotlib.provider.units import Units
import rasterio
import numpy.testing

class LayerTest(unittest.TestCase):
    
    def get_array(self, tiff_path):
        with rasterio.open(tiff_path) as src:
            return src.read(1)
    
    def test_convert_units_pass(self):
        input = "test/example_output/processed_output/spatial/AG_Biomass_C_tc_per_ha_2010.tif"
        expected_output = "test/example_output/processed_output/spatial/AG_Biomass_C_absolute_2010.tif"
        
        assert(os.path.exists(input))
        converted_layer = Layer(input, units=Units.TcPerHa).convert_units(Units.Tc)
        
        actual_array = self.get_array(converted_layer.path)
        
        assert(os.path.exists(expected_output))
        expected_array = self.get_array(expected_output)
            
        numpy.testing.assert_almost_equal(actual_array, expected_array, 6)
    
    def test_convert_units_invert(self):
        input = "test/example_output/processed_output/spatial/AG_Biomass_C_tc_per_ha_2010.tif"
        
        assert(os.path.exists(input))
        converted_layer = Layer(input, units=Units.TcPerHa).convert_units(Units.Tc).convert_units(Units.TcPerHa)
        
        actual_array = self.get_array(converted_layer.path)
        
        assert(os.path.exists(input))
        
        expected_array = self.get_array(input)

        numpy.testing.assert_almost_equal(actual_array, expected_array, 5)
        
    
    def test_convert_units_fail(self):
        input = "test/example_output/processed_output/spatial/AG_Biomass_C_tc_per_ha_2010.tif"
        
        assert(os.path.exists(input))
        converted_layer = Layer(input, units=Units.TcPerHa).convert_units(Units.Tc)
        
        actual_array = self.get_array(converted_layer.path)
        
        assert(os.path.exists(input))
        
        expected_array = self.get_array(input)

            
        try:
            numpy.testing.assert_almost_equal(actual_array, expected_array, 6)
        except AssertionError as e:
            return
        except Exception as e:
            self.fail() 
            
    def test_blend_pass(self):
        input = "test/example_output/processed_output/spatial/AG_Biomass_C_tc_per_ha_2010.tif"
        blend_input = [
            Layer('test/example_output/processed_output/spatial/AG_Biomass_C_absolute_2011.tif'),
            BlendMode.Add,
            Layer('test/example_output/processed_output/spatial/AG_Biomass_C_absolute_2012.tif'),
            BlendMode.Subtract,
            Layer('test/example_output/processed_output/spatial/AG_Biomass_C_absolute_2013.tif'),
            BlendMode.Add,
            Layer('test/example_output/processed_output/spatial/AG_Biomass_C_absolute_2014.tif'),
            BlendMode.Add
        ]
        
        blended_layer = Layer(input, units=Units.TcPerHa).blend(*blend_input)

        actual = self.get_array(blended_layer.path)
        expected = self.get_array(r'test\example_output\blend\2010_2014.tif')
        
        shutil.copy(blended_layer.path, 'test.tif')
        
        numpy.testing.assert_almost_equal(actual, expected, 4)