import locale
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
from catplotlib.spatial.display.frame import Frame
from catplotlib.util.tempfile import TempFileManager
Image.MAX_IMAGE_PIXELS = None

class Quadrant:
    '''
    Represents a quadrant of a QuadrantLayout: its x/y origin (top left corner),
    width, height, display title, and whether or not to add a scalebar.
    '''

    def __init__(self, x_origin, y_origin, width, height, title=None, scalebar=False):
        self.x_origin = x_origin
        self.y_origin = y_origin
        self.width = width
        self.height = height
        self.title = title
        self.scalebar = scalebar


class QuadrantLayout:
    '''
    Combines frames into a 4-box layout.

    Arguments:
    'qN_pct' -- tuple giving the percent width and height of the combined image
        reserved for quadrant N.
    'margin' -- proportion of space in the combined image to reserve for the
        outer margin.
    '''

    def __init__(self, q1_pct, q2_pct, q3_pct, q4_pct, margin=0.025, q1_scalebar=False,
                 q2_scalebar=True, q3_scalebar=False, q4_scalebar=False):
        self._q1_pct = q1_pct
        self._q2_pct = q2_pct
        self._q3_pct = q3_pct
        self._q4_pct = q4_pct
        self._margin = margin
        self._q1_scalebar = q1_scalebar
        self._q2_scalebar = q2_scalebar
        self._q3_scalebar = q3_scalebar
        self._q4_scalebar = q4_scalebar

    def render(
        self, q1_frame, q2_frame, q3_frame, q4_frame,
        q1_label=None, q2_label=None, q3_label=None, q4_label=None,
        title=None, dimensions=None
    ):
        '''
        Renders four Frame objects into a single Frame with a quadrant layout.

        Arguments:
        'qN_frame' -- Frame object to render in quadrant N.
        'qN_label' -- optional title for quadrant N.
        'title' -- optional title for the combined image.
        'dimensions' -- pixel dimensions for the combined image.

        Returns the combined image as a new Frame for the same year as q1_frame.
        '''
        width, height = dimensions or (640, 480)
        x_margin = int(width * self._margin // 2)
        y_margin = int(height * self._margin // 2)

        canvas_width = int(width * (1 - self._margin * 1.5))
        canvas_height = int(height * (1 - self._margin * 1.5))
        canvas_x_min = x_margin
        canvas_x_max = width - x_margin
        canvas_y_min = y_margin
        canvas_y_max = height - y_margin

        image = Image.new("RGBA", dimensions, (255, 255, 255, 255))

        if title:
            title_font = self._find_optimal_font_size(title, canvas_width, int(height * 0.05))
            title_w, title_h = title_font.getsize(title)
            true_title_height = int(title_h) + int(height * 0.01)
            
            title_x = width // 2 - title_w // 2
            title_y = canvas_y_min
            ImageDraw.Draw(image).text((title_x, title_y), title, (0, 0, 0), font=title_font)

            canvas_height -= true_title_height
            canvas_y_min += true_title_height

        quadrants = [
            Quadrant(canvas_x_min,
                     canvas_y_min,
                     int(self._q1_pct[0] / 100 * canvas_width),
                     int(self._q1_pct[1] / 100 * canvas_height),
                     q1_label, self._q1_scalebar),
            Quadrant(int(canvas_x_max - self._q2_pct[0] / 100 * canvas_width),
                     canvas_y_min,
                     int(self._q2_pct[0] / 100 * canvas_width),
                     int(self._q2_pct[1] / 100 * canvas_height),
                     q2_label, self._q2_scalebar),
            Quadrant(canvas_x_min,
                     int(canvas_y_max - self._q3_pct[1] / 100 * canvas_height + y_margin // 4),
                     int(self._q3_pct[0] / 100 * canvas_width),
                     int(self._q3_pct[1] / 100 * canvas_height),
                     q3_label, self._q3_scalebar),
            Quadrant(int(canvas_x_max - self._q4_pct[0] / 100 * canvas_width),
                     int(canvas_y_max - self._q4_pct[1] / 100 * canvas_height + y_margin // 4),
                     int(self._q4_pct[0] / 100 * canvas_width),
                     int(self._q4_pct[1] / 100 * canvas_height),
                     q4_label, self._q4_scalebar)]

        quadrant_label_font = None
        all_labels = [label for label in (q1_label, q2_label, q3_label, q4_label) if label]
        if all_labels:
            longest_label = sorted(all_labels, key=len, reverse=True)[0]
            quadrant_label_font = self._find_optimal_font_size(
                longest_label, canvas_width // 4, int(canvas_height * self._margin))

        for i, frame in enumerate((q1_frame, q2_frame, q3_frame, q4_frame)):
            if frame:
                self._render_quadrant(image, quadrants[i], frame, quadrant_label_font)

        out_path = TempFileManager.mktmp(suffix=".png")
        image.save(out_path)

        return Frame(q1_frame.year, out_path)
    
    def _render_quadrant(self, base_image, quadrant, frame, font):
        true_title_height = 0
        if quadrant.title:
            base_width, base_height = base_image.size
            title_width, title_height = font.getsize(quadrant.title)
            true_title_height = int(title_height) + int(base_height * 0.01)
            title_x_pos = int(quadrant.x_origin + quadrant.width / 2 - title_width / 2)
            title_y_pos = int(quadrant.y_origin + true_title_height // 2)
            ImageDraw.Draw(base_image).text(
                (title_x_pos, title_y_pos), quadrant.title, (0, 0, 0, 255), font=font)

        working_frame = frame.resize(
            int(quadrant.width * (1 - self._margin * 2)),
            int((quadrant.height - true_title_height) * (1 - self._margin * 2)))

        new_width, new_height = working_frame.size
        x_offset = (quadrant.width - new_width) // 2
        x_pos = quadrant.x_origin + x_offset
        y_offset = (quadrant.height - new_height) // 2
        y_pos = quadrant.y_origin + y_offset + true_title_height // 2

        frame_image = Image.open(working_frame.path)
        base_image.paste(frame_image, (x_pos, y_pos))

        if quadrant.scalebar:
            self._add_scalebar(base_image, quadrant, working_frame.scale)

    def _add_scalebar(self, base_image, quadrant, scale):
        scalebar_length_px = quadrant.width // 5
        scalebar_length_km = scalebar_length_px * scale / 1000
        scalebar_height = quadrant.height // 20

        label = locale.format_string("%.2f", scalebar_length_km) + " km"
        font = self._find_optimal_font_size(label, scalebar_length_px, scalebar_height * 0.75)
        label_width, label_height = font.getsize(label)
        label_x = quadrant.x_origin + quadrant.width - label_width
        label_y = quadrant.y_origin + quadrant.height - label_height

        draw = ImageDraw.Draw(base_image)
        draw.text((label_x, label_y), label, font=font, fill=(0, 0, 0, 128))
        line_width = scalebar_height - label_height
        draw.line((quadrant.x_origin + quadrant.width - scalebar_length_px,
                   quadrant.y_origin + quadrant.height - label_height - line_width // 2,
                   quadrant.x_origin + quadrant.width,
                   quadrant.y_origin + quadrant.height - label_height - line_width // 2),
                  fill=(0, 0, 0, 128), width=line_width)

    def _find_optimal_font_size(self, text, max_width, max_height, font_face="arial.ttf"):
        font_size = 1
        font = ImageFont.truetype(font_face, font_size)
        text_width, text_height = font.getsize(text)
        while text_width < max_width and text_height < max_height:
            font = ImageFont.truetype(font_face, font_size)
            text_width, text_height = font.getsize(text)
            font_size += 1

        return font
