from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
from catplotlib.spatial.display.frame import Frame
from catplotlib.util.tempfile import TempFileManager
from itertools import chain
Image.MAX_IMAGE_PIXELS = None

class Box:
    '''
    A single component of a BoxLayout: its x/y origin (top left corner),
    width, height, display title, and whether or not to add a scalebar.
    '''

    def __init__(self, x_origin, y_origin, width, height, title=None, scalebar=False):
        self.x_origin = x_origin
        self.y_origin = y_origin
        self.width = width
        self.height = height
        self.title = title
        self.scalebar = scalebar


class BoxLayout:
    '''
    Combines frames into a layout composed of an arbitrary number of boxes.

    Arguments:
    'dimensions' -- list of lists of tuples where each inner list is a row in
        the overall layout, and each tuple gives the percent width and height
        of the combined image reserved for a layout box, and whether or not to
        include a scalebar (True/False).
    'margin' -- proportion of space in the combined image to reserve for the
        outer margin.
    '''

    def __init__(self, dimensions, margin=0.025):
        self._dimensions = dimensions
        self._margin = margin

    def render(self, contents, title=None, dimensions=None):
        '''
        Renders Frame data into the layout.

        Arguments:
        'contents' -- list of list of tuples in the same structure as the
            layout dimensions, where each inner list is a row, and each tuple
            contains the Frame to render and an optional title (or None).
        'title' -- optional title for the combined image.
        'dimensions' -- pixel dimensions for the combined image.

        Returns the combined image as a new Frame.
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

        boxes = []
        row_y_min = canvas_y_min
        row_y_max = canvas_y_min
        for row in zip(self._dimensions, contents):
            box_x_min = canvas_x_min
            for (box_dimensions, box_data) in zip(*row):
                box_width, box_height, scalebar = box_dimensions
                box_frame, box_title = box_data
                box_x_px = int(box_width / 100 * canvas_width)
                box_y_px = int(box_height / 100 * canvas_height)
                boxes.append(Box(box_x_min, row_y_min, box_x_px, box_y_px, box_title, scalebar))
                
                box_x_min += box_x_px
                row_y_max = max(row_y_max, row_y_min + box_y_px)

            row_y_min = row_y_max

        box_label_font = None
        all_labels = [item[1] for item in chain(*contents) if item[1]]
        if all_labels:
            longest_label = sorted(all_labels, key=len, reverse=True)[0]
            narrowest_box = int(min((item[0] for item in chain(*self._dimensions))) / 100 * canvas_width)
            box_label_font = self._find_optimal_font_size(
                longest_label, narrowest_box, int(canvas_height * self._margin))

        for i, (frame, label) in enumerate(chain(*contents)):
            if frame:
                self._render_box(image, boxes[i], frame, box_label_font)

        out_path = TempFileManager.mktmp(suffix=".png")
        image.save(out_path)

        return Frame(contents[0][0][0].year, out_path)
    
    def _render_box(self, base_image, box, frame, font):
        true_title_height = 0
        if box.title:
            base_width, base_height = base_image.size
            title_width, title_height = font.getsize(box.title)
            true_title_height = int(title_height) + int(base_height * 0.01)
            title_x_pos = int(box.x_origin + box.width / 2 - title_width / 2)
            title_y_pos = int(box.y_origin + true_title_height // 2)
            ImageDraw.Draw(base_image).text(
                (title_x_pos, title_y_pos), box.title, (0, 0, 0, 255), font=font)

        working_frame = frame.resize(
            int(box.width * (1 - self._margin * 2)),
            int((box.height - true_title_height) * (1 - self._margin * 2)))

        new_width, new_height = working_frame.size
        x_offset = (box.width - new_width) // 2
        x_pos = box.x_origin + x_offset
        y_offset = (box.height - new_height) // 2
        y_pos = box.y_origin + y_offset + true_title_height // 2

        frame_image = Image.open(working_frame.path)
        base_image.paste(frame_image, (x_pos, y_pos))

        if box.scalebar:
            self._add_scalebar(base_image, box, working_frame.scale)

    def _add_scalebar(self, base_image, box, scale):
        scalebar_length_px = box.width // 5
        scalebar_length_km = scalebar_length_px * scale / 1000
        scalebar_height = box.height // 20

        label = f"{scalebar_length_km:.2f} km"
        font = self._find_optimal_font_size(label, scalebar_length_px, scalebar_height * 0.75)
        label_width, label_height = font.getsize(label)
        label_x = box.x_origin + box.width - label_width
        label_y = box.y_origin + box.height - label_height

        draw = ImageDraw.Draw(base_image)
        draw.text((label_x, label_y), label, font=font, fill=(0, 0, 0, 128))
        line_width = scalebar_height - label_height
        draw.line((box.x_origin + box.width - scalebar_length_px,
                   box.y_origin + box.height - label_height - line_width // 2,
                   box.x_origin + box.width,
                   box.y_origin + box.height - label_height - line_width // 2),
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
