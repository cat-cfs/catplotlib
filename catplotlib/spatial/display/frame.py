import matplotlib
from PIL import Image
from catplotlib.util.tempfile import TempFileManager
Image.MAX_IMAGE_PIXELS = None

class Frame:
    '''
    Represents a presentation-format image that can be included in an animation.
    A frame usually applies to a particular year and points to an image file on disk.

    Arguments:
    'year' -- the year this Frame applies to.
    'path' -- the path to the image file this Frame represents.
    '''

    def __init__(self, year, path, scale=None):
        self._year = year
        self._path = path
        self._scale = scale

    @property
    def year(self):
        '''The year this Frame applies to.'''
        return self._year

    @property
    def path(self):
        '''The path to the Frame's image file.'''
        return self._path

    @property
    def scale(self):
        '''
        The scale (in metres per pixel) of the image, where None means
        unknown or not applicable.
        '''
        return self._scale

    @property
    def size(self):
        '''The width and height of the image.'''
        return Image.open(self._path).size

    def composite(self, frame, send_to_bottom=False):
        '''
        Combines another RGBA Frame with this one using their alpha channels.

        Arguments:
        'frame' -- the frame to combine with this one.
        'send_to_bottom' -- use the other frame as the background instead of
            this one.

        Returns the merged image as a new Frame with the same year as this one.
        '''
        out_path = TempFileManager.mktmp(suffix=".png")
        this_image = Image.open(self._path)
        other_image = Image.open(frame.path)

        if send_to_bottom:
            Image.alpha_composite(other_image, this_image).save(out_path)
        else:
            Image.alpha_composite(this_image, other_image).save(out_path)

        return Frame(self._year, out_path, self._scale)

    def merge_horizontal(self, *frames):
        '''
        Merges one or more Frames horizontally with this one.

        Arguments:
        'frames' -- one or more Frames to merge horizontally.

        Returns the merged image as a new Frame with the same year as this one.
        '''
        images = [Image.open(self._path)] + [Image.open(frame.path) for frame in frames]
        widths, heights = zip(*(image.size for image in images))

        total_width = sum(widths)
        max_height = max(heights)

        merged_image = Image.new("RGBA", (total_width, max_height), color=(255, 255, 255, 255))

        x_offset = 0
        for image in images:
            merged_image.paste(image, (x_offset, 0))
            x_offset += image.size[0]

        out_path = TempFileManager.mktmp(suffix=".png")
        merged_image.save(out_path)

        return Frame(self._year, out_path, scale=None)

    def resize(self, max_width, max_height):
        '''
        Resizes the image as closely as possible to the specified width and height
        while preserving the aspect ratio.

        Arguments:
        'max_width' -- the new maximum width.
        'max_height' -- the new maximum height.

        Returns the resized image as a new Frame with the same year as this one
        and updated scale reflecting the new pixel size in metres.
        '''
        original_width, original_height = self.size
        aspect_ratio = original_width / original_height

        if aspect_ratio > 1:
            new_width = max_width
            new_height = int(new_width / aspect_ratio)
            if new_height > max_height:
                new_height = max_height
                new_width = int(new_height * aspect_ratio)
        else:
            new_height = max_height
            new_width = int(new_height * aspect_ratio)
            if new_width > max_width:
                new_width = max_width
                new_height = int(new_width / aspect_ratio)

        out_path = TempFileManager.mktmp(suffix=".png")
        Image.open(self.path).resize((new_width, new_height), Image.ANTIALIAS).save(out_path)
        new_scale = self._scale * (original_width / new_width) if self._scale else None

        return Frame(self._year, out_path, new_scale)
