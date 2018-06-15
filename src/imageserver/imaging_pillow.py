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
    from PIL import Image, ImageCms, ImageColor, ExifTags, TiffTags, IptcImagePlugin
except Exception as e:
    _pillow_import_error = e


class PillowBackend(object):
    """
    Implements a back-end for imaging.py using the Python Pillow library.
    """
    MAX_ICC_SIZE = 1048576 * 5

    # Keys in image.info that are important to preserve through the processing chain
    METADATA_INFO_KEYS = (
        'icc_profile', 'exif',                            # Generic
        'gamma',                                          # PNG
        'description', 'software', 'artist', 'copyright'  # TIFF
    )

    def __init__(self, gs_path, temp_files_path, pdf_default_dpi):
        """
        Initialises the Pillow library. This function must be called once
        before the other functions can be used.

        See imaging.init() for a description of the parameters.
        An ImportError is raised if the Pillow library failed to load.
        """
        global _pillow_import_error
        if _pillow_import_error:
            raise ImportError("Failed to import Pillow: " + str(_pillow_import_error))
        try:
            # Cache some useful ICC profiles
            linear_file = io.BytesIO(LINEAR_RGB_ICC_PROFILE)
            srgb_file = io.BytesIO(SRGB_ICC_PROFILE)
            self.linear_rgb_profile = ImageCms.ImageCmsProfile(linear_file)
            self.srgb_profile = ImageCms.ImageCmsProfile(srgb_file)

            # Pre-calculate Linear RGB <--> sRGB transformations
            self._transform_rgb_srgb_to_linear = ImageCms.buildTransform(
                self.srgb_profile, self.linear_rgb_profile, 'RGB', 'RGB'
            )
            self._transform_rgb_linear_to_srgb = ImageCms.buildTransform(
                self.linear_rgb_profile, self.srgb_profile, 'RGB', 'RGB'
            )
            self._transform_rgba_srgb_to_linear = ImageCms.buildTransform(
                self.srgb_profile, self.linear_rgb_profile, 'RGBA', 'RGBA'
            )
            self._transform_rgba_linear_to_srgb = ImageCms.buildTransform(
                self.linear_rgb_profile, self.srgb_profile, 'RGBA', 'RGBA'
            )
        finally:
            linear_file.close()
            srgb_file.close()

    def get_version_info(self):
        """
        Returns a string with the Pillow library version information.
        """
        return "Pillow version: " + PIL.__version__

    def supported_file_types(self):
        """
        Returns which image types are supported by the Pillow back-end.
        See the function documentation for imaging.supported_file_types() for
        more information.
        """
        return [
            'gif',
            'jpg', 'jpeg', 'jpe', 'jfif', 'jif', 'pjpg', 'pjpeg',
            'png', 'tif', 'tiff'
        ]

    def supported_operations(self):
        """
        Returns which imaging operations are supported by the Pillow back-end.
        See the function documentation for imaging.supported_operations() and
        imaging.adjust_image() for more information.
        """
        return {
            'page': False,
            'width': True,
            'height': True,
            'size_fit': True,
            'align_h': False,
            'align_v': False,
            'rotation': True,
            'flip': True,
            'sharpen': False,
            'dpi_x': True,
            'dpi_y': True,
            'fill': True,
            'top': True,
            'left': True,
            'bottom': True,
            'right': True,
            'crop_fit': True,
            'overlay_data': False,
            'overlay_size': False,
            'overlay_pos': False,
            'overlay_opacity': False,
            'icc_data': False,
            'icc_intent': False,
            'icc_bpc': False,
            'tile': True,
            'colorspace': False,
            'format': True,
            'quality': True,
            'resize_type': True,
            'resize_gamma': True,
            'strip': True
        }

    def adjust_image(self, image_data, data_type, image_spec):
        """
        Pillow implementation of imaging.adjust_image(),
        see the function documentation there for full details.

        This method does not support all the functionality of the ImageMagick version.
        """
        if not image_data:
            raise ValueError('Image must be supplied')

        # Check for bad parameters, set default values for missing parameters
        self._validate_image_spec(image_spec)

        # Read image data, blow up here if a bad image
        image = self._load_image_data(image_data, data_type)
        bufout = io.BytesIO()
        try:
            # Keep a copy of the original image's info
            original_info = image.info
            original_info['mode'] = image.mode
            original_info['size'] = image.size
            # Special case for TIFF
            if hasattr(image, 'tag_v2'):
                original_info.update(self._get_tiff_info_dict(image))

            # Page selection - P3

            # #2321 Ensure no div by 0
            if 0 in image.size:
                raise ValueError('Image dimensions are zero')

            # Prevent enlargements, using largest of width/height to allow for rotation.
            # If enabling enlargements, enforce some max value to prevent server attacks.
            max_dimension = max(image.size)
            new_width = _limit_number(
                image_spec['width'],
                0,
                image.width if image_spec['rotation'] == 0.0 else max_dimension
            )
            new_height = _limit_number(
                image_spec['height'],
                0,
                image.height if image_spec['rotation'] == 0.0 else max_dimension
            )

            # If the target format supports transparency and we need it,
            # upgrade the image to RGBA
            if image_spec['fill'] == 'none' or image_spec['fill'] == 'transparent':
                if self._supports_transparency(image_spec['format']):
                    if image.mode != 'LA' and image.mode != 'RGBA':
                        image = self._image_change_mode(
                            image,
                            'LA' if image.mode == 'L' else 'RGBA'
                        )
                        self._restore_pillow_info(image, original_info)
                else:
                    image_spec['fill'] = '#ffffff'

            # Set background colour, required for rotation or resizes that
            # change the overall aspect ratio
            try:
                if image_spec['fill'] == 'auto':
                    fill_rgb = self._auto_fill_colour(image)
                elif image_spec['fill'] == 'none' or image_spec['fill'] == 'transparent':
                    fill_rgb = None
                elif image_spec['fill']:
                    fill_rgb = ImageColor.getrgb(image_spec['fill'])
                else:
                    fill_rgb = ImageColor.getrgb('#ffffff')
            except ValueError:
                raise ValueError('Invalid or unsupported fill colour')

            # The order of imaging operations is fixed, and defined in image_help.md#notes
            # (1) Flip
            if image_spec['flip'] == 'h' or image_spec['flip'] == 'v':
                image = self._image_flip(image, image_spec['flip'])
                self._restore_pillow_info(image, original_info)
            # (2) Rotate
            if image_spec['rotation']:
                image = self._image_rotate(
                    image,
                    image_spec['rotation'],
                    image_spec['resize_type'], fill_rgb
                )
                self._restore_pillow_info(image, original_info)
            # (3) Crop
            if (image_spec['top'], image_spec['left'], image_spec['bottom'], image_spec['right']) != (0.0, 0.0, 1.0, 1.0):
                image = self._image_crop(
                    image,
                    image_spec['top'], image_spec['left'],
                    image_spec['bottom'], image_spec['right'],
                    image_spec['crop_fit'], new_width, new_height
                )
                self._restore_pillow_info(image, original_info)
                # If auto-fill is enabled and we didn't rotate
                # (i.e. we haven't filled yet), work out a new fill colour, post-crop
                if image_spec['fill'] == 'auto' and not image_spec['rotation']:
                    fill_rgb = self._auto_fill_colour(image)
            # (4) Resize
            if new_width != 0 or new_height != 0:
                image = self._image_resize(
                    image,
                    new_width, new_height,
                    image_spec['size_fit'],
                    image_spec['align_h'], image_spec['align_v'],
                    fill_rgb,
                    image_spec['resize_type'],
                    image_spec['resize_gamma']
                )
                self._restore_pillow_info(image, original_info)
            # (5) Blur/sharpen - P2
            # (6) Overlay - P2
            # (7) Tile
            if image_spec['tile'] >= (1, 4):
                image = self._image_tile(image, image_spec['tile'])
                self._restore_pillow_info(image, original_info)
            # (8) Apply ICC profile - P3
            # (9) Set colorspace - P3
            # (10) Strip (preparation, the strip is done by _get_pillow_save_options)
            if image_spec['strip']:
                image = self._image_pre_strip(image)
                self._restore_pillow_info(image, original_info)

            # Check/set the image mode for the output image format
            image = self._set_pillow_save_mode(image, image_spec['format'], fill_rgb)
            if 'transparency' in image.info:
                original_info['transparency'] = image.info['transparency']
            self._restore_pillow_info(image, original_info)
            # Get the save parameters for the output image format
            save_opts = self._get_pillow_save_options(
                image,
                image_spec['format'], image_spec['quality'],
                image_spec['dpi_x'], image_spec['dpi_y'],
                original_info, image_spec['strip']
            )
            # Encode the image bytes and return encoded bytes
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

    def _validate_image_spec(self, image_spec):
        """
        Reads and validates the imaging parameters from a Python dictionary as
        described at imaging.adjust_image(). The dictionary is updated in-place
        with default values for any missing parameters.
        Raises a ValueError if any of the parameters have invalid values.
        """
        # Remove None entries from dict
        image_spec = {k: v for k, v in image_spec.items() if v is not None}
        # Set default values / adjust parameters to safe values
        image_spec['page'] = _limit_number(image_spec.get('page', 1), 1, 999999)
        image_spec['width'] = image_spec.get('width', 0)
        image_spec['height'] = image_spec.get('height', 0)
        image_spec['size_fit'] = image_spec.get('size_fit', False)
        image_spec['align_h'] = image_spec.get('align_h', '')
        image_spec['align_v'] = image_spec.get('align_v', '')
        image_spec['rotation'] = _limit_number(image_spec.get('rotation', 0.0), -360.0, 360.0)
        image_spec['flip'] = image_spec.get('flip', '')
        image_spec['sharpen'] = _limit_number(image_spec.get('sharpen', 0), -500, 500)
        image_spec['dpi_x'] = _limit_number(image_spec.get('dpi_x', 0), 0, 32000)
        image_spec['dpi_y'] = _limit_number(image_spec.get('dpi_y', 0), 0, 32000)
        image_spec['fill'] = image_spec.get('fill', '#ffffff')
        image_spec['top'] = _limit_number(image_spec.get('top', 0.0), 0.0, 1.0)
        image_spec['left'] = _limit_number(image_spec.get('left', 0.0), 0.0, 1.0)
        image_spec['bottom'] = _limit_number(image_spec.get('bottom', 1.0), 0.0, 1.0)
        image_spec['right'] = _limit_number(image_spec.get('right', 1.0), 0.0, 1.0)
        image_spec['crop_fit'] = image_spec.get('crop_fit', False)
        image_spec['overlay_data'] = image_spec.get('overlay_data', None)
        image_spec['overlay_size'] = _limit_number(image_spec.get('overlay_size', 1.0), 0.0, 1.0)
        image_spec['overlay_pos'] = image_spec.get('overlay_pos', '')
        image_spec['overlay_opacity'] = _limit_number(image_spec.get('overlay_opacity', 1.0), 0.0, 1.0)
        image_spec['icc_data'] = image_spec.get('icc_data', None)
        image_spec['icc_intent'] = image_spec.get('icc_intent', '')
        image_spec['icc_bpc'] = image_spec.get('icc_bpc', False)
        image_spec['tile'] = image_spec.get('tile', (0, 0))
        image_spec['colorspace'] = image_spec.get('colorspace', '')
        image_spec['format'] = image_spec.get('format', 'jpg')
        image_spec['quality'] = _limit_number(image_spec.get('quality', 80), 1, 100)
        image_spec['resize_type'] = _limit_number(image_spec.get('resize_type', 3), 1, 3)
        image_spec['resize_gamma'] = image_spec.get('resize_gamma', True)
        image_spec['strip'] = image_spec.get('strip', False)

        tile_spec = image_spec['tile']
        if tile_spec[0] > 0:
            image_spec['tile'] = (_limit_number(tile_spec[0], 1, tile_spec[1]), tile_spec[1])
        if image_spec['bottom'] < image_spec['top']:
            image_spec['bottom'] = image_spec['top']
        if image_spec['right'] < image_spec['left']:
            image_spec['right'] = image_spec['left']

        # Check for parameter values that should raise an error
        if len(image_spec['align_h']) > 16:
            raise ValueError('HAlign value too long')
        if len(image_spec['align_v']) > 16:
            raise ValueError('VAlign value too long')
        if len(image_spec['flip']) > 1:
            raise ValueError('Flip value too long')
        if len(image_spec['fill']) > 32:
            raise ValueError('Fill colour value too long')
        if len(image_spec['format']) > 4:
            raise ValueError('Format value too long')
        if len(image_spec['overlay_pos']) > 32:
            raise ValueError('Overlay position value too long')
        if image_spec['icc_data'] and len(image_spec['icc_data']) > PillowBackend.MAX_ICC_SIZE:
            raise ValueError('ICC profile too large')
        if len(image_spec['icc_intent']) > 10:
            raise ValueError('ICC rendering intent too long')
        tile_spec = image_spec['tile']
        if tile_spec[0] > 0:
            grid_axis_len = int(math.sqrt(tile_spec[1]))
            if tile_spec[1] < 4 or tile_spec[1] != (grid_axis_len * grid_axis_len):
                raise ValueError('Tile grid size is not square, or is less than 4')

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
            results += self._tag_dict_to_tuplist(image.tag_v2, 'tiff', TiffTagsGetter)
        except AttributeError:  # .tag_v2
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
            fixed_dict = {k[1]: v for k, v in tag_dict.items()}
            # Convert byte values to str and [byte, byte] to (str, str)
            for k, v in fixed_dict.items():
                if isinstance(v, bytes):
                    fixed_dict[k] = v.decode('utf8')
                elif isinstance(v, (tuple, list)) and v and isinstance(v[0], bytes):
                    fixed_dict[k] = tuple([vi.decode('utf8') for vi in v])
        return fixed_dict

    def _get_tiff_info_dict(self, image):
        """
        Pillow has a 'tiffinfo' parameter for setting TIFF tags when saving, but
        using it causes errors with the libtiff back end. Luckily the TIFF plugin
        also supports separate save parameters for the most common info fields.
        This function extracts the tags that can be supplied as separate save
        parameters, and returns them as a name/value dictionary, e.g.
        {'software': 'Adobe Photoshop'}
        """
        d = {}
        skip_tags = ('icc_profile', 'exif')
        tag_dict = {k.lower(): v for k, v in image.tag_v2.named().items()}
        for tag in tag_dict:
            if (tag in PillowBackend.METADATA_INFO_KEYS) and (tag not in skip_tags):
                d[tag] = tag_dict[tag]
        return d

    def _supports_transparency(self, format):
        """
        Returns whether the given file format supports transparency.
        """
        return self._get_pillow_format(format) in ['gif', 'png']

    def _supports_icc_profile(self, format):
        """
        Returns whether the given file format supports an embedded ICC profile.
        """
        return self._get_pillow_format(format) in ['jpeg', 'png']

    def _restore_pillow_info(self, image, info_dict, info_keys=None):
        """
        Most of the Pillow operations return a new Image that is missing the info
        attributes of the input image. This utility copies one or more info
        attributes from info_dict into image. The info_keys can be an iterable of
        key names to copy from info_dict, or if left blank it defaults to
        PillowBackend.METADATA_INFO_KEYS. Keys that do not exist in info_dict are
        silently ignored.
        """
        if not info_keys:
            info_keys = PillowBackend.METADATA_INFO_KEYS
        elif isinstance(info_keys, str):
            info_keys = [info_keys]

        for key in info_keys:
            if key in info_dict:
                image.info[key] = info_dict[key]

    def _set_pillow_save_mode(self, image, save_format, fill_rgb, auto_close=True):
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
                new_image.info['transparency'] = 255
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

    def _get_pillow_save_options(self, image, format, quality, dpi_x, dpi_y,
                                 original_info, strip_info):
        """
        Returns a dictionary of the save options for an image in the desired file
        format, e.g. compression level, dpi, and other format-specific options.
        When strip_info is True, some metadata (e.g. EXIF tags) and color profiles
        are removed from the image info. When strip_info is False, this metadata
        is copied to the returned save options, as required by some image plugins.
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
        if dpi_x and dpi_y:
            save_opts['dpi'] = (dpi_x, dpi_y)
            save_opts['resolution'] = (dpi_x, dpi_y)
            save_opts['resolution_unit'] = 'inch'
        else:
            for key in ('dpi', 'resolution', 'resolution_unit'):
                if key in original_info:
                    save_opts[key] = original_info[key]
        # Set JPEG compression
        if save_opts['format'] in ['jpg', 'jpeg']:
            save_opts['quality'] = quality
        # Set PNG compression
        if save_opts['format'] == 'png':
            save_opts['compress_level'] = min(quality // 10, 9)
        # Set or preserve TIFF compression (it uses raw otherwise)
        if save_opts['format'] == 'tiff':
            save_opts['compression'] = original_info.get('compression', 'jpeg')
        # Preserve or remove metadata
        if strip_info:
            # Remove info from image, don't add to save_opts
            for key in PillowBackend.METADATA_INFO_KEYS:
                if key in image.info:
                    del image.info[key]
        else:
            # Keep info by adding it to save_opts (some Pillow plugins keep the
            # image info, some require it to be copied to save parameters)
            for key in PillowBackend.METADATA_INFO_KEYS:
                if key in image.info:
                    save_opts[key] = image.info[key]
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

    def _auto_fill_colour(self, image):
        """
        Calculates and returns a Pillow fill colour for an image.
        """
        # Auto-fill colour is P2, so for now just return white
        return ImageColor.getrgb('#ffffff')

    def _get_image_align_offset(self, image, target_width, target_height, align_h, align_v):
        """
        Returns the (x, y) position (from the target's top left) to place an image
        inside a target rectangle, based on the alignment parameters.
        The alignment values are as described at imaging.adjust_image().
        """
        # Image-in-image positioning is P3, so for now just centre it
        offset_x = (target_width - image.width) // 2
        offset_y = (target_height - image.height) // 2
        # Do not allow the image to get chopped off when aligning it
        offset_x = max(0, min(offset_x, target_width - image.width))
        offset_y = max(0, min(offset_y, target_height - image.height))
        return offset_x, offset_y

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

    def _image_pre_strip(self, image, auto_close=True):
        """
        For an image that is going to be "stripped", performs any image
        pre-processing required, returning either the same image unchanged
        or a processed copy of it.
        """
        # For RGB images that have a non-sRGB colour profile (e.g. Nikon RGB)
        # we mess up the colours by simply stripping it. If we convert to sRGB
        # first, the result is much better, sometimes visually identical. For
        # CMYK images it is documented that stripping them alters the colours,
        # and there is no default/fallback profile.
        if image.mode.startswith('RGB') and 'icc_profile' in image.info:
            if image.info['icc_profile'] != SRGB_ICC_PROFILE:
                builtin_profile = ImageCms.ImageCmsProfile(io.BytesIO(image.info['icc_profile']))
                new_image = ImageCms.profileToProfile(image, builtin_profile, self.srgb_profile)
                if auto_close:
                    image.close()
                return new_image
        return image

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

    def _image_resize_bare(self, image, width, height, quality, gamma_correct, auto_close=True):
        """
        Resizes an image, returning a resized copy.
        The quality number can be from 1 (fastest) to 3 (best quality).
        The gamma correction flag controls whether sRGB images are gamma corrected
        during the resize (giving a better quality image but very slow processing).
        """
        use_image = image
        builtin_profile = None
        # Use gamma correction when resizing sRGB images - http://www.4p8.com/eric.brasseur/gamma.html
        # Since Pillow does not have any colorspace awareness, we'll assume that
        # anything in "RGB" mode without an embedded profile is actually sRGB.
        # This topic is discussed at https://github.com/python-pillow/Pillow/issues/1604
        do_gamma_correct = image.mode.startswith('RGB') and gamma_correct
        if do_gamma_correct:
            if 'icc_profile' in image.info:
                builtin_profile = ImageCms.ImageCmsProfile(io.BytesIO(image.info['icc_profile']))
                use_image = ImageCms.profileToProfile(image, builtin_profile, self.linear_rgb_profile)
            else:
                transform = self._transform_rgba_srgb_to_linear if image.mode.endswith('A') else \
                            self._transform_rgb_srgb_to_linear
                use_image = ImageCms.applyTransform(image, transform)
        # Actual resize here
        new_image = use_image.resize(
            (width, height),
            resample=self._get_pillow_resample(quality)
        )
        if do_gamma_correct:
            if builtin_profile:
                new_image = ImageCms.profileToProfile(new_image, self.linear_rgb_profile, builtin_profile)
            else:
                transform = self._transform_rgba_linear_to_srgb if new_image.mode.endswith('A') else \
                            self._transform_rgb_linear_to_srgb
                new_image = ImageCms.applyTransform(new_image, transform)
                # Pillow attaches the sRGB profile, but as we arrived here without one...
                if 'icc_profile' in new_image.info:
                    del new_image.info['icc_profile']
        if auto_close:
            image.close()
        return new_image

    def _image_resize(self, image, width, height, size_auto_fit,
                      align_h, align_v, fill_rgb, quality, gamma_correct,
                      auto_close=True):
        """
        Resizes an image, returning a resized copy.
        Width or height can be 0 to use the image's original width or height.
        The image will not be resized beyond its original size.

        If the width and height ratio do not match the image's aspect ratio and
        when size_auto_fit is false, the image will be returned at the requested
        size, with the resized image centred within it, surrounded by the fill
        colour. If size_auto_fit is true, either the width or height will be
        reduced so that there is no fill (and the requested size then is not
        respected).

        The quality number can be from 1 (fastest) to 3 (best quality).
        The gamma correction flag controls whether sRGB images are gamma corrected
        during the resize (giving a better quality image but very slow processing).
        """
        cur_aspect = image.width / image.height
        resize_canvas = False

        # Determine the final image dimensions
        if width == 0 and height == 0:
            # Keep the old dimensions
            width = image.width
            height = image.height
        elif width == 0 or height == 0:
            # Auto-resize based on the one dimension specified
            if width == 0:
                width = math.ceil(cur_aspect * height)
            if height == 0:
                height = math.ceil(width / cur_aspect)
        else:
            # Both a width and a height are specified
            if size_auto_fit:
                # Auto-adjust the requested canvas size to best fit the image
                max_height = height
                # Try first to resize image for the requested width
                height = math.ceil(width / cur_aspect)
                if height > max_height:
                    # Image would be too tall, we need to resize for the requested height instead
                    height = max_height
                    width = math.ceil(height * cur_aspect)
            else:
                # Use the requested canvas size, and best fit the image within it
                resize_canvas = True

        # At this point, width and height contain the final image dimensions
        new_image = None
        if not resize_canvas:
            # Plain image resize
            if width != image.width or height != image.height:
                new_image = self._image_resize_bare(
                    image, width, height, quality, gamma_correct, auto_close=False
                )
        else:
            canvas_width = width
            canvas_height = height
            canvas_aspect = canvas_width / canvas_height

            # Determine how the image should fit into the new canvas
            if canvas_aspect < cur_aspect:
                width = canvas_width
                height = math.ceil(width / cur_aspect)
            else:
                height = canvas_height
                width = math.ceil(height * cur_aspect)

            # Handle float rounding, prevent single-side 1px canvas borders
            if abs(width - canvas_width) == 1:
                width = canvas_width
            if abs(height - canvas_height) == 1:
                height = canvas_height

            # First perform plain image resize
            if width != image.width or height != image.height:
                new_image = self._image_resize_bare(
                    image, width, height, quality, gamma_correct, auto_close=False
                )

            # Then adjust the canvas if required
            if width != canvas_width or height != canvas_height:
                canvas_image = Image.new(image.mode, (canvas_width, canvas_height), fill_rgb)
                canvas_image.paste(
                    new_image,
                    self._get_image_align_offset(
                        new_image, canvas_width, canvas_height, align_h, align_v
                    )
                )
                new_image = canvas_image

        if new_image is None:
            return image
        if auto_close:
            image.close()
        return new_image

    def _image_tile(self, image, tile_spec, auto_close=True):
        """
        Copies and crops an image into tiles, returning the new copy/tile.
        The tile spec should be (tile number, grid size), where the grid size
        is a square (2*2, 3*3, 4*4, etc) and the tile number is between 1 and
        the grid size. 1 is the top left tile, the last is bottom right.
        When the image length cannot be divided exactly, some tiles may need to
        be larger than others, but this will always be applied to the
        right/bottom-most strip of tiles so that all strips fit together correctly
        from the left/top.
        """
        grid_axis_len = int(math.sqrt(tile_spec[1]))
        # Get 0-based X,Y coords for the tile number in the grid
        div = tile_spec[0] // grid_axis_len
        rem = tile_spec[0] % grid_axis_len
        tile_x0 = (rem - 1) if rem != 0 else (grid_axis_len - 1)
        tile_y0 = div if rem != 0 else (div - 1)

        # Get tile size
        tile_width = image.width // grid_axis_len
        tile_height = image.height // grid_axis_len
        tile_width_extra = image.width % grid_axis_len
        tile_height_extra = image.height % grid_axis_len

        # Get crop position
        left_px = tile_x0 * tile_width
        top_px = tile_y0 * tile_height

        # Adjust tile size for inexact division if this is a right/bottom tile
        if tile_x0 == (grid_axis_len - 1):
            tile_width += tile_width_extra
        if tile_y0 == (grid_axis_len - 1):
            tile_height += tile_height_extra

        # then crop to get the tile
        new_image = image.crop((left_px, top_px, left_px + tile_width, top_px + tile_height))
        if auto_close:
            image.close()
        return new_image


class TiffTagsGetter(object):
    """
    Provides a bare-minimum compatibility layer for converting a call to
    self.get(tag_number) into a call to TiffTags.lookup(tag_number).name.

    This allows the caller to have a single interface that behaves like
    "TiffTags.TAGS.get(tag_number)" (v1 interface) while also searching the
    TiffTags v2 interface, which returns a different data type.
    """
    @staticmethod
    def get(tag_number):
        taginfo = TiffTags.lookup(tag_number)
        return None if taginfo.name == 'unknown' else taginfo.name


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

# sRGB ICC profile
SRGB_ICC_PROFILE = (b'\x00\x00\x0c\x48\x4c\x69\x6e\x6f\x02\x10\x00\x00\x6d\x6e\x74\x72\x52\x47\x42\x20\x58\x59'
                    b'\x5a\x20\x07\xce\x00\x02\x00\x09\x00\x06\x00\x31\x00\x00\x61\x63\x73\x70\x4d\x53\x46\x54'
                    b'\x00\x00\x00\x00\x49\x45\x43\x20\x73\x52\x47\x42\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\xf6\xd6\x00\x01\x00\x00\x00\x00\xd3\x2d\x48\x50\x20\x20\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x11'
                    b'\x63\x70\x72\x74\x00\x00\x01\x50\x00\x00\x00\x33\x64\x65\x73\x63\x00\x00\x01\x84\x00\x00'
                    b'\x00\x6c\x77\x74\x70\x74\x00\x00\x01\xf0\x00\x00\x00\x14\x62\x6b\x70\x74\x00\x00\x02\x04'
                    b'\x00\x00\x00\x14\x72\x58\x59\x5a\x00\x00\x02\x18\x00\x00\x00\x14\x67\x58\x59\x5a\x00\x00'
                    b'\x02\x2c\x00\x00\x00\x14\x62\x58\x59\x5a\x00\x00\x02\x40\x00\x00\x00\x14\x64\x6d\x6e\x64'
                    b'\x00\x00\x02\x54\x00\x00\x00\x70\x64\x6d\x64\x64\x00\x00\x02\xc4\x00\x00\x00\x88\x76\x75'
                    b'\x65\x64\x00\x00\x03\x4c\x00\x00\x00\x86\x76\x69\x65\x77\x00\x00\x03\xd4\x00\x00\x00\x24'
                    b'\x6c\x75\x6d\x69\x00\x00\x03\xf8\x00\x00\x00\x14\x6d\x65\x61\x73\x00\x00\x04\x0c\x00\x00'
                    b'\x00\x24\x74\x65\x63\x68\x00\x00\x04\x30\x00\x00\x00\x0c\x72\x54\x52\x43\x00\x00\x04\x3c'
                    b'\x00\x00\x08\x0c\x67\x54\x52\x43\x00\x00\x04\x3c\x00\x00\x08\x0c\x62\x54\x52\x43\x00\x00'
                    b'\x04\x3c\x00\x00\x08\x0c\x74\x65\x78\x74\x00\x00\x00\x00\x43\x6f\x70\x79\x72\x69\x67\x68'
                    b'\x74\x20\x28\x63\x29\x20\x31\x39\x39\x38\x20\x48\x65\x77\x6c\x65\x74\x74\x2d\x50\x61\x63'
                    b'\x6b\x61\x72\x64\x20\x43\x6f\x6d\x70\x61\x6e\x79\x00\x00\x64\x65\x73\x63\x00\x00\x00\x00'
                    b'\x00\x00\x00\x12\x73\x52\x47\x42\x20\x49\x45\x43\x36\x31\x39\x36\x36\x2d\x32\x2e\x31\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x12\x73\x52\x47\x42\x20\x49\x45\x43\x36\x31\x39'
                    b'\x36\x36\x2d\x32\x2e\x31\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x58\x59\x5a\x20\x00\x00\x00\x00\x00\x00'
                    b'\xf3\x51\x00\x01\x00\x00\x00\x01\x16\xcc\x58\x59\x5a\x20\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x58\x59\x5a\x20\x00\x00\x00\x00\x00\x00\x6f\xa2\x00\x00'
                    b'\x38\xf5\x00\x00\x03\x90\x58\x59\x5a\x20\x00\x00\x00\x00\x00\x00\x62\x99\x00\x00\xb7\x85'
                    b'\x00\x00\x18\xda\x58\x59\x5a\x20\x00\x00\x00\x00\x00\x00\x24\xa0\x00\x00\x0f\x84\x00\x00'
                    b'\xb6\xcf\x64\x65\x73\x63\x00\x00\x00\x00\x00\x00\x00\x16\x49\x45\x43\x20\x68\x74\x74\x70'
                    b'\x3a\x2f\x2f\x77\x77\x77\x2e\x69\x65\x63\x2e\x63\x68\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x16\x49\x45\x43\x20\x68\x74\x74\x70\x3a\x2f\x2f\x77\x77\x77\x2e\x69\x65\x63\x2e'
                    b'\x63\x68\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x64\x65\x73\x63\x00\x00\x00\x00\x00\x00\x00\x2e\x49\x45\x43\x20\x36\x31'
                    b'\x39\x36\x36\x2d\x32\x2e\x31\x20\x44\x65\x66\x61\x75\x6c\x74\x20\x52\x47\x42\x20\x63\x6f'
                    b'\x6c\x6f\x75\x72\x20\x73\x70\x61\x63\x65\x20\x2d\x20\x73\x52\x47\x42\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x2e\x49\x45\x43\x20\x36\x31\x39\x36\x36\x2d\x32\x2e\x31\x20\x44'
                    b'\x65\x66\x61\x75\x6c\x74\x20\x52\x47\x42\x20\x63\x6f\x6c\x6f\x75\x72\x20\x73\x70\x61\x63'
                    b'\x65\x20\x2d\x20\x73\x52\x47\x42\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x64\x65\x73\x63\x00\x00\x00\x00\x00\x00\x00\x2c\x52\x65'
                    b'\x66\x65\x72\x65\x6e\x63\x65\x20\x56\x69\x65\x77\x69\x6e\x67\x20\x43\x6f\x6e\x64\x69\x74'
                    b'\x69\x6f\x6e\x20\x69\x6e\x20\x49\x45\x43\x36\x31\x39\x36\x36\x2d\x32\x2e\x31\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x2c\x52\x65\x66\x65\x72\x65\x6e\x63\x65\x20\x56\x69\x65'
                    b'\x77\x69\x6e\x67\x20\x43\x6f\x6e\x64\x69\x74\x69\x6f\x6e\x20\x69\x6e\x20\x49\x45\x43\x36'
                    b'\x31\x39\x36\x36\x2d\x32\x2e\x31\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x76\x69\x65\x77\x00\x00\x00\x00\x00\x13'
                    b'\xa4\xfe\x00\x14\x5f\x2e\x00\x10\xcf\x14\x00\x03\xed\xcc\x00\x04\x13\x0b\x00\x03\x5c\x9e'
                    b'\x00\x00\x00\x01\x58\x59\x5a\x20\x00\x00\x00\x00\x00\x4c\x09\x56\x00\x50\x00\x00\x00\x57'
                    b'\x1f\xe7\x6d\x65\x61\x73\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00'
                    b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x8f\x00\x00\x00\x02\x73\x69\x67\x20\x00\x00'
                    b'\x00\x00\x43\x52\x54\x20\x63\x75\x72\x76\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x05'
                    b'\x00\x0a\x00\x0f\x00\x14\x00\x19\x00\x1e\x00\x23\x00\x28\x00\x2d\x00\x32\x00\x37\x00\x3b'
                    b'\x00\x40\x00\x45\x00\x4a\x00\x4f\x00\x54\x00\x59\x00\x5e\x00\x63\x00\x68\x00\x6d\x00\x72'
                    b'\x00\x77\x00\x7c\x00\x81\x00\x86\x00\x8b\x00\x90\x00\x95\x00\x9a\x00\x9f\x00\xa4\x00\xa9'
                    b'\x00\xae\x00\xb2\x00\xb7\x00\xbc\x00\xc1\x00\xc6\x00\xcb\x00\xd0\x00\xd5\x00\xdb\x00\xe0'
                    b'\x00\xe5\x00\xeb\x00\xf0\x00\xf6\x00\xfb\x01\x01\x01\x07\x01\x0d\x01\x13\x01\x19\x01\x1f'
                    b'\x01\x25\x01\x2b\x01\x32\x01\x38\x01\x3e\x01\x45\x01\x4c\x01\x52\x01\x59\x01\x60\x01\x67'
                    b'\x01\x6e\x01\x75\x01\x7c\x01\x83\x01\x8b\x01\x92\x01\x9a\x01\xa1\x01\xa9\x01\xb1\x01\xb9'
                    b'\x01\xc1\x01\xc9\x01\xd1\x01\xd9\x01\xe1\x01\xe9\x01\xf2\x01\xfa\x02\x03\x02\x0c\x02\x14'
                    b'\x02\x1d\x02\x26\x02\x2f\x02\x38\x02\x41\x02\x4b\x02\x54\x02\x5d\x02\x67\x02\x71\x02\x7a'
                    b'\x02\x84\x02\x8e\x02\x98\x02\xa2\x02\xac\x02\xb6\x02\xc1\x02\xcb\x02\xd5\x02\xe0\x02\xeb'
                    b'\x02\xf5\x03\x00\x03\x0b\x03\x16\x03\x21\x03\x2d\x03\x38\x03\x43\x03\x4f\x03\x5a\x03\x66'
                    b'\x03\x72\x03\x7e\x03\x8a\x03\x96\x03\xa2\x03\xae\x03\xba\x03\xc7\x03\xd3\x03\xe0\x03\xec'
                    b'\x03\xf9\x04\x06\x04\x13\x04\x20\x04\x2d\x04\x3b\x04\x48\x04\x55\x04\x63\x04\x71\x04\x7e'
                    b'\x04\x8c\x04\x9a\x04\xa8\x04\xb6\x04\xc4\x04\xd3\x04\xe1\x04\xf0\x04\xfe\x05\x0d\x05\x1c'
                    b'\x05\x2b\x05\x3a\x05\x49\x05\x58\x05\x67\x05\x77\x05\x86\x05\x96\x05\xa6\x05\xb5\x05\xc5'
                    b'\x05\xd5\x05\xe5\x05\xf6\x06\x06\x06\x16\x06\x27\x06\x37\x06\x48\x06\x59\x06\x6a\x06\x7b'
                    b'\x06\x8c\x06\x9d\x06\xaf\x06\xc0\x06\xd1\x06\xe3\x06\xf5\x07\x07\x07\x19\x07\x2b\x07\x3d'
                    b'\x07\x4f\x07\x61\x07\x74\x07\x86\x07\x99\x07\xac\x07\xbf\x07\xd2\x07\xe5\x07\xf8\x08\x0b'
                    b'\x08\x1f\x08\x32\x08\x46\x08\x5a\x08\x6e\x08\x82\x08\x96\x08\xaa\x08\xbe\x08\xd2\x08\xe7'
                    b'\x08\xfb\x09\x10\x09\x25\x09\x3a\x09\x4f\x09\x64\x09\x79\x09\x8f\x09\xa4\x09\xba\x09\xcf'
                    b'\x09\xe5\x09\xfb\x0a\x11\x0a\x27\x0a\x3d\x0a\x54\x0a\x6a\x0a\x81\x0a\x98\x0a\xae\x0a\xc5'
                    b'\x0a\xdc\x0a\xf3\x0b\x0b\x0b\x22\x0b\x39\x0b\x51\x0b\x69\x0b\x80\x0b\x98\x0b\xb0\x0b\xc8'
                    b'\x0b\xe1\x0b\xf9\x0c\x12\x0c\x2a\x0c\x43\x0c\x5c\x0c\x75\x0c\x8e\x0c\xa7\x0c\xc0\x0c\xd9'
                    b'\x0c\xf3\x0d\x0d\x0d\x26\x0d\x40\x0d\x5a\x0d\x74\x0d\x8e\x0d\xa9\x0d\xc3\x0d\xde\x0d\xf8'
                    b'\x0e\x13\x0e\x2e\x0e\x49\x0e\x64\x0e\x7f\x0e\x9b\x0e\xb6\x0e\xd2\x0e\xee\x0f\x09\x0f\x25'
                    b'\x0f\x41\x0f\x5e\x0f\x7a\x0f\x96\x0f\xb3\x0f\xcf\x0f\xec\x10\x09\x10\x26\x10\x43\x10\x61'
                    b'\x10\x7e\x10\x9b\x10\xb9\x10\xd7\x10\xf5\x11\x13\x11\x31\x11\x4f\x11\x6d\x11\x8c\x11\xaa'
                    b'\x11\xc9\x11\xe8\x12\x07\x12\x26\x12\x45\x12\x64\x12\x84\x12\xa3\x12\xc3\x12\xe3\x13\x03'
                    b'\x13\x23\x13\x43\x13\x63\x13\x83\x13\xa4\x13\xc5\x13\xe5\x14\x06\x14\x27\x14\x49\x14\x6a'
                    b'\x14\x8b\x14\xad\x14\xce\x14\xf0\x15\x12\x15\x34\x15\x56\x15\x78\x15\x9b\x15\xbd\x15\xe0'
                    b'\x16\x03\x16\x26\x16\x49\x16\x6c\x16\x8f\x16\xb2\x16\xd6\x16\xfa\x17\x1d\x17\x41\x17\x65'
                    b'\x17\x89\x17\xae\x17\xd2\x17\xf7\x18\x1b\x18\x40\x18\x65\x18\x8a\x18\xaf\x18\xd5\x18\xfa'
                    b'\x19\x20\x19\x45\x19\x6b\x19\x91\x19\xb7\x19\xdd\x1a\x04\x1a\x2a\x1a\x51\x1a\x77\x1a\x9e'
                    b'\x1a\xc5\x1a\xec\x1b\x14\x1b\x3b\x1b\x63\x1b\x8a\x1b\xb2\x1b\xda\x1c\x02\x1c\x2a\x1c\x52'
                    b'\x1c\x7b\x1c\xa3\x1c\xcc\x1c\xf5\x1d\x1e\x1d\x47\x1d\x70\x1d\x99\x1d\xc3\x1d\xec\x1e\x16'
                    b'\x1e\x40\x1e\x6a\x1e\x94\x1e\xbe\x1e\xe9\x1f\x13\x1f\x3e\x1f\x69\x1f\x94\x1f\xbf\x1f\xea'
                    b'\x20\x15\x20\x41\x20\x6c\x20\x98\x20\xc4\x20\xf0\x21\x1c\x21\x48\x21\x75\x21\xa1\x21\xce'
                    b'\x21\xfb\x22\x27\x22\x55\x22\x82\x22\xaf\x22\xdd\x23\x0a\x23\x38\x23\x66\x23\x94\x23\xc2'
                    b'\x23\xf0\x24\x1f\x24\x4d\x24\x7c\x24\xab\x24\xda\x25\x09\x25\x38\x25\x68\x25\x97\x25\xc7'
                    b'\x25\xf7\x26\x27\x26\x57\x26\x87\x26\xb7\x26\xe8\x27\x18\x27\x49\x27\x7a\x27\xab\x27\xdc'
                    b'\x28\x0d\x28\x3f\x28\x71\x28\xa2\x28\xd4\x29\x06\x29\x38\x29\x6b\x29\x9d\x29\xd0\x2a\x02'
                    b'\x2a\x35\x2a\x68\x2a\x9b\x2a\xcf\x2b\x02\x2b\x36\x2b\x69\x2b\x9d\x2b\xd1\x2c\x05\x2c\x39'
                    b'\x2c\x6e\x2c\xa2\x2c\xd7\x2d\x0c\x2d\x41\x2d\x76\x2d\xab\x2d\xe1\x2e\x16\x2e\x4c\x2e\x82'
                    b'\x2e\xb7\x2e\xee\x2f\x24\x2f\x5a\x2f\x91\x2f\xc7\x2f\xfe\x30\x35\x30\x6c\x30\xa4\x30\xdb'
                    b'\x31\x12\x31\x4a\x31\x82\x31\xba\x31\xf2\x32\x2a\x32\x63\x32\x9b\x32\xd4\x33\x0d\x33\x46'
                    b'\x33\x7f\x33\xb8\x33\xf1\x34\x2b\x34\x65\x34\x9e\x34\xd8\x35\x13\x35\x4d\x35\x87\x35\xc2'
                    b'\x35\xfd\x36\x37\x36\x72\x36\xae\x36\xe9\x37\x24\x37\x60\x37\x9c\x37\xd7\x38\x14\x38\x50'
                    b'\x38\x8c\x38\xc8\x39\x05\x39\x42\x39\x7f\x39\xbc\x39\xf9\x3a\x36\x3a\x74\x3a\xb2\x3a\xef'
                    b'\x3b\x2d\x3b\x6b\x3b\xaa\x3b\xe8\x3c\x27\x3c\x65\x3c\xa4\x3c\xe3\x3d\x22\x3d\x61\x3d\xa1'
                    b'\x3d\xe0\x3e\x20\x3e\x60\x3e\xa0\x3e\xe0\x3f\x21\x3f\x61\x3f\xa2\x3f\xe2\x40\x23\x40\x64'
                    b'\x40\xa6\x40\xe7\x41\x29\x41\x6a\x41\xac\x41\xee\x42\x30\x42\x72\x42\xb5\x42\xf7\x43\x3a'
                    b'\x43\x7d\x43\xc0\x44\x03\x44\x47\x44\x8a\x44\xce\x45\x12\x45\x55\x45\x9a\x45\xde\x46\x22'
                    b'\x46\x67\x46\xab\x46\xf0\x47\x35\x47\x7b\x47\xc0\x48\x05\x48\x4b\x48\x91\x48\xd7\x49\x1d'
                    b'\x49\x63\x49\xa9\x49\xf0\x4a\x37\x4a\x7d\x4a\xc4\x4b\x0c\x4b\x53\x4b\x9a\x4b\xe2\x4c\x2a'
                    b'\x4c\x72\x4c\xba\x4d\x02\x4d\x4a\x4d\x93\x4d\xdc\x4e\x25\x4e\x6e\x4e\xb7\x4f\x00\x4f\x49'
                    b'\x4f\x93\x4f\xdd\x50\x27\x50\x71\x50\xbb\x51\x06\x51\x50\x51\x9b\x51\xe6\x52\x31\x52\x7c'
                    b'\x52\xc7\x53\x13\x53\x5f\x53\xaa\x53\xf6\x54\x42\x54\x8f\x54\xdb\x55\x28\x55\x75\x55\xc2'
                    b'\x56\x0f\x56\x5c\x56\xa9\x56\xf7\x57\x44\x57\x92\x57\xe0\x58\x2f\x58\x7d\x58\xcb\x59\x1a'
                    b'\x59\x69\x59\xb8\x5a\x07\x5a\x56\x5a\xa6\x5a\xf5\x5b\x45\x5b\x95\x5b\xe5\x5c\x35\x5c\x86'
                    b'\x5c\xd6\x5d\x27\x5d\x78\x5d\xc9\x5e\x1a\x5e\x6c\x5e\xbd\x5f\x0f\x5f\x61\x5f\xb3\x60\x05'
                    b'\x60\x57\x60\xaa\x60\xfc\x61\x4f\x61\xa2\x61\xf5\x62\x49\x62\x9c\x62\xf0\x63\x43\x63\x97'
                    b'\x63\xeb\x64\x40\x64\x94\x64\xe9\x65\x3d\x65\x92\x65\xe7\x66\x3d\x66\x92\x66\xe8\x67\x3d'
                    b'\x67\x93\x67\xe9\x68\x3f\x68\x96\x68\xec\x69\x43\x69\x9a\x69\xf1\x6a\x48\x6a\x9f\x6a\xf7'
                    b'\x6b\x4f\x6b\xa7\x6b\xff\x6c\x57\x6c\xaf\x6d\x08\x6d\x60\x6d\xb9\x6e\x12\x6e\x6b\x6e\xc4'
                    b'\x6f\x1e\x6f\x78\x6f\xd1\x70\x2b\x70\x86\x70\xe0\x71\x3a\x71\x95\x71\xf0\x72\x4b\x72\xa6'
                    b'\x73\x01\x73\x5d\x73\xb8\x74\x14\x74\x70\x74\xcc\x75\x28\x75\x85\x75\xe1\x76\x3e\x76\x9b'
                    b'\x76\xf8\x77\x56\x77\xb3\x78\x11\x78\x6e\x78\xcc\x79\x2a\x79\x89\x79\xe7\x7a\x46\x7a\xa5'
                    b'\x7b\x04\x7b\x63\x7b\xc2\x7c\x21\x7c\x81\x7c\xe1\x7d\x41\x7d\xa1\x7e\x01\x7e\x62\x7e\xc2'
                    b'\x7f\x23\x7f\x84\x7f\xe5\x80\x47\x80\xa8\x81\x0a\x81\x6b\x81\xcd\x82\x30\x82\x92\x82\xf4'
                    b'\x83\x57\x83\xba\x84\x1d\x84\x80\x84\xe3\x85\x47\x85\xab\x86\x0e\x86\x72\x86\xd7\x87\x3b'
                    b'\x87\x9f\x88\x04\x88\x69\x88\xce\x89\x33\x89\x99\x89\xfe\x8a\x64\x8a\xca\x8b\x30\x8b\x96'
                    b'\x8b\xfc\x8c\x63\x8c\xca\x8d\x31\x8d\x98\x8d\xff\x8e\x66\x8e\xce\x8f\x36\x8f\x9e\x90\x06'
                    b'\x90\x6e\x90\xd6\x91\x3f\x91\xa8\x92\x11\x92\x7a\x92\xe3\x93\x4d\x93\xb6\x94\x20\x94\x8a'
                    b'\x94\xf4\x95\x5f\x95\xc9\x96\x34\x96\x9f\x97\x0a\x97\x75\x97\xe0\x98\x4c\x98\xb8\x99\x24'
                    b'\x99\x90\x99\xfc\x9a\x68\x9a\xd5\x9b\x42\x9b\xaf\x9c\x1c\x9c\x89\x9c\xf7\x9d\x64\x9d\xd2'
                    b'\x9e\x40\x9e\xae\x9f\x1d\x9f\x8b\x9f\xfa\xa0\x69\xa0\xd8\xa1\x47\xa1\xb6\xa2\x26\xa2\x96'
                    b'\xa3\x06\xa3\x76\xa3\xe6\xa4\x56\xa4\xc7\xa5\x38\xa5\xa9\xa6\x1a\xa6\x8b\xa6\xfd\xa7\x6e'
                    b'\xa7\xe0\xa8\x52\xa8\xc4\xa9\x37\xa9\xa9\xaa\x1c\xaa\x8f\xab\x02\xab\x75\xab\xe9\xac\x5c'
                    b'\xac\xd0\xad\x44\xad\xb8\xae\x2d\xae\xa1\xaf\x16\xaf\x8b\xb0\x00\xb0\x75\xb0\xea\xb1\x60'
                    b'\xb1\xd6\xb2\x4b\xb2\xc2\xb3\x38\xb3\xae\xb4\x25\xb4\x9c\xb5\x13\xb5\x8a\xb6\x01\xb6\x79'
                    b'\xb6\xf0\xb7\x68\xb7\xe0\xb8\x59\xb8\xd1\xb9\x4a\xb9\xc2\xba\x3b\xba\xb5\xbb\x2e\xbb\xa7'
                    b'\xbc\x21\xbc\x9b\xbd\x15\xbd\x8f\xbe\x0a\xbe\x84\xbe\xff\xbf\x7a\xbf\xf5\xc0\x70\xc0\xec'
                    b'\xc1\x67\xc1\xe3\xc2\x5f\xc2\xdb\xc3\x58\xc3\xd4\xc4\x51\xc4\xce\xc5\x4b\xc5\xc8\xc6\x46'
                    b'\xc6\xc3\xc7\x41\xc7\xbf\xc8\x3d\xc8\xbc\xc9\x3a\xc9\xb9\xca\x38\xca\xb7\xcb\x36\xcb\xb6'
                    b'\xcc\x35\xcc\xb5\xcd\x35\xcd\xb5\xce\x36\xce\xb6\xcf\x37\xcf\xb8\xd0\x39\xd0\xba\xd1\x3c'
                    b'\xd1\xbe\xd2\x3f\xd2\xc1\xd3\x44\xd3\xc6\xd4\x49\xd4\xcb\xd5\x4e\xd5\xd1\xd6\x55\xd6\xd8'
                    b'\xd7\x5c\xd7\xe0\xd8\x64\xd8\xe8\xd9\x6c\xd9\xf1\xda\x76\xda\xfb\xdb\x80\xdc\x05\xdc\x8a'
                    b'\xdd\x10\xdd\x96\xde\x1c\xde\xa2\xdf\x29\xdf\xaf\xe0\x36\xe0\xbd\xe1\x44\xe1\xcc\xe2\x53'
                    b'\xe2\xdb\xe3\x63\xe3\xeb\xe4\x73\xe4\xfc\xe5\x84\xe6\x0d\xe6\x96\xe7\x1f\xe7\xa9\xe8\x32'
                    b'\xe8\xbc\xe9\x46\xe9\xd0\xea\x5b\xea\xe5\xeb\x70\xeb\xfb\xec\x86\xed\x11\xed\x9c\xee\x28'
                    b'\xee\xb4\xef\x40\xef\xcc\xf0\x58\xf0\xe5\xf1\x72\xf1\xff\xf2\x8c\xf3\x19\xf3\xa7\xf4\x34'
                    b'\xf4\xc2\xf5\x50\xf5\xde\xf6\x6d\xf6\xfb\xf7\x8a\xf8\x19\xf8\xa8\xf9\x38\xf9\xc7\xfa\x57'
                    b'\xfa\xe7\xfb\x77\xfc\x07\xfc\x98\xfd\x29\xfd\xba\xfe\x4b\xfe\xdc\xff\x6d\xff\xff')

# Linear RGB ICC profile
LINEAR_RGB_ICC_PROFILE = (b'\x00\x00\x01\xE0\x41\x44\x42\x45\x02\x10\x00\x00\x6D\x6E\x74\x72\x52\x47\x42\x20\x58'
                          b'\x59\x5A\x20\x07\xDF\x00\x0C\x00\x16\x00\x08\x00\x04\x00\x1E\x61\x63\x73\x70\x41\x50'
                          b'\x50\x4C\x00\x00\x00\x00\x6E\x6F\x6E\x65\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\xF6\xD6\x00\x01\x00\x00\x00\x00\xD3\x2C\x41\x44\x42\x45'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x09\x64\x65\x73\x63\x00\x00\x00\xF0\x00\x00\x00\x6A\x63\x70\x72'
                          b'\x74\x00\x00\x01\x5C\x00\x00\x00\x21\x77\x74\x70\x74\x00\x00\x01\x80\x00\x00\x00\x14'
                          b'\x72\x58\x59\x5A\x00\x00\x01\x94\x00\x00\x00\x14\x67\x58\x59\x5A\x00\x00\x01\xA8\x00'
                          b'\x00\x00\x14\x62\x58\x59\x5A\x00\x00\x01\xBC\x00\x00\x00\x14\x72\x54\x52\x43\x00\x00'
                          b'\x01\xD0\x00\x00\x00\x0E\x62\x54\x52\x43\x00\x00\x01\xD0\x00\x00\x00\x0E\x67\x54\x52'
                          b'\x43\x00\x00\x01\xD0\x00\x00\x00\x0E\x64\x65\x73\x63\x00\x00\x00\x00\x00\x00\x00\x10'
                          b'\x4C\x69\x6E\x65\x61\x72\x69\x7A\x65\x64\x20\x73\x52\x47\x42\x00\x00\x00\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                          b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x74\x65\x78\x74\x00\x00\x00\x00\x6E'
                          b'\x6F\x20\x63\x6F\x70\x79\x72\x69\x67\x68\x74\x2C\x20\x75\x73\x65\x20\x66\x72\x65\x65'
                          b'\x6C\x79\x00\x00\x00\x00\x58\x59\x5A\x20\x00\x00\x00\x00\x00\x00\xF3\x52\x00\x01\x00'
                          b'\x00\x00\x01\x16\xCC\x58\x59\x5A\x20\x00\x00\x00\x00\x00\x00\x6F\xA1\x00\x00\x38\xF5'
                          b'\x00\x00\x03\x90\x58\x59\x5A\x20\x00\x00\x00\x00\x00\x00\x62\x96\x00\x00\xB7\x87\x00'
                          b'\x00\x18\xDA\x58\x59\x5A\x20\x00\x00\x00\x00\x00\x00\x24\x9F\x00\x00\x0F\x84\x00\x00'
                          b'\xB6\xC2\x63\x75\x72\x76\x00\x00\x00\x00\x00\x00\x00\x01\x01\x00\x00\x00')


def _limit_number(val, min_val, max_val):
    """
    Returns val, or min_val or max_val if val is out of range.
    """
    if val < min_val:
        return min_val
    elif val > max_val:
        return max_val
    return val
