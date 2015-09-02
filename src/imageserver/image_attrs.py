#
# Quru Image Server
#
# Document:      image_attrs.py
# Date started:  31 Mar 2011
# By:            Matt Fozard
# Purpose:       Wrapper for required image attribute changes
# Requires:
# Copyright:     Quru Ltd (www.quru.com)
# Licence:
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see http://www.gnu.org/licenses/
#
# Last Changed:  $Date$ $Rev$ by $Author$
#
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
# 29Sep2011  Matt  Changed cache key/hashes to use unique image ID
# 14May2015  Matt  #2517 Normalize the image src
#

import re
import threading

from flask_app import app
from util import filepath_filename, filepath_parent, filepath_normalize
from util import get_file_extension, round_crop, unicode_to_ascii
from util import validate_number, validate_tile_spec

# We'll cache the image attribute validators. One copy per thread as I suspect
# - e.g. the RegexValidator construction - probably isn't thread safe.
thread_data = threading.local()


class AttributeValidator(object):
    pass


class FuncWrapValidator(AttributeValidator):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, value):
        return self.func(value, *self.args, **self.kwargs)


class RangeValidator(FuncWrapValidator):
    func = staticmethod(validate_number)

    @property
    def min(self):
        return self.args[0]

    @property
    def max(self):
        return self.args[1]


class TileValidator(FuncWrapValidator):
    func = staticmethod(validate_tile_spec)


class RegexValidator(AttributeValidator):
    def __init__(self, pattern, flags=0):
        self.rx = re.compile(pattern, flags)

    def __call__(self, value):
        matches = self.rx.match(value)
        if not matches:
            raise ValueError(
                "Pattern %r did not match %r" %
                (self.rx.pattern, value)
            )
        return True


class LengthValidator(RangeValidator):
    def __call__(self, value):
        value_len = 0 if value is None else len(value)
        return super(LengthValidator, self).__call__(value_len)


class RealRangeValidator(RangeValidator):
    pass


class IntegerValidator(RangeValidator):
    def __call__(self, value):
        if not isinstance(value, int):
            raise ValueError("Value %r is not an int" % value)
        return super(IntegerValidator, self).__call__(value)


class TypeValidator(AttributeValidator):
    def __call__(self, value):
        if type(value) != self.valid_type:
            raise ValueError(
                "Value %r had type %r, not %r" %
                (value, type(value), self.valid_type)
            )
        return True


class BooleanValidator(TypeValidator):
    valid_type = bool


class ChoiceValidator(AttributeValidator):
    def __init__(self, choices):
        self._choices = choices

    @property
    def choices(self):
        return self._choices() if callable(self._choices) else self._choices

    def __call__(self, value):
        if value not in self.choices:
            raise ValueError(
                "Value %r not a valid choice. %r" %
                (value, self.choices)
            )
        return True


class ICCProfileValidator(ChoiceValidator):
    def icc_choices(self):
        """
        Returns a dictionary of the available ICC profile choices,
        grouped by the colorspace of the profiles.
        """
        iccs = {}
        icc_types = app.image_engine.get_icc_profile_colorspaces()
        for cspace in icc_types:
            iccs[cspace] = app.image_engine.get_icc_profile_names(cspace)
            iccs[cspace].sort()
        return iccs


class AlignValidator(RegexValidator):
    def __init__(self, edge_codes):
        self.edge_choices = edge_codes

        regex_codes = "".join(edge_codes)
        super(AlignValidator, self).__init__(
            "[" + regex_codes + "](0(\.\d+)?|1(\.0+)?)$"
        )


class ImageAttrs():
    """
    Class to wrap and manage the attribute changes required for an image.

    src is the only mandatory parameter, the full relative image file path.
    db_id is the unique database ID, 0 if the image is new, or -1 if not known
    (only required for creating the cache key and searching hashes).

    Setting an attribute value to None (or not specifying a value) means
    "leave this attribute unchanged" with respect to the original image.

    Users of this class should call validate() at some point before using
    the attribute values.
    """
    class_version = 1500

    def __init__(self, src, db_id=-1, page=None,
                 iformat=None, template=None, width=None, height=None,
                 align_h=None, align_v=None, rotation=None, flip=None,
                 top=None, left=None, bottom=None, right=None, crop_fit=None,
                 size_fit=None, fill=None, quality=None, sharpen=None,
                 overlay_src=None, overlay_size=None, overlay_pos=None, overlay_opacity=None,
                 icc_profile=None, icc_intent=None, icc_bpc=None, colorspace=None,
                 strip=None, dpi=None, tile_spec=None):
        self._version = self.__class__.class_version
        self._filename = filepath_normalize(src)
        self._filename_ext = get_file_extension(self._filename)
        self._db_id = db_id
        self._page = page
        self._format = self._no_blank(iformat)
        self._template = self._no_blank(template)
        self._width = width
        self._height = height
        self._align_h = self._no_blank(align_h)
        self._align_v = self._no_blank(align_v)
        self._rotation = rotation
        self._flip = self._no_blank(flip)
        self._top = top
        self._left = left
        self._bottom = bottom
        self._right = right
        self._crop_fit = crop_fit
        self._size_fit = size_fit
        self._fill = self._no_blank(fill)
        self._quality = quality
        self._sharpen = sharpen
        self._overlay_src = self._no_blank(overlay_src)
        self._overlay_size = overlay_size
        self._overlay_pos = self._no_blank(overlay_pos)
        self._overlay_opacity = overlay_opacity
        self._icc_profile = self._no_blank(icc_profile)
        self._icc_intent = self._no_blank(icc_intent)
        self._icc_bpc = icc_bpc
        self._colorspace = self._no_blank(colorspace)
        self._strip = strip
        self._dpi_x = dpi
        self._dpi_y = dpi
        self._tile = tile_spec
        self._round_floats()

    def __str__(self):
        filename = unicode_to_ascii(self.filename(with_path=False))
        if self._db_id > 0:
            return filename + ' ' + self.get_cache_key()
        else:
            return filename

    def __unicode__(self):
        return unicode(self.__str__())

    def to_dict(self):
        """
        Returns a dictionary of fields and values represented by this object.
        """
        dct = {}
        for attr in self.validators().keys():
            dct[attr] = getattr(self, "_%s" % attr)
        return dct

    def filename(self, with_path=True, append_format=False, replace_format=False):
        """
        Returns the supplied filename for this image, with or without the preceding
        path (with, by default).

        If append_format is True, the filename will be appended with .format if a
        format attribute has been given and is different from the filename's existing
        extension. Or if replace_format is True, the existing extension replaced.
        The virtual format 'pjpg' is returned as '.jpg' in these cases.
        """
        f = self._filename
        if not with_path:
            fname = filepath_filename(f)
            if fname:
                f = fname
        if (append_format or replace_format) and \
           self._format and \
           self._format != self._filename_ext:
            # Do not return filenames with the pjpg virtual format
            final_ext = self._format
            if final_ext in ['pjpg', 'pjpeg']:
                if self._filename_ext in ['jpg', 'jpeg']:
                    final_ext = self._filename_ext
                else:
                    final_ext = 'jpg'

            if append_format or not self._filename_ext:
                return f + '.' + final_ext
            elif replace_format:
                return f[0:-(len(self._filename_ext))] + final_ext
        return f

    def folder_path(self):
        """
        Returns the server's folder path (without filename) for this image.
        """
        return filepath_parent(self._filename) or ''

    def database_id(self):
        """
        Returns the image's database ID if known, 0 if there is not yet an image
        record, or -1 if the ID is not known or is not applicable (e.g. for
        temporary images).
        """
        return self._db_id

    def page(self):
        """
        Returns the page number attribute if it was supplied, or None
        """
        return self._page

    def format(self):
        """
        Returns the requested format of this image,
        or the filename's extension if no format attribute was supplied.
        """
        return self._format if self._format else self._filename_ext

    def format_raw(self):
        """
        Returns the format attribute if it was supplied, otherwise None
        """
        return self._format

    def mime_type(self):
        """
        Returns the internet MIME type for this image's required format.
        E.g. "image/jpeg".
        Raises a ValueError if the image's format is unknown.
        """
        try:
            (_, mime_type) = app.config['IMAGE_FORMATS'][self.format()]
            return mime_type
        except:
            raise ValueError('Unknown image type for ' + self.format())

    def template(self):
        """
        Returns the template attribute if it was supplied, or None
        """
        return self._template

    def width(self):
        """
        Returns the width attribute if it was supplied, or None
        """
        return self._width

    def height(self):
        """
        Returns the height attribute if it was supplied, or None
        """
        return self._height

    def align_h(self):
        """
        Returns the horizontal align attribute if it was supplied, or None
        """
        return self._align_h

    def align_v(self):
        """
        Returns the vertical align attribute if it was supplied, or None
        """
        return self._align_v

    def rotation(self):
        """
        Returns the rotation attribute if it was supplied, or None
        """
        return self._rotation

    def flip(self):
        """
        Returns the flip attribute if it was supplied, or None
        """
        return self._flip

    def top(self):
        """
        Returns the top attribute if it was supplied, or None
        """
        return self._top

    def left(self):
        """
        Returns the left attribute if it was supplied, or None
        """
        return self._left

    def bottom(self):
        """
        Returns the bottom attribute if it was supplied, or None
        """
        return self._bottom

    def right(self):
        """
        Returns the right attribute if it was supplied, or None
        """
        return self._right

    def crop_fit(self):
        """
        Returns the crop auto-fit attribute if it was supplied, or None
        """
        return self._crop_fit

    def size_fit(self):
        """
        Returns the size auto-fit attribute if it was supplied, or None
        """
        return self._size_fit

    def fill(self):
        """
        Returns the fill attribute if it was supplied, or None
        """
        return self._fill

    def quality(self):
        """
        Returns the quality attribute if it was supplied, or None
        """
        return self._quality

    def sharpen(self):
        """
        Returns the sharpen attribute if it was supplied, or None
        """
        return self._sharpen

    def overlay_src(self):
        """
        Returns the overlay_src attribute if it was supplied, or None
        """
        return self._overlay_src

    def overlay_opacity(self):
        """
        Returns the overlay_opacity attribute if it was supplied, or None
        """
        return self._overlay_opacity

    def overlay_size(self):
        """
        Returns the overlay_size attribute if it was supplied, or None
        """
        return self._overlay_size

    def overlay_pos(self):
        """
        Returns the overlay_pos attribute if it was supplied, or None
        """
        return self._overlay_pos

    def icc_profile(self):
        """
        Returns the ICC profile attribute if it was supplied, or None
        """
        return self._icc_profile

    def icc_intent(self):
        """
        Returns the ICC profile intent attribute if it was supplied, or None
        """
        return self._icc_intent

    def icc_bpc(self):
        """
        Returns the ICC Black Point Compensation attribute if it was supplied, or None
        """
        return self._icc_bpc

    def colorspace(self):
        """
        Returns the colorspace attribute if it was supplied, or None
        """
        return self._colorspace

    def strip_info(self):
        """
        Returns the strip attribute if it was supplied, or None
        """
        return self._strip

    def dpi(self):
        """
        Returns the DPI attribute if it was supplied, or None
        """
        return self._dpi_x

    def tile_spec(self):
        """
        Returns a tuple of (tile number, grid size) if this object represents
        a tile, or None
        """
        return self._tile

    def src_is_pdf(self):
        """
        Returns whether the image src appears to be a PDF or postscript file.
        This is based only on the file extension.
        """
        return self._filename_ext in app.config['PDF_FILE_TYPES']

    def set_database_id(self, db_id):
        """
        Sets the database ID, for use if it is not known at object creation time.
        """
        self._db_id = db_id

    @staticmethod
    def _validators():
        """
        Returns a dictionary mapping the internal field names of
        this class to a validation class and web parameter name.
        E.g. { "filename": (LengthValidator(1, 1024), "src"),
               "width": (RangeValidator(0, 10000), "width"), ... }
        """
        # These are lazy-loaded choices not available at import time
        formats = lambda: [""] + app.image_engine.get_image_formats()
        templates = lambda: [""] + app.image_engine.get_template_names()
        iccs = lambda: [""] + app.image_engine.get_icc_profile_names()
        # These are hard-coded choices
        ov_positions = ("", "c", "n", "e", "s", "w", "ne", "nw", "se", "sw")
        intents = ("", "saturation", "perceptual", "absolute", "relative")
        colorspaces = ("", "srgb", "rgb", "cmyk", "gray", "grey")

        return {
            "filename": (LengthValidator(1, 1024), 'src'),
            "page": (RangeValidator(0, 999999), 'page'),
            "format": (ChoiceValidator(formats), 'format'),
            "template": (ChoiceValidator(templates), 'tmp'),
            "width": (
                RangeValidator(0, app.config['MAX_IMAGE_DIMENSION']),
                'width'
            ),
            "height": (
                RangeValidator(0, app.config['MAX_IMAGE_DIMENSION']),
                'height'
            ),
            "align_h": (AlignValidator(("l", "c", "r")), 'halign'),
            "align_v": (AlignValidator(("t", "c", "b")), 'valign'),
            "rotation": (RealRangeValidator(-360.0, 360.0), 'angle'),
            "flip": (ChoiceValidator(("", "h", "v")), 'flip'),
            "top": (RealRangeValidator(0.0, 1.0), 'top'),
            "left": (RealRangeValidator(0.0, 1.0), 'left'),
            "bottom": (RealRangeValidator(0.0, 1.0), 'bottom'),
            "right": (RealRangeValidator(0.0, 1.0), 'right'),
            "crop_fit": (BooleanValidator(), 'autocropfit'),
            "size_fit": (BooleanValidator(), 'autosizefit'),
            "fill": (LengthValidator(3, 32), 'fill'),
            "quality": (RangeValidator(1, 100), 'quality'),
            "sharpen": (RangeValidator(-500, 500), 'sharpen'),
            "overlay_src": (LengthValidator(1, 1024), 'overlay'),
            "overlay_pos": (ChoiceValidator(ov_positions), 'ovpos'),
            "overlay_size": (RealRangeValidator(0.0, 1.0), 'ovsize'),
            "overlay_opacity": (RealRangeValidator(0.0, 1.0), 'ovopacity'),
            "icc_profile": (ICCProfileValidator(iccs), 'icc'),
            "icc_intent": (ChoiceValidator(intents), 'intent'),
            "icc_bpc": (BooleanValidator(), 'bpc'),
            "colorspace": (ChoiceValidator(colorspaces), 'colorspace'),
            "strip": (BooleanValidator(), 'strip'),
            "dpi_x": (RangeValidator(0, 32000), 'dpi'),
            "dpi_y": (RangeValidator(0, 32000), 'dpi'),
            "tile": (TileValidator(app.config['MAX_GRID_TILES']), 'tile')
        }

    @staticmethod
    def reset_validators():
        """
        Resets the cached validators, for the current thread only.
        This will be necessary if any of the application configuration
        affecting validation changes e.g. new IMAGE_FORMATS.
        """
        try:
            del thread_data.validators
            del thread_data.validators_flat
        except AttributeError:
            pass

    @staticmethod
    def validators():
        """
        Returns a cached dictionary mapping the internal field names of
        this class to a validation class and web parameter name.
        E.g. { "filename": (LengthValidator(1, 1024), "src"),
               "width": (RangeValidator(0, 10000), "width"), ... }
        """
        try:
            return thread_data.validators
        except AttributeError:
            thread_data.validators = ImageAttrs._validators()
            return thread_data.validators

    @staticmethod
    def validators_flat():
        """
        Returns a cached version of validators() as a flat list of tuples.
        E.g. [ ("filename", LengthValidator(1, 1024), "src"),
               ("width", RangeValidator(0, 10000), "width"), ... ]
        """
        try:
            return thread_data.validators_flat
        except AttributeError:
            d = ImageAttrs.validators()
            thread_data.validators_flat = [(k, d[k][0], d[k][1]) for k in d]
            return thread_data.validators_flat

    def validate(self):
        """
        Validates that all attributes, if they have been given a value, are of
        the correct data type and within allowed limits. This method raises a
        ValueError if an attribute value is invalid, otherwise returns with no value.
        """
        try:
            validators = self.validators_flat()
            for (attr, validator, web_attr) in validators:
                val = getattr(self, "_%s" % attr)
                if val is not None:
                    validator(val)
        except ValueError as e:
            raise ValueError('%s: %s' % (web_attr, str(e)))

    def attributes_change_image(self):
        """
        Returns a boolean indicating whether the image attributes held by
        this object would change the original image. Simply, this is True
        if the image format has changed or if any of the attributes
        (excluding template name) has been given a value.

        Because the template name is not considered by this function, callers
        should ensure that apply_template_values() has been invoked as
        required before calling this function.
        """
        # aligns, fill, crop_fit, size_fit, overlay_*, ICC intent and BPC
        # require other attributes to be set to have any effect,
        # so they don't need checking below.
        return (
            (self.format_raw() is not None) or
            (self.page() is not None) or
            (self.rotation() is not None) or
            (self.flip() is not None) or
            (self.width() is not None) or
            (self.height() is not None) or
            (self.top() is not None) or
            (self.left() is not None) or
            (self.bottom() is not None) or
            (self.right() is not None) or
            (self.quality() is not None) or
            (self.sharpen() is not None) or
            (self.overlay_src() is not None) or
            (self.icc_profile() is not None) or
            (self.colorspace() is not None) or
            (self.dpi() is not None) or
            self.strip_info() or
            (self.tile_spec() is not None)
        )

    def suitable_for_base(self, target_attrs):
        """
        Detects whether this set of image attributes defines an image that
        would be suitable as a base to create the image with target_attrs.
        You should ensure that normalise_values() has been called first for
        both this object and the target object.

        Returns a numeric reason code if the check fails, or 0 if this object
        would make a good base image.

        Since this class holds image attribute changes rather than the actual
        known image attributes, the filenames must match at the very least.
        i.e. There is no way of telling here whether a different filename
        would be a suitable base, even if it was in reality a copy of this one.

        Note that ImageManager._adjust_image() relies on the behaviour of this
        function, and is required to cancel some operations (e.g. do not apply
        duplicate rotation, if the source image is already rotated) based on
        this return value.
        """
        base = self
        target = target_attrs

        # Filename must match
        if base.filename() != target.filename():
            return 1

        # Page must match
        if base.page() != target.page():
            return 2

        # File formats must match (a lossy jpg is no good as a base for lossless png)
        if base.format() != target.format():
            return 3

        # Fill must match. normalise_values tries its best to clear the
        # fill if it won't actually apply, so this check shouldn't fail incorrectly.
        if base.fill() != target.fill():
            return 4

        # Sharpen on base must be None or the target image will be created with
        # its sharpening on top, resulting in an incorrect or poor image
        if base.sharpen() is not None:
            return 5

        # Aspect ratios must match, within reason
        # (it will vary a bit for resized versions of the same image)
        if base.width() is not None and base.height() is not None and not base.size_fit():
            this_aspect = round(float(base.width()) / float(base.height()), 2)
        else:
            this_aspect = -1   # Aspect unchanged
        if target.width() is not None and target.height() is not None and not target.size_fit():
            target_aspect = round(float(target.width()) / float(target.height()), 2)
        else:
            target_aspect = -1
        if this_aspect != target_aspect:
            return 6

        # Quality of base must be as good as or better than the target.
        # Unspecified quality is 101, because the original unmodified image
        # quality cannot be bettered by a copy of it, even if the copy is "100%".
        this_quality = 101 if base.quality() is None else base.quality()
        target_quality = 101 if target.quality() is None else target.quality()
        if this_quality < target_quality:
            return 7

        # Width and height are similar to quality. If None, the width/height is
        # original and cannot be bettered. Since in Python (1 > None) == True
        # we must swap None for a large int (same as the 101 for quality).
        this_width    = 999999999 if base.width() is None else base.width()
        this_height   = 999999999 if base.height() is None else base.height()
        target_width  = 999999999 if target.width() is None else target.width()
        target_height = 999999999 if target.height() is None else target.height()
        if this_width < target_width or this_height < target_height:
            return 8

        # Define some helpers to continue. As for fill (above),
        # these are relying on normalise_values() having been performed.
        base_is_flipped = base.flip() is not None
        base_is_rotated = base.rotation() is not None
        base_is_cropped = (
            base.top() is not None or
            base.left() is not None or
            base.bottom() is not None or
            base.right() is not None
        )

        # Flip value of base must be either none or the same
        if base_is_flipped and base.flip() != target.flip():
            return 9

        # Rotation of the base must either none or the same
        if base_is_rotated and base.rotation() != target.rotation():
            return 10

        # Size fit must be the same if the base might be re-aspected already
        # (and we've checked that the target aspect matches the base aspect)
        # otherwise it doesn't matter
        if this_aspect != -1 and base.size_fit() != target.size_fit():
            return 11

        # Strip irrelevant if target will strip, otherwise base must not be stripped
        # (apart from ICC processing, which is handled below)
        if not target.strip_info() and base.strip_info():
            return 12

        # For PDFs, DPI determines the image size; for other types, it's just metadata
        if base.src_is_pdf():
            # DPI must be the same (otherwise the image engine will set the DPI
            # metadata but won't actually resize it to reflect the new DPI)
            if base.dpi() != target.dpi():
                return 13
        else:
            # DPI irrelevant if target will set it, otherwise base must be original DPI
            if not target.dpi() and base.dpi():
                return 13

        # ICC of the base must be none or the same
        if base.icc_profile() is not None and (
            base.icc_profile() != target.icc_profile() or
            base.icc_intent() != target.icc_intent() or
            base.icc_bpc() != target.icc_bpc()):
            return 14
        # If target wants ICC then base can't be stripped either
        if target.icc_profile() and base.strip_info():
            return 14

        # Colorspace of the base must either none or the same
        if base.colorspace() is not None and base.colorspace() != target.colorspace():
            return 15

        # Base crop must be identical (all the same or all None) to the target.
        # Even if the base crop is all None this is only a suitable base if width
        # and height are the originals, otherwise the base would be a resized
        # version with missing pixels that the new crop might require.
        crop_match = (
            base_is_cropped == False and
            base.width() is None and
            base.height() is None
        ) or (
            # The same crop, and
            base.top() == target.top() and
            base.left() == target.left() and
            base.bottom() == target.bottom() and
            base.right() == target.right() and (
                # both have no crop fit, or
                (not base.crop_fit() and not target.crop_fit()) or
                # both have the same crop fit
                (
                    base.crop_fit() and target.crop_fit() and
                    base.width() == target.width() and
                    base.height() == target.height()
                )
            )
        )
        if not crop_match:
            return 16

        # Base cannot contain an overlay unless we're tiling, in which case
        # the tile request must be for the exact same image. If base has an
        # overlay we: a) can't be sure the target image will end up with it still
        # at the right size and b) any image processing to come would be applied
        # on top of the overlay, instead of separately before the overlay.
        if base.overlay_src() is not None:
            if target.tile_spec() is None:
                return 17
            else:
                # Tiling a overlayed image, the target must be the same everything.
                # This bit also relies on the checks that have gone before.
                if (base.width() != target.width() or
                    base.height() != target.height() or
                    base.rotation() != target.rotation() or
                    base.flip() != target.flip() or
                    base.top() != target.top() or
                    base.left() != target.left() or
                    base.bottom() != target.bottom() or
                    base.right() != target.right() or
                    base.sharpen() != target.sharpen() or
                    base.overlay_src() != target.overlay_src() or
                    base.overlay_pos() != target.overlay_pos() or
                    base.overlay_opacity() != target.overlay_opacity() or
                    base.overlay_size() != target.overlay_size()
                ):
                    return 17

        # Tile OK if base is not a tile, otherwise must be the same tile
        # for the exact same shape and size
        tile_match = base.tile_spec() is None or (
            base.tile_spec() == target.tile_spec() and
            base.width() == target.width() and
            base.height() == target.height() and
            base.rotation() == target.rotation() and
            base.flip() == target.flip() and
            base.top() == target.top() and
            base.left() == target.left() and
            base.bottom() == target.bottom() and
            base.right() == target.right() and
            base.overlay_src() == target.overlay_src() and
            base.overlay_pos() == target.overlay_pos() and
            base.overlay_opacity() == target.overlay_opacity() and
            base.overlay_size() == target.overlay_size()
        )
        if not tile_match:
            return 18

        # If the image might fill, aligns must be the same
        if (target.width() and target.height() and
            not target.size_fit()
        ):
            if (base.align_h() != target.align_h() or
                base.align_v() != target.align_v()
            ):
                return 19

        # #513 - this method must finally take into account the documented
        # order of operations. Namely: 1) Flip then 2) Rotate then 3) Crop.
        # The base image must be rejected when a flip/rotate/crop is
        # required if a later stage is already present in the base (even if it
        # has the same value). Otherwise the final image would have the
        # functions applied in the wrong order, giving a different output
        # when a base is used vs the same image generated from scratch.
        if target.flip() is not None:
            if base_is_rotated or base_is_cropped:
                return 20
        if target.rotation() is not None:
            if base_is_cropped:
                return 20

        # If we made it this far, it's a good base image
        return 0

    def get_metadata_cache_key(self):
        """
        As for get_cache_key() but returns a key for storing
        associated image metadata instead of the image itself.
        """
        return self.get_cache_key(_prefix='IMG_MD:')

    def get_cache_key(self, _prefix='IMG:'):
        """
        Returns a string representing a hash of all image attributes.
        If 2 cache keys are the same, the images and attributes are identical.

        Requires the database ID attribute to be set, and normalise_values()
        should first be called to ensure consistency across cache keys.

        Note: the template attribute is not included in the returned key,
        because template definitions may change during the lifetime of the
        cache. When a template is specified, callers should ensure that
        apply_template_values() has first been invoked.
        """
        assert self._db_id > 0, 'Image database ID must be set to create cache key'
        key_parts = [_prefix + str(self._db_id)]

        # Note: Most functions check for "is None" to see if a value is given.
        #       Here we treat all values as booleans because we do not want
        #       to include values with "", 0, False or None. In all cases
        #       these values ultimately mean "do not change".

        if self._format:
            key_parts.append('F' + self._format)

        if self._page:
            key_parts.append('G' + str(self._page))

        if self._width:
            key_parts.append('W' + str(self._width))

        if self._height:
            key_parts.append('H' + str(self._height))

        if self._align_h:
            key_parts.append('AH' + self._align_h)

        if self._align_v:
            key_parts.append('AV' + self._align_v)

        if self._rotation:
            key_parts.append('O' + self._float_to_str(self._rotation))

        if self._flip:
            key_parts.append('V' + str(self._flip))

        if self._top:
            key_parts.append('T' + self._float_to_str(self._top))

        if self._left:
            key_parts.append('L' + self._float_to_str(self._left))

        if self._bottom:
            key_parts.append('B' + self._float_to_str(self._bottom))

        if self._right:
            key_parts.append('R' + self._float_to_str(self._right))

        if self._crop_fit:
            key_parts.append('CF')

        if self._size_fit:
            key_parts.append('Z')

        if self._fill:
            key_parts.append('I' + self._fill)

        if self._quality:
            key_parts.append('Q' + str(self._quality))

        if self._sharpen:
            key_parts.append('S' + str(self._sharpen))

        if self._overlay_src:
            key_parts.append('Y' + str(hash(self._overlay_src)))

        if self._overlay_pos:
            key_parts.append('YP' + self._overlay_pos)

        if self._overlay_opacity:
            key_parts.append('YO' + self._float_to_str(self._overlay_opacity))

        if self._overlay_size:
            key_parts.append('YS' + self._float_to_str(self._overlay_size))

        if self._icc_profile:
            key_parts.append('P' + self._icc_profile)

        if self._icc_intent:
            key_parts.append('N' + self._icc_intent)

        if self._icc_bpc:
            key_parts.append('C')

        if self._colorspace:
            key_parts.append('K' + self._colorspace)

        if self._strip:
            key_parts.append('X')

        if self._dpi_x:
            key_parts.append('D' + str(self._dpi_x))

        if self._tile:
            key_parts.append('E%s:%s' % (self._tile[0], self._tile[1]))

        return ','.join(key_parts)

    def apply_template_values(
        self, override_values, page, iformat,
        width, height, align_h, align_v,
        rotation, flip,
        top, left, bottom, right, crop_fit,
        size_fit, fill, quality, sharpen,
        overlay_src, overlay_size, overlay_pos, overlay_opacity,
        icc_profile, icc_intent, icc_bpc,
        colorspace, strip, dpi
    ):
        """
        Applies a set of new image attributes to this object.
        If override_values is False, each new attribute value will only be applied
        if there is no existing value for that attribute.
        """
        if override_values or self._format is None:
            self._format = self._no_blank(iformat)

        if override_values or self._page is None:
            self._page = page

        if override_values or self._width is None:
            self._width = width

        if override_values or self._height is None:
            self._height = height

        if override_values or self._align_h is None:
            self._align_h = align_h

        if override_values or self._align_v is None:
            self._align_v = align_v

        if override_values or self._rotation is None:
            self._rotation = rotation

        if override_values or self._flip is None:
            self._flip = self._no_blank(flip)

        if override_values or self._top is None:
            self._top = top

        if override_values or self._left is None:
            self._left = left

        if override_values or self._bottom is None:
            self._bottom = bottom

        if override_values or self._right is None:
            self._right = right

        if override_values or self._crop_fit is None:
            self._crop_fit = crop_fit

        if override_values or self._size_fit is None:
            self._size_fit = size_fit

        if override_values or self._fill is None:
            self._fill = self._no_blank(fill)

        if override_values or self._quality is None:
            self._quality = quality

        if override_values or self._sharpen is None:
            self._sharpen = sharpen

        if override_values or self._overlay_src is None:
            self._overlay_src = self._no_blank(overlay_src)

        if override_values or self._overlay_size is None:
            self._overlay_size = overlay_size

        if override_values or self._overlay_pos is None:
            self._overlay_pos = self._no_blank(overlay_pos)

        if override_values or self._overlay_opacity is None:
            self._overlay_opacity = overlay_opacity

        if override_values or self._icc_profile is None:
            self._icc_profile = self._no_blank(icc_profile)

        if override_values or self._icc_intent is None:
            self._icc_intent = self._no_blank(icc_intent)

        if override_values or self._icc_bpc is None:
            self._icc_bpc = icc_bpc

        if override_values or self._colorspace is None:
            self._colorspace = self._no_blank(colorspace)

        if override_values or self._strip is None:
            self._strip = strip

        if override_values or self._dpi_x is None:
            self._dpi_x = dpi

        if override_values or self._dpi_y is None:
            self._dpi_y = dpi

        self._round_floats()

    def apply_default_values(
        self, iformat=None, colorspace=None, strip=None, dpi=None
    ):
        """
        Applies optional default image attributes for this object.
        Each new attribute value will only be applied if it is not None and if
        there is no existing value for that attribute.
        """
        if iformat and self._format is None:
            self._format = self._no_blank(iformat)

        if colorspace and self._colorspace is None and self._icc_profile is None:
            # Note we only do this if the ICC profile is blank too
            self._colorspace = self._no_blank(colorspace)

        if strip and self._strip is None:
            self._strip = strip

        if dpi and self._dpi_x is None:
            self._dpi_x = dpi

        if dpi and self._dpi_y is None:
            self._dpi_y = dpi

    def normalise_values(self):
        """
        Removes all attributes with a value if they would have no effect.
        E.g. a rotation value of 0 or 360 can be safely removed.
        Clearing unnecessary values improves consistency and helps to standardise
        the cache key for improved caching performance.

        It is necessary to call this function before calling attributes_change_image
        or suitable_for_base.

        But this function should not be called until after apply_template_values
        and apply_default_values, so that attribute removal is not performed until
        all possible parameters have been applied.
        """
        if self._page == 0 or self._page == 1:
            self._page = None

        if self._format == 'pjpeg':
            self._format = 'pjpg'

        if self._format == self._filename_ext:
            self._format = None

        if self._width == 0:
            self._width = None

        if self._height == 0:
            self._height = None

        if self._align_h == 'c0.5':
            self._align_h = None

        if self._align_v == 'c0.5':
            self._align_v = None

        if (
            self._rotation == 0 or
            self._rotation == -360 or
            self._rotation == 360
        ):
            self._rotation = None

        if self._top == 0 or self._top == 1:
            self._top = None

        if self._left == 0 or self._left == 1:
            self._left = None

        if self._bottom == 1 or self._bottom == 0:
            self._bottom = None

        if self._right == 1 or self._right == 0:
            self._right = None

        if (
            self._size_fit and
            (self._width is None or self._height is None)
        ):
            self._size_fit = None

        if (
            self._crop_fit and
            self._top is None and
            self._left is None and
            self._bottom is None and
            self._right is None
        ):
            self._crop_fit = None

        if (
            self._fill == '#ffffff' or
            self._fill == 'white' or
            self._fill == 'rgb(255,255,255)'
        ):
            self._fill = None

        if self._quality == 0:
            self._quality = None

        if self._sharpen == 0:
            self._sharpen = None

        if self._overlay_pos == 'c':
            self._overlay_pos = None

        if self._overlay_opacity == 1:
            self._overlay_opacity = None

        if self._overlay_size == 1:
            self._overlay_size = None

        if self._dpi_x == 0:
            self._dpi_x = None

        if self._dpi_y == 0:
            self._dpi_y = None

        if self._tile and (self._tile[1] < 2):
            self._tile = None

        # Rotate 180 + flip v == flip h
        if self._rotation == 180 and self._flip == 'v':
            self._rotation = None
            self._flip = 'h'

        # Rotate 180 + flip h == flip v
        if self._rotation == 180 and self._flip == 'h':
            self._rotation = None
            self._flip = 'v'

        not_stretched = (self._width is None or self._height is None or
                         self._size_fit)

        # If fill is still set, ensure it would actually take effect.
        # It will mess up the base image detection if set unnecessarily.
        if (self._fill is not None and
            not_stretched and self._rotation is None
        ):
            self._fill = None

        # Ditto for aligning
        if (self._align_h or self._align_v) and not_stretched:
            self._align_h = None
            self._align_v = None

        # The imaging back-end currently treats RGB == SRGB
        # Normalise greys
        if self._colorspace == 'srgb':
            self._colorspace = 'rgb'

        if self._colorspace == 'grey':
            self._colorspace = 'gray'

        # No overlay src, zero size or fully transparent == no overlay
        if self._overlay_src is None or self._overlay_opacity == 0 or self._overlay_size == 0:
            self._overlay_src = None
            self._overlay_pos = None
            self._overlay_size = None
            self._overlay_opacity = None

        # No ICC name == no ICC
        if self._icc_profile is None:
            self._icc_intent = None
            self._icc_bpc = None

    def _no_blank(self, strval):
        """
        Returns strval if it has a value, or None if strval is either None
        or an empty string.
        """
        return strval or None

    def _float_to_str(self, f):
        """
        Returns f as a string, without scientific notation.
        E.g. 0.00005 is returned as '0.00005' where a simple
             str(0.00005) would return '5e-05'.
        """
        s = ('%.5f' % f).rstrip('0')
        return (s + '0') if s.endswith('.') else s

    def _round_floats(self):
        """
        Rounds float attributes to a standard number of decimal places
        """
        if self._align_h is not None and len(self._align_h) > 8:
            self._align_h = self._align_h[:8]

        if self._align_v is not None and len(self._align_v) > 8:
            self._align_v = self._align_v[:8]

        if self._rotation is not None:
            self._rotation = round_crop(self._rotation)

        if self._top is not None:
            self._top = round_crop(self._top)

        if self._left is not None:
            self._left = round_crop(self._left)

        if self._bottom is not None:
            self._bottom = round_crop(self._bottom)

        if self._right is not None:
            self._right = round_crop(self._right)

        if self._overlay_size is not None:
            self._overlay_size = round_crop(self._overlay_size)

        if self._overlay_opacity is not None:
            self._overlay_opacity = round_crop(self._overlay_opacity)
