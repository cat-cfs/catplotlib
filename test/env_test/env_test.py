import unittest
import catplotlib
import os 

class EnvTest(unittest.TestCase):
    
    def test_env(self):
        self.assertEqual(os.path.abspath(os.path.join(os.getcwd(), 'catplotlib')), os.path.abspath(os.path.dirname(catplotlib.__file__)))

        
        