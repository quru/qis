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

_pillow_import_error = None
try:
    import PIL
    from PIL import Image, ExifTags, TiffTags, IptcImagePlugin
except Exception as e:
    _pillow_import_error = e


class PillowBackend(object):
    """
    Implements a back-end for imaging.py using the Python Pillow library.
    """
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
        image = self._load_image_data(image_data, data_type)
        try:
            # TODO implement me
            raise ValueError('This is TODO')
        finally:
            image.close()

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
