import os
import shutil
import logging
import sys
from glob import glob
from gcbmanimation.layer.layercollection import LayerCollection
from gcbmanimation.layer.layer import Layer
from gcbmanimation.layer.layer import BlendMode
from gcbmanimation.layer.boundingbox import BoundingBox
from gcbmanimation.color.quantilecolorizer import QuantileColorizer
from gcbmanimation.util.disturbancelayerconfigurer import DisturbanceLayerConfigurer
from gcbmanimation.provider.sqlitegcbmresultsprovider import SqliteGcbmResultsProvider
from gcbmanimation.provider.spatialgcbmresultsprovider import SpatialGcbmResultsProvider
from gcbmanimation.indicator.indicator import Indicator
from gcbmanimation.layer.units import Units
from gcbmanimation.indicator.compositeindicator import CompositeIndicator
from gcbmanimation.animator.legend import Legend
from gcbmanimation.animator.animator import Animator
from gcbmanimation.util.tempfile import TempFileManager
from gcbmanimation.util.utmzones import find_best_projection

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # Test a plain old LayerCollection - bounding box is the first layer found.
    layers = LayerCollection(colorizer=QuantileColorizer())
    bbox = None
    for layer_path in glob(r"C:\Projects\Standalone_Template\processed_output\spatial\NPP*.tiff"):
        year = os.path.splitext(layer_path)[0][-4:]
        layer = Layer(layer_path, year)
        layers.append(layer)
        if not bbox:
            bbox = BoundingBox(layer_path)

    # Render and save the output for viewing.
    indicator_frames, indicator_legend = layers.render(bounding_box=bbox, start_year=2010, end_year=2020)
    for rendered_layer in indicator_frames:
        shutil.copyfile(rendered_layer.path, rf"c:\tmp\indicator_{rendered_layer.year}.png")

    # Test a DisturbanceLayerConfigurer.
    disturbance_configurer = DisturbanceLayerConfigurer()
    disturbance_layers = disturbance_configurer.configure(r"C:\Projects\Standalone_Template\layers\tiled\study_area.json")

    # Render using the bounding box from earlier and save the output for viewing.
    disturbance_frames, disturbance_legend = disturbance_layers.render(bounding_box=bbox, start_year=2010, end_year=2020)
    for rendered_layer in disturbance_frames:
        shutil.copyfile(rendered_layer.path, rf"c:\tmp\disturbance_{rendered_layer.year}.png")

    # Test an Indicator.
    results_db = SqliteGcbmResultsProvider(r"C:\Projects\Standalone_Template\processed_output\compiled_gcbm_output.db")
    indicator = Indicator(
        "NPP", r"C:\Projects\Standalone_Template\processed_output\spatial\NPP*.tiff",
        results_db, {"indicator": "NPP"}, graph_units=Units.Ktc, colorizer=QuantileColorizer(palette="Greens"))

    # Render using the bounding box from earlier and save the output for viewing.
    for frame in indicator.render_map_frames(bounding_box=bbox)[0]:
        shutil.copyfile(frame.path, rf"c:\tmp\{indicator.title}_map_{frame.year}.png")

    for frame in indicator.render_graph_frames():
        shutil.copyfile(frame.path, rf"c:\tmp\{indicator.title}_graph_{frame.year}.png")

    # Test generating a legend.
    legend = Legend({"Indicator": indicator_legend, "Disturbances": disturbance_legend})
    legend_frame = legend.render()
    shutil.copyfile(legend_frame.path, rf"c:\tmp\legend.png")

    # Test animator.
    animator = Animator(disturbance_layers, [indicator], r"c:\tmp")
    animator.render(bbox, 2010, 2020, include_single_views=True)

    # Test a composite indicator.
    composite_indicator = CompositeIndicator(
        "NBP", {
            r"C:\Projects\Standalone_Template\processed_output\spatial\NPP_*.tiff": BlendMode.Add,
            r"C:\Projects\Standalone_Template\processed_output\spatial\Ecosystem_Removals_*.tiff": BlendMode.Subtract
        })

    for frame in composite_indicator.render_map_frames(bounding_box=bbox)[0]:
        shutil.copyfile(frame.path, rf"c:\tmp\{composite_indicator.title}_map_{frame.year}.png")

    for frame in composite_indicator.render_graph_frames():
        shutil.copyfile(frame.path, rf"c:\tmp\{composite_indicator.title}_graph_{frame.year}.png")
    
    # Test cropped area.
    import mojadata.boundingbox as moja
    from mojadata.layer.vectorlayer import VectorLayer
    from mojadata.layer.attribute import Attribute
    from mojadata.layer.filter.valuefilter import ValueFilter

    moja_bbox = moja.BoundingBox(VectorLayer(
        "bbox", r"C:\Projects\Standalone_Template\layers\raw\inventory\inventory.shp",
        Attribute("PolyID", filter=ValueFilter(1))))

    moja_bbox.init()
    cropped_bbox = BoundingBox("bounding_box.tiff", find_best_projection(Layer("bounding_box.tiff", 0)))
    results_provider = SpatialGcbmResultsProvider(r"C:\Projects\Standalone_Template\processed_output\spatial\NPP*.tiff")
    
    indicator = Indicator(
        "NPP", r"C:\Projects\Standalone_Template\processed_output\spatial\NPP*.tiff", results_provider,
        graph_units=Units.Tc, title="NPP Cropped")

    for frame in indicator.render_graph_frames(bounding_box=cropped_bbox):
        shutil.copyfile(frame.path, rf"c:\tmp\{indicator.title}_graph_{frame.year}.png")

    for frame in indicator.render_map_frames(cropped_bbox)[0]:
        shutil.copyfile(frame.path, rf"c:\tmp\{indicator.title}_map_{frame.year}.png")

    cropped_animator = Animator(disturbance_layers, [indicator], r"c:\tmp")
    cropped_animator.render(cropped_bbox)
