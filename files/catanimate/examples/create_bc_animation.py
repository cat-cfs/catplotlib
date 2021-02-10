import mojadata.boundingbox as moja
from mojadata.cleanup import cleanup
from mojadata.layer.vectorlayer import VectorLayer
from mojadata.layer.attribute import Attribute
from mojadata.layer.filter.valuefilter import ValueFilter
from gcbmanimation.color.quantilecolorizer import QuantileColorizer
from gcbmanimation.color.customcolorizer import CustomColorizer
from gcbmanimation.layer.layer import Layer
from gcbmanimation.layer.layer import BlendMode
from gcbmanimation.layer.boundingbox import BoundingBox
from gcbmanimation.util.disturbancelayerconfigurer import DisturbanceLayerConfigurer
from gcbmanimation.provider.spatialgcbmresultsprovider import SpatialGcbmResultsProvider
from gcbmanimation.indicator.indicator import Indicator
from gcbmanimation.indicator.compositeindicator import CompositeIndicator
from gcbmanimation.indicator.indicator import Units
from gcbmanimation.animator.animator import Animator
from gcbmanimation.util.utmzones import find_best_projection
from gcbmanimation.util.tempfile import TempFileManager
from dbfread import DBF

if __name__ == "__main__":
    TempFileManager.delete_on_exit()
    draw = "draw001"
    scenario = "base"

    layer_root = r"O:\GCBM\21_BC_wildfires\uncertainty_analysis\05_working\00_tile\layers\tiled"
    output_root = r"O:\GCBM\21_BC_wildfires\uncertainty_analysis\05_working\02_gcbm_outputs"
    scenario_output = rf"{output_root}\bc_fire_uncertainty_harvest_base_fire_high_{draw}_{scenario}\output"

    # Gather up all the tiled disturbance layers into a single collection.
    scanner = DisturbanceLayerConfigurer(CustomColorizer({
        ("Wild Fires", "Future wild fire, no access", "Future wild fire, accessible"): "Reds_d",
        (
            "Clearcut harvest with slash pile burning",
            "Future salvage harvest, Douglas-fir",
            "Future salvage harvest, non-Douglas-fir",
            "Base CC"
        ): "Blues_d",
        (
            "Mountain Pine Beetle - Low Impact",
            "Mountain Pine Beetle - Severe Impact",
            "Mountain Pine Beetle - Moderate Impact",
            "Mountain Pine Beetle - Very Severe Impact"
        ): "Purples_d"
    }), background_color=(240, 240, 240))

    disturbances = scanner.configure(rf"{layer_root}\base\study_area.json")
    disturbances.merge(scanner.configure(rf"{layer_root}\fire_2019\BASE\study_area.json"))
    disturbances.merge(scanner.configure(rf"{layer_root}\future_harvest\BASE\study_area.json"))
    disturbances.merge(scanner.configure(rf"{layer_root}\future_fire_salvage\high\{draw}\study_area.json"))
    if scenario == "miti":
        disturbances.merge(scanner.configure(rf"{layer_root}\future_fire_salvage\high\{draw}\salvage\study_area.json"))

    tsa_attributes = DBF(rf"{layer_root}\..\raw\base\reference\tsa_bc.dbf")
    tsa_names = (row["pspuName"] for row in tsa_attributes)
    for tsa in tsa_names:
        print(f"Processing TSA: {tsa}")
        moja_bbox = moja.BoundingBox(
            VectorLayer(
                "bbox",
                rf"{layer_root}\..\raw\base\reference\tsa_bc.shp",
                Attribute("pspuName", filter=ValueFilter(tsa))),
            pixel_size=0.001)

        # Set up the bounding box: we want it to be the TSA boundary cropped down to only the simulated
        # pixels (non-nodata) in age_1990.tif.
        with cleanup():
            moja_bbox.init()
            
        tsa_bounding_box = BoundingBox("bounding_box.tiff")
        cropped_simulation_area = tsa_bounding_box.crop(BoundingBox(rf"{scenario_output}\age_1990.tif"))
        bounding_box = BoundingBox(cropped_simulation_area.path, find_best_projection(cropped_simulation_area))

        indicators = [
            Indicator("Total Merch", (rf"{scenario_output}\Total_Merch_*.tif", Units.Tc),
                      SpatialGcbmResultsProvider((rf"{scenario_output}\Total_Merch_*.tif", Units.Tc)),
                      graph_units=Units.Mtc, map_units=Units.TcPerHa, title=f"NPP in {tsa}",
                      colorizer=QuantileColorizer(palette="GnBu")),
            # Indicator("NPP", rf"{scenario_output}\ha_NPP_*.tif",
                      # SpatialGcbmResultsProvider(rf"{scenario_output}\ha_NPP_*.tif"),
                      # graph_units=Units.MtcFlux, map_units=Units.TcPerHaFlux, title=f"NPP in {tsa}",
                      # colorizer=QuantileColorizer(palette="GnBu")),
            # Indicator("Aboveground Biomass", (rf"{scenario_output}\abs_AG_Biomass_C_*.tif", Units.Tc),
                      # SpatialGcbmResultsProvider((rf"{scenario_output}\abs_AG_Biomass_C_*.tif", Units.Tc)),
                      # graph_units=Units.Mtc, map_units=Units.TcPerHa,
                      # title=f"Aboveground Biomass in {tsa}",
                      # colorizer=QuantileColorizer(palette="GnBu")),
            # CompositeIndicator(
                # "NBP", {
                    # rf"{scenario_output}\ha_NPP_*.tif"                         : BlendMode.Add,
                    # rf"{scenario_output}\ha_Disturbance_Emissions_CO_*.tif"    : BlendMode.Subtract,
                    # rf"{scenario_output}\ha_Disturbance_Emissions_CO2_*.tif"   : BlendMode.Subtract,
                    # rf"{scenario_output}\ha_Disturbance_Emissions_CH4_*.tif"   : BlendMode.Subtract,
                    # rf"{scenario_output}\ha_Rh_*.tif"                          : BlendMode.Subtract,
                    # (rf"{scenario_output}\abs_All_to_Products_*.tif", Units.Tc): BlendMode.Subtract,
                # },
                # graph_units=Units.MtcFlux, map_units=Units.TcPerHaFlux,
                # colorizer=QuantileColorizer(palette="Blues", negative_palette=["#FFDEAD", "#F4A460", "#D2691E"]),
                # title=f"NBP in {tsa}"),
        ]

        animator = Animator(disturbances, indicators, rf"c:\tmp\{tsa}")
        animator.render(bounding_box, fps=1)
