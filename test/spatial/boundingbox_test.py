import unittest
import os 
import shutil
from catplotlib.spatial.layer import Layer, BlendMode
from catplotlib.spatial.layercollection import LayerCollection
from catplotlib.spatial.boundingbox import BoundingBox
import rasterio
import numpy.testing

class BoundingBoxTest(unittest.TestCase):
    
    def _get_array(self, tiff_path):
        with rasterio.open(tiff_path) as src:
            return src.read(1)
    
    def test_crop_single(self):
        bounding_box = BoundingBox('test/example_output/layers/tiled/bounding_box.tiff', crop_to_data=False)
        crop_layer = Layer('test/example_output/layers/tiled/Classifier1_moja.tiff')
        
        bounding_box_array = self._get_array(bounding_box.path)
                
        original = self._get_array(crop_layer.path)
        
        cropped_layer = bounding_box.crop(crop_layer)
        
        actual_output = self._get_array(cropped_layer.path)
        
        self.assertNotEqual(bounding_box_array.shape, original.shape)
        self.assertEqual(bounding_box_array.shape, actual_output.shape)
        
    def test_crop_multi(self):
        bounding_box = BoundingBox('test/example_output/layers/tiled/bounding_box.tiff', crop_to_data=False)
        layers = []
        layers.append(Layer('test/example_output/layers/tiled/Classifier1_moja.tiff'))
        layers.append(Layer('test/example_output/layers/tiled/Classifier2_moja.tiff'))
        
        layer_collection = LayerCollection(layers)
        
        bounding_box_array = self._get_array(bounding_box.path)
        
        cropped_layer_collection: LayerCollection = bounding_box.crop(layer_collection)
        
        for cropped_layer, actual_layer in zip(cropped_layer_collection._layers, layers):
            original_array = self._get_array(actual_layer.path)
            actual_output = self._get_array(cropped_layer.path)
            
            self.assertNotEqual(bounding_box_array.shape, original_array.shape)
            self.assertEqual(bounding_box_array.shape, actual_output.shape)
        