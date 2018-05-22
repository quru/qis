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
# Last Changed:  $Date$ $Rev$ by $Author$
#
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
#

__pillow_import_error = None
try:
    import PIL
except Exception as e:
    __pillow_import_error = e


def pillow_init():
    """
    Initialises the Pillow library.
    This function must be called once before the other functions can be used.
    An ImportError is raised if the Pillow library failed to load.
    """
    global __pillow_import_error
    if __pillow_import_error:
        raise ImportError("Failed to import Pillow: " + str(__pillow_import_error))


def pillow_adjust_image(
        image_data, data_type,
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
    Pillow version of imagemagick_adjust_image() in the imaging_magick.py back end.
    See the function documentation there for full details.
    This method may not support all the functionality of the ImageMagick version.
    """
    # TODO implement me
    return None


def pillow_burst_pdf(pdf_data, dest_dir, dpi):
    """
    Pillow version of imagemagick_burst_pdf() in the imaging_magick.py back end.
    See the function documentation there for full details.
    This method may not support all the functionality of the ImageMagick version.
    """
    raise NotImplementedError(
        'PDF support is not currently implemented in the free version'
    )


def pillow_get_image_profile_data(image_data, data_type):
    """
    Pillow version of imagemagick_get_image_profile_data() in the imaging_magick.py back end.
    See the function documentation there for full details.
    This method may not support all the functionality of the ImageMagick version.
    """
    # TODO implement me
    return []


def pillow_get_image_dimensions(image_data, data_type):
    """
    Pillow version of imagemagick_get_image_dimensions() in the imaging_magick.py back end.
    See the function documentation there for full details.
    """
    # TODO implement me
    return (0, 0)


def pillow_get_version_info():
    """
    Returns a string with the Pillow library version information.
    """
    return "Pillow version: " + PIL.__version__
