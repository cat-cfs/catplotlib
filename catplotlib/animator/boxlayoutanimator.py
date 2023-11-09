import os
import imageio
import logging
import shutil
from catplotlib.util import localization
from catplotlib.animator.layout.boxlayout import BoxLayout
from catplotlib.animator.legend import Legend
from catplotlib.util.tempfile import TempFileManager

class BoxLayoutAnimator:
    '''
    Creates animations from GCBM results. Takes a collection of disturbance layers
    and one or more indicators and produces a WMV for each indicator showing the
    timeseries of disturbances, spatial output, and graphed database output.

    Arguments:
    'disturbances' -- a LayerCollection of the input disturbance layers for the
        GCBM simulation.
    'indicators' -- a list of Indicator objects grouping a set of GCBM spatial
        outputs and a related ecosystem indicator from the GCBM results database.
    'output_path' -- the directory to generate the output video files in.
    '''

    def __init__(self, disturbances, indicators, output_path="."):
        self._disturbances = disturbances
        self._indicators = indicators
        self._output_path = output_path

    def render(self, bounding_box=None, start_year=None, end_year=None, fps=1,
               include_single_views=False, save_frames=False):
        '''
        Renders a set of animations, one for each Indicator in this animator.

        Arguments:
        'bounding_box' -- a Layer object to act as a bounding box for the rendered
            frames: disturbance and spatial output layers will be cropped to the
            bounding box's minimum spatial extent and nodata pixels.
        'start_year' -- the year to render from - if not provided, will be detected
            from the indicator.
        'end_year' -- the year to render to - if not provided, will be detected
            from the indicator.
        'fps' -- the framerate to use for the output animation - default 1.
        'include_single_views' -- include animations for each result view (graph,
            map, disturbances) separately in addition to the standard 4-quadrant
            layout.
        'save_frames' -- also save the individual frames that make up the animation.
        '''
        os.makedirs(self._output_path, exist_ok=True)

        disturbance_frames = None
        disturbance_legend = None
        for indicator in self._indicators:
            logging.info(f"Rendering animation: {indicator.title}")

            if not start_year or not end_year:
                indicator_start_year, indicator_end_year = indicator.simulation_years
                start_year = start_year or indicator_start_year
                end_year = end_year or indicator_end_year

            graph_frames = indicator.render_graph_frames(
                bounding_box=bounding_box, start_year=start_year, end_year=end_year)

            has_graph_frames = graph_frames is not None and len(graph_frames) > 0

            units = _(indicator.map_units.value[2])
            units_label = f" ({units})" if units else ""
            indicator_legend_title = f"{indicator.indicator}{units_label}"
            indicator_frames, indicator_legend = indicator.render_map_frames(
                bounding_box, start_year, end_year)

            if not disturbance_frames:
                logging.info(f"{indicator.title}: rendering disturbance frames")
                disturbance_frames, disturbance_legend = self._disturbances.render(
                    bounding_box, start_year, end_year)

            if include_single_views:
                self._render_single_view(f"{indicator.title} " + _("(graph view)"),
                                         graph_frames, start_year, end_year, scalebar=False)

                self._render_single_view(f"{indicator.title} " + _("(map view)"), indicator_frames,
                                         start_year, end_year, indicator_legend, indicator_legend_title)

            left_legend_frame = Legend({None: disturbance_legend}).render()
            right_legend_frame = Legend({None: indicator_legend}).render()

            layout = BoxLayout([
                [(50, 60, False), (50, 60, True)],
                [(25, 40, False), (50, 40, False), (25, 40, False)]
            ])

            animation_frames = []
            for year in range(start_year, end_year + 1):
                disturbance_frame = self._find_frame(disturbance_frames, year)
                indicator_frame = self._find_frame(indicator_frames, year)
                graph_frame = self._find_frame(graph_frames, year) if has_graph_frames else None
                title = f"{indicator.title}, " + _("Year:") + f" {year}"
                animation_frames.append(layout.render([
                    [(disturbance_frame, _("Disturbances")), (indicator_frame, indicator_legend_title)],
                    [(left_legend_frame, None), (graph_frame, indicator.indicator), (right_legend_frame, None)]
                ], title=title, dimensions=(3840, 2160)))

            logging.info(f"{indicator.title}: creating final output")
            self._create_animation(indicator.title, animation_frames, fps)
        
            if save_frames:
                for frame in animation_frames:
                    shutil.copyfile(frame.path, os.path.join(self._output_path, os.path.basename(frame.path)))

        if include_single_views:
            self._render_single_view(_("Disturbances"), disturbance_frames, start_year, end_year,
                                     disturbance_legend, _("Disturbances"), fps=fps)

    def _render_single_view(self, title, frames, start_year, end_year,
                            legend=None, legend_title=None, scalebar=True, fps=1):

        box_sizes = [[(70, 100, scalebar), (30, 100, False)]] if legend else [[(100, 100, scalebar)]]
        layout = BoxLayout(box_sizes)
        legend_frame = Legend({legend_title: legend}).render() if legend else None

        animation_frames = []
        for year in range(start_year, end_year + 1):
            view_frame = self._find_frame(frames, year)
            frame_title = f"{title}, " + _("Year:") + f" {year}"
            animation_frames.append(layout.render(
                [[(view_frame, None)] + ([(legend_frame, None)] if legend else [])],
                title=frame_title, dimensions=(3840, 2160)))

        self._create_animation(title, animation_frames, fps)

    def _create_animation(self, title, frames, fps=1):
        video_frames = [imageio.imread(frame.path) for frame in frames]
        video_frames.append(video_frames[-1]) # Duplicate the last frame to display longer.
        imageio.mimsave(os.path.join(self._output_path, f"{title}.wmv"), video_frames,
                        fps=fps, ffmpeg_log_level="fatal", quality=8)

        TempFileManager.cleanup("*.tif")

    def _find_frame(self, frame_collection, year, default=None):
        return next(filter(lambda frame: frame.year == year, frame_collection), None)
