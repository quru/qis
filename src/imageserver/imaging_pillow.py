#
# Quru Image Server
#
# Document:      imaging_pillow.py
# Date started:  22 May 2018
# By:            Matt Fozard
# Purpose:       Provides an interface to the Pillow image processing library
# Requires:      The Python Pillow library (http://python-pillow.org)
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
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
#

import io
import math

_pillow_import_error = None
try:
    import PIL
    from PIL import Image, ImageColor, ExifTags, TiffTags, IptcImagePlugin
except Exception as e:
    _pillow_import_error = e


# TODO when not stripping - add extra save info for JPG, GIF, PNG, TIFF


class PillowBackend(object):
    """
    Implements a back-end for imaging.py using the Python Pillow library.
    """
    MAX_ICC_SIZE = 1048576 * 5

    def __init__(self, gs_path, temp_files_path, pdf_default_dpi):
        """
        Initialises the Pillow library. This function must be called once
        before the other functions can be used.

        See imaging.imaging_init() for a description of the parameters.
        An ImportError is raised if the Pillow library failed to load.
        """
        global _pillow_import_error
        if _pillow_import_error:
            raise ImportError("Failed to import Pillow: " + str(_pillow_import_error))

    def get_version_info(self):
        """
        Returns a string with the Pillow library version information.
        """
        return "Pillow version: " + PIL.__version__

    def adjust_image(
            self, image_data, data_type,
            page=1, iformat='jpg',
            new_width=0, new_height=0, size_auto_fit=False,
            align_h=None, align_v=None, rotation=0.0, flip=None,
            crop_top=0.0, crop_left=0.0, crop_bottom=1.0, crop_right=1.0, crop_auto_fit=False,
            fill_colour='#ffffff', rquality=3, cquality=75, sharpen=0,
            dpi=0, strip_info=False,
            overlay_data=None, overlay_size=1.0, overlay_pos=None, overlay_opacity=1.0,
            icc_profile=None, icc_intent=None, icc_bpc=False,
            colorspace=None, tile_spec=(0, 0)
        ):
        """
        Pillow implementation of imaging.adjust_image(),
        see the function documentation there for full details.

        This method may not support all the functionality of the ImageMagick version.
        """
        # Check for bad parameters
        if not image_data:
            raise ValueError('Image must be supplied')
        if align_h and len(align_h) > 16:
            raise ValueError('HAlign value too long')
        if align_v and len(align_v) > 16:
            raise ValueError('VAlign value too long')
        if flip and len(flip) > 1:
            raise ValueError('Flip value too long')
        if fill_colour and len(fill_colour) > 32:
            raise ValueError('Fill colour value too long')
        if iformat and len(iformat) > 4:
            raise ValueError('Format value too long')
        if overlay_pos and len(overlay_pos) > 32:
            raise ValueError('Overlay position value too long')
        if icc_profile and len(icc_profile) > PillowBackend.MAX_ICC_SIZE:
            raise ValueError('ICC profile too large')
        if icc_intent and len(icc_intent) > 10:
            raise ValueError('ICC rendering intent too long')        
        if tile_spec[0] > 0:
            grid_axis_len = int(math.sqrt(tile_spec[1]))
            if tile_spec[1] < 4 or tile_spec[1] != (grid_axis_len * grid_axis_len):
                raise ValueError('Tile grid size is not square, or is less than 4')

        # Read image data, blow up here if a bad image
        image = self._load_image_data(image_data, data_type)
        bufout = io.BytesIO()
        try:
            original_info = image.info
            original_info['mode'] = image.mode
            original_info['size'] = image.size

            # Adjust parameters to safe values (part 1)
            page = self._limit_number(page, 1, 999999)
            rotation = self._limit_number(rotation, -360.0, 360.0)
            crop_top = self._limit_number(crop_top, 0.0, 1.0)
            crop_left = self._limit_number(crop_left, 0.0, 1.0)
            crop_bottom = self._limit_number(crop_bottom, 0.0, 1.0)
            crop_right = self._limit_number(crop_right, 0.0, 1.0)
            if crop_bottom < crop_top:
                crop_bottom = crop_top
            if crop_right < crop_left:
                crop_right = crop_left
            rquality = self._limit_number(rquality, 1, 3)
            cquality = self._limit_number(cquality, 1, 100)
            sharpen = self._limit_number(sharpen, -500, 500)
            dpi = self._limit_number(dpi, 0, 32000)
            if tile_spec[0] > 0:
                tile_spec[0] = self._limit_number(tile_spec[0], 1, tile_spec[1])
            overlay_size = self._limit_number(overlay_size, 0.0, 1.0)
            overlay_opacity = self._limit_number(overlay_opacity, 0.0, 1.0)

            # Page selection - P3

            # #2321 Ensure no div by 0
            if 0 in image.size:
                raise ValueError('Image dimensions are zero')

            # Adjust parameters to safe values (part 2)
            # Prevent enlargements, using largest of width/height to allow for rotation.
            # If enabling enlargements, enforce some max value to prevent server attacks.
            max_dimension = max(image.size)
            new_width = self._limit_number(
                new_width, 0, image.width if rotation == 0.0 else max_dimension
            )
            new_height = self._limit_number(
                new_height, 0, image.height if rotation == 0.0 else max_dimension
            )

            # If the target format supports transparency and we need it,
            # upgrade the image to RGBA
            if fill_colour == 'none' or fill_colour == 'transparent':
                if self._supports_transparency(iformat):
                    if image.mode != 'LA' and image.mode != 'RGBA':
                        image = self._image_change_mode(
                            image,
                            'LA' if image.mode == 'L' else 'RGBA'
                        )
                else:
                    fill_colour = '#ffffff'

            # Set background colour, required for rotation or resizes that
            # change the overall aspect ratio
            try:
                if fill_colour == 'auto':
                    raise NotImplementedError('Auto fill is not yet implemented')
                elif fill_colour == 'none' or fill_colour == 'transparent':
                    fill_rgb = None
                elif fill_colour:
                    fill_rgb = ImageColor.getrgb(fill_colour)
                else:
                    fill_rgb = ImageColor.getrgb('#ffffff')
            except ValueError:
                raise ValueError('Invalid or unsupported fill colour')

            # The order of imaging operations is fixed, and defined in image_help.md#notes
            # (1) Flip
            if flip == 'h' or flip == 'v':
                image = self._image_flip(image, flip)
            # (2) Rotate
            if rotation:
                image = self._image_rotate(image, rotation, rquality, fill_rgb)
            # (3) Crop
            if (crop_top, crop_left, crop_bottom, crop_right) != (0.0, 0.0, 1.0, 1.0):
                image = self._image_crop(
                    image, crop_top, crop_left, crop_bottom, crop_right,
                    crop_auto_fit, new_width, new_height
                )
                # If auto-fill is enabled and we didn't rotate (i.e. we haven't used the
                # fill colour yet), work out a new fill colour, post-crop
                if fill_colour == 'auto' and not rotation:
                    raise NotImplementedError('Auto fill is not yet implemented')
            # (4) Resize
            if new_width != 0 or new_height != 0:
                image = self._image_resize(image, new_width, new_height, rquality)
            # (5) Overlay - P2
            # (6) Tile
            # (7) Apply ICC profile - P3
            # (8) Set colorspace - P3
            # (9) Strip TODO see jpeg save options for how to not strip

            # Return encoded image bytes
            image = self._set_pillow_save_mode(
                image, iformat, fill_rgb, original_info
            )
            save_opts = self._get_pillow_save_options(
                image, iformat, cquality, dpi, original_info
            )
            image.save(bufout, **save_opts)
            return bufout.getvalue()
        finally:
            image.close()
            bufout.close()

    def burst_pdf(self, pdf_data, dest_dir, dpi):
        """
        Pillow implementation of imaging.burst_pdf(),
        see the function documentation there for full details.

        This method may not support all the functionality of the ImageMagick version.
        """
        raise NotImplementedError(
            'PDF support is not currently implemented in the free version'
        )

    def get_image_profile_data(self, image_data, data_type):
        """
        Pillow implementation of imaging.get_image_profile_data(),
        see the function documentation there for full details.

        This method may not support all the functionality of the ImageMagick version.
        """
        image = self._load_image_data(image_data, data_type)
        try:
            return self._get_image_tags(image)
        finally:
            image.close()

    def get_image_dimensions(self, image_data, data_type):
        """
        Pillow implementation of imaging.get_image_dimensions(),
        see the function documentation there for full details.
        """
        image = self._load_image_data(image_data, data_type)
        try:
            return image.size
        finally:
            image.close()

    def _load_image_data(self, image_data, data_type):
        """
        Returns a Pillow Image from raw image file bytes. The data type should
        be the image's file extension to provide a decoding hint. The image is
        lazy loaded - the pixel data is not decoded until either something requires
        it or the load() method is called.
        The caller should call close() on the image after use.
        Raises a ValueError if the image type is not supported.
        """
        try:
            return Image.open(io.BytesIO(image_data))
        except IOError:
            raise ValueError("Invalid or unsupported image format")

    def _get_image_tags(self, image):
        """
        The back end of get_image_profile_data(),
        returning a list of tuples in the format expected by exif.py.
        """
        results = []
        # JpegImagePlugin and WebPImagePlugin
        try:
            results += self._tag_dict_to_tuplist(image._getexif(), 'exif', ExifTags.TAGS)
        except AttributeError:  # ._getexif
            pass
        # TiffImageplugin
        try:
            results += self._tag_dict_to_tuplist(image.tag, 'tiff', TiffTags.TAGS)
        except AttributeError:  # .tag
            pass
        # JpegImagePlugin and TiffImageplugin
        results += self._tag_dict_to_tuplist(
            self._fix_iptc_dict(IptcImagePlugin.getiptcinfo(image)),
            'iptc',
            IptcTags
        )
        # PNGImagePlugin - Pillow has no built-in support for reading XMP or EXIF data
        #                  from the headers. EXIF in PNG was only standardised in July 2017.
        #                  There is image.info['pnginfo'] but I haven't seen it present yet.
        # <nothing to do for PNG>
        results.sort()
        return results

    def _tag_dict_to_tuplist(self, tag_dict, key_type, key_dict):
        """
        Converts a Pillow tag dictionary to a list of tuples in the format
        expected by exif.py: [('exif', 'key', 'value'), ...]. Returns an empty
        list if the dictionary is None or empty or if no tags were recognised.
        """
        results = []
        if tag_dict:
            for k, v in tag_dict.items():
                key_name = key_dict.get(k)
                if key_name:
                    if key_name == "GPSInfo":
                        results += self._tag_dict_to_tuplist(v, 'exif', ExifTags.GPSTAGS)
                    else:
                        results.append(
                            (key_type, key_name, self._tag_value_to_string(v))
                        )
        return results

    def _tag_value_to_string(self, val):
        """
        Converts an EXIF/TIFF tag value from the Python type returned by Pillow
        into the string format required by exif.py. From the exif.py documentation:
        >
        > raw_string_val should be in format "str" for strings, "123" for numbers,
        > "10/50" for ratios, "1/2, 11/20" for a list of ratios,
        > and "83, 84, 82" for binary (this representing "STR")
        >
        """
        if isinstance(val, str):
            return val
        elif isinstance(val, bytes):
            return ', '.join([str(c) for c in val])
        elif isinstance(val, (int, float)):
            return str(val)
        elif isinstance(val, tuple) and len(val) == 1:
            return self._tag_value_to_string(val[0])
        elif isinstance(val, tuple) and len(val) == 2 and isinstance(val[0], int):
            return "%d/%d" % val
        elif isinstance(val, tuple):
            return ', '.join(self._tag_value_to_string(v) for v in val)
        else:
            # We don't know how to handle, but return something
            return str(val)

    def _fix_iptc_dict(self, tag_dict):
        """
        Given Pillow's IPTC dict in the format {(datatype, tagcode): b'value'},
        returns a new dict in the format {tagcode: 'value'} similar to the EXIF
        and TIFF dicts.
        """
        fixed_dict = {}
        if tag_dict:
            # Convert {(datatype, tagcode): value} to {tagcode:value}
            fixed_dict = {k[1]:v for k, v in tag_dict.items()}
            # Convert byte values to str and [byte, byte] to (str, str)
            for k, v in fixed_dict.items():
                if isinstance(v, bytes):
                    fixed_dict[k] = v.decode('utf8')
                elif isinstance(v, (tuple, list)) and v and isinstance(v[0], bytes):
                    fixed_dict[k] = tuple([vi.decode('utf8') for vi in v])
        return fixed_dict

    def _limit_number(self, val, min_val, max_val):
        """
        Returns val, or min_val or max_val if val is out of range.
        """
        if val < min_val:
            return min_val
        elif val > max_val:
            return max_val
        return val

    def _supports_transparency(self, format):
        """
        Returns whether the given file format supports transparency.
        """
        return self._get_pillow_format(format) in ['gif', 'png']

    def _set_pillow_save_mode(self, image, save_format, fill_rgb, original_info, auto_close=True):
        """
        Pillow by design raises an error if you try to save an image in an
        incompatible mode for the output format,
        e.g. https://github.com/python-pillow/Pillow/issues/2609
        so if required by the output format, this method copies and changes the
        mode of an image, returning the new copy.
        """
        convert = False
        save_format = self._get_pillow_format(save_format)
        # GIF requires P mode, plus transparency if we're in LA or RGBA mode
        if save_format == 'gif' and image.mode != 'P':
            if image.mode.endswith('A'):
                # Convert to P with transparency
                alpha_band = image.split()[-1]
                new_image = image.convert(
                    'P', dither=Image.FLOYDSTEINBERG, palette=Image.ADAPTIVE,
                    colors=255  # 0-254 leaving 255 for transparency
                )
                mask = Image.eval(alpha_band, lambda p: 255 if p <= 128 else 0)
                new_image.paste(255, mask)
                original_info['transparency'] = 255  # for _get_pillow_save_options()
                if auto_close:
                    image.close()
                return new_image
            else:
                # Plain convert to P
                return self._image_change_mode(image, 'P', auto_close=auto_close)
        # PNG supports 1, L, LA, P, RGB and RGBA
        if save_format == 'png' and image.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA'):
            convert = True
        # JPG supports L, RGB, and CMYK
        if save_format == 'jpeg' and image.mode not in ('L', 'RGB', 'CMYK'):
            convert = True
        # TIFF supports all sorts depending on the compression method,
        # so we'll try allowing through the superset of PNG + JPG
        if save_format == 'tiff' and image.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA', 'CMYK'):
            convert = True
        # Convert to RGB if required
        if convert:
            if image.mode.endswith('A'):
                # Convert transparency to the fill colour
                # See https://github.com/python-pillow/Pillow/issues/2609#issuecomment-313922483
                new_image = Image.new(image.mode[:-1], image.size, fill_rgb)
                new_image.paste(image, image.split()[-1])
                if auto_close:
                    image.close()
                return new_image
            else:
                # Plain convert to RGB
                return self._image_change_mode(image, 'RGB', auto_close=auto_close)
        # Otherwise return image unchanged
        return image

    def _get_pillow_save_options(self, image, format, quality, dpi, original_info):
        """
        Returns a dictionary of save options for an image plus desired image
        format, quality, and other file options.
        """
        save_opts = {}
        # Special case - handle progressive JPEG
        if format in ['pjpg', 'pjpeg']:
            format = 'jpeg'
            save_opts['progressive'] = True
        elif 'progression' in original_info:
            save_opts['progressive'] = original_info['progression']
        # Set final format
        save_opts['format'] = self._get_pillow_format(format)
        # Preserve transparency if we're in P, L, or RGB mode and it was there before
        if (not image.mode.endswith('A') and
            self._supports_transparency(save_opts['format']) and
            'transparency' in original_info):
            save_opts['transparency'] = original_info['transparency']
        # Set or preserve DPI
        if dpi > 0:
            save_opts['dpi'] = (dpi, dpi)
        elif 'dpi' in original_info:
            save_opts['dpi'] = original_info['dpi']
        # Set JPEG compression
        if save_opts['format'] in ['jpg', 'jpeg']:
            save_opts['quality'] = quality
        # Set PNG compression
        if save_opts['format'] == 'png':
            save_opts['compress_level'] = min(quality // 10, 9)
        # Set or preserve TIFF compression (it uses raw otherwise)
        if save_opts['format'] == 'tiff':
            save_opts['compression'] = original_info.get('compression', 'jpeg')
        return save_opts

    def _get_pillow_format(self, format):
        """
        Converts a file extension to a Pillow file format.
        Pillow is a bit picky with it's file format names.
        """
        format = format.lower()
        if format in ['jpg', 'jpeg', 'jpe', 'jfif', 'jif']:
            return 'jpeg'
        elif format in ['tiff', 'tif']:
            return 'tiff'
        else:
            return format

    def _get_pillow_resample(self, quality, rotating=False):
        """
        Returns a Pillow resampling filter from 1 (fastest) to 3 (best quality).
        """
        if quality == 1:
            return Image.BILINEAR if not rotating else Image.NEAREST
        elif quality == 2:
            return Image.BICUBIC if not rotating else Image.BILINEAR
        else:
            return Image.LANCZOS if not rotating else Image.BICUBIC

    def _auto_crop_fit(self, image, top_px, left_px, bottom_px, right_px,
                       target_width, target_height):
        """
        For the given image, cropped to the specified rectangle, and targetting
        an output size of target_width x target_height, widens the cropping rectangle
        either vertically or horizontally as far as possible, in order to reduce areas
        that would otherwise become background fill colour in the output image.

        In other words, an attempt is made to change the aspect ratio of the provided
        cropping rectangle so that it matches the aspect ratio of the final output image.

        Returns a tuple of the adjusted (top_px, left_px, bottom_px, right_px).
        """
        # #2321 Ensure we have a valid starting crop, prevent div by 0
        if right_px <= left_px or bottom_px <= top_px or not target_width or not target_height:
            return top_px, left_px, bottom_px, right_px

        cropped_width = right_px - left_px
        cropped_height = bottom_px - top_px
        target_aspect = target_width / target_height
        cropped_aspect = cropped_width / cropped_height

        if target_aspect < cropped_aspect:
            # The final resize would fit the requested crop by width,
            # see if we can adjust the crop to fill the height
            max_cropped_height = math.ceil(cropped_width / target_aspect)  # The crop height we need to get to the target aspect ratio
            want_height = max_cropped_height - cropped_height
            if want_height > 0:
                to_fill_height = want_height
                available_top = top_px
                available_bottom = image.height - bottom_px
                available_min = min(available_top, available_bottom)

                if available_top + available_bottom <= to_fill_height:
                    # We cannot reach max_cropped_height, the best we can do is use all height
                    top_px = 0
                    bottom_px = image.height
                else:
                    # We can reach max_cropped_height (there is room for all of to_fill_height)
                    if available_min * 2 >= to_fill_height:
                        # We can stretch the crop rectangle equally on both sides
                        top_px -= (to_fill_height // 2)
                        bottom_px += (to_fill_height // 2)
                    else:
                        # We require an uneven vertical stretch
                        if available_top < available_bottom:
                            top_px = 0
                            to_fill_height -= available_top
                            bottom_px += to_fill_height
                        else:
                            bottom_px = image.height
                            to_fill_height -= available_bottom
                            top_px -= to_fill_height
        else:
            # The final resize would fit the requested crop by height,
            # see if we can adjust the crop to fill the width
            max_cropped_width = math.ceil(cropped_height * target_aspect)  # The crop width we need to get to the target aspect ratio
            want_width = max_cropped_width - cropped_width
            if want_width > 0:
                to_fill_width = want_width
                available_left = left_px
                available_right = image.width - right_px
                available_min = min(available_left, available_right)

                if available_left + available_right <= to_fill_width:
                    # We cannot reach max_cropped_width, the best we can do is use all width
                    left_px = 0
                    right_px = image.width
                else:
                    # We can reach max_cropped_width (there is room for all of to_fill_width)
                    if available_min * 2 >= to_fill_width:
                        # We can stretch the crop rectangle equally on both sides
                        left_px -= (to_fill_width // 2)
                        right_px += (to_fill_width // 2)
                    else:
                        # We require an uneven horizontal stretch
                        if available_left < available_right:
                            left_px = 0
                            to_fill_width -= available_left
                            right_px += to_fill_width
                        else:
                            right_px = image.width
                            to_fill_width -= available_right
                            left_px -= to_fill_width

        return top_px, left_px, bottom_px, right_px

    def _image_change_mode(self, image, mode, auto_close=True):
        """
        Copies and changes the mode of an image, e.g. to 'RGBA',
        returning the new copy.
        """
        if mode == 'P':
            new_image = image.convert(mode, dither=Image.FLOYDSTEINBERG, palette=Image.ADAPTIVE)
        else:
            new_image = image.convert(mode)
        if auto_close:
            image.close()
        return new_image

    def _image_flip(self, image, flip, auto_close=True):
        """
        Copies and flips an image left to right ('h') or top to bottom ('v'),
        returning the new copy.
        """
        if flip == 'h':
            new_image = image.transpose(Image.FLIP_LEFT_RIGHT)
        else:
            new_image = image.transpose(Image.FLIP_TOP_BOTTOM)
        if auto_close:
            image.close()
        return new_image

    def _image_rotate(self, image, angle, quality, fill_rgb, auto_close=True):
        """
        Copies and rotates an image clockwise, returning the new copy.
        """
        new_image = image.rotate(
            angle * -1,
            self._get_pillow_resample(quality, rotating=True),
            expand=True,
            fillcolor=fill_rgb  # Requires Pillow 5.2
        )
        if auto_close:
            image.close()
        return new_image

    def _image_crop(self, image, crop_top, crop_left, crop_bottom, crop_right,
                    crop_auto_fit, target_width, target_height, auto_close=True):
        """
        Copies and crops an image, returning the new copy.
        If target_width is set and target_height is set and auto-fit is True, the
        requested crop will be expanded in one direction to better match the target size.
        """
        # Get the cropping pixels
        top_px = math.ceil(image.height * crop_top)
        left_px = math.ceil(image.width * crop_left)
        bottom_px = math.ceil(image.height * crop_bottom)
        right_px = math.ceil(image.width * crop_right)
        # Does that actually produce a crop?
        if top_px > 0 or left_px > 0 or bottom_px < image.height or right_px < image.width:
            if crop_auto_fit and target_width and target_height:
                # Auto crop fit function
                top_px, left_px, bottom_px, right_px = self._auto_crop_fit(
                    image,
                    top_px, left_px, bottom_px, right_px,
                    target_width, target_height
                )
            if right_px > left_px and bottom_px > top_px:
                # Crop to the numbers
                new_image = image.crop((left_px, top_px, right_px, bottom_px))
                if auto_close:
                    image.close()
                return new_image
        # Return unchanged image
        return image

    def _image_resize(self, image, width, height, quality, auto_close=True):
        """
        Resizes an image, returning a resized copy.
        The quality number can be from 1 (fastest) to 3 (best quality).
        The image will not be resized beyond its original size.
        """
        # TODO Constrain size
        # TODO Test for aspect changes
        # TODO Do we need to gamma correct?
        new_image = image.resize(
            (width, height),
            resample=self._get_pillow_resample(quality)
        )
        if auto_close:
            image.close()
        return new_image


# A mapping of Pillow's IPTC tag codes to the exif.py tag names
IptcTags = {
    5: 'ObjectName',
    7: 'EditStatus',
    8: 'EditorialUpdate',
    10: 'Urgency',
    12: 'SubjectReference',
    15: 'Category',
    20: 'SupplementalCategories',
    22: 'FixtureIdentifier',
    25: 'Keywords',
    26: 'ContentLocationCode',
    27: 'ContentLocationName',
    30: 'ReleaseDate',
    35: 'ReleaseTime',
    37: 'ExpirationDate',
    38: 'ExpirationTime',
    40: 'SpecialInstructions',
    42: 'ActionAdvised',
    45: 'ReferenceService',
    47: 'ReferenceDate',
    50: 'ReferenceNumber',
    55: 'DateCreated',
    60: 'TimeCreated',
    62: 'DigitalCreationDate',
    63: 'DigitalCreationTime',
    65: 'OriginatingProgram',
    70: 'ProgramVersion',
    75: 'ObjectCycle',
    80: 'By-line',
    85: 'By-lineTitle',
    90: 'City',
    92: 'Sub-location',
    95: 'Province-State',
    100: 'Country-PrimaryLocationCode',
    101: 'Country-PrimaryLocationName',
    103: 'OriginalTransmissionReference',
    105: 'Headline',
    110: 'Credit',
    115: 'Source',
    116: 'CopyrightNotice',
    118: 'Contact',
    120: 'Caption-Abstract',
    121: 'LocalCaption',
    122: 'Writer-Editor',
    125: 'RasterizedCaption',
    130: 'ImageType',
    131: 'ImageOrientation',
    135: 'LanguageIdentifier',
}
