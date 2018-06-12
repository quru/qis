#
# Quru Image Server
#
# Document:      imaging.py
# Date started:  22 May 2018
# By:            Matt Fozard
# Purpose:       Front-end interface to the supported imaging back-ends
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
# Notable modifications:
# Date       By    Details
# =========  ====  ============================================================
#

import tempfile

from . import imaging_magick as magick
from . import imaging_pillow as pillow

_backend = None


def backend_supported(back_end):
    """
    Returns whether a back-end imaging library is installed and supported.
    Possible back-ends: "pillow" or "imagemagick". This method can be called
    before imaging.init() to find out what back-ends are available.
    """
    try:
        if back_end.lower() == 'imagemagick':
            return magick.ImageMagickBackend('gs', '.', 150) is not None
        elif back_end.lower() == 'pillow':
            return pillow.PillowBackend('gs', '.', 150) is not None
    except ImportError:
        pass
    return False


def init(back_end='auto', gs_path='gs', temp_files_path=None, pdf_default_dpi=150):
    """
    Initialises the back-end imaging library. This function must be called
    once on startup before the other functions can be used; it is not safe
    to call during normal operation.
    An ImportError is raised if the back-end imaging library cannot be loaded.

    back_end - which back-end to load: "pillow", "imagemagick", or "auto"
    gs_path - for PDF file support, the path to the Ghostscript command, e.g. "gs"
    temp_files_path - the directory in which to create temp files, e.g. "/tmp",
                      defaults to the operating system's temp directory
    pdf_default_dpi - the default target DPI when converting PDFs to images,
                      or when requesting the dimensions of a PDF, e.g. 150
    """
    global _backend
    if not temp_files_path:
        temp_files_path = tempfile.gettempdir()

    if back_end.lower() == 'imagemagick':
        _backend = magick.ImageMagickBackend(gs_path, temp_files_path, pdf_default_dpi)
    elif back_end.lower() == 'pillow':
        _backend = pillow.PillowBackend(gs_path, temp_files_path, pdf_default_dpi)
    elif back_end.lower() == 'auto':
        try:
            _backend = magick.ImageMagickBackend(gs_path, temp_files_path, pdf_default_dpi)
        except ImportError:
            _backend = pillow.PillowBackend(gs_path, temp_files_path, pdf_default_dpi)
    else:
        raise ValueError('Unsupported back end: ' + back_end)


def get_backend():
    """
    Returns whether the initialised imaging back-end is "pillow" or "imagemagick",
    or returns None if imaging.init() has not been called.
    """
    global _backend
    if not _backend:
        return None
    elif isinstance(_backend, magick.ImageMagickBackend):
        return 'imagemagick'
    elif isinstance(_backend, pillow.PillowBackend):
        return 'pillow'
    else:
        return 'unknown'


def get_version_info():
    """
    Returns a string containing the back-end library version information.
    """
    return _backend.get_version_info()


# TODO we might need a supported file types too
# TODO poke operation support via image manager, not here directly,
#      and map overlay data/src and icc data/src keys


def supported_operations():
    """
    Returns a dictionary of key:boolean entries for which of the imaging operations
    defined for imaging.adjust_image() are supported by the current back-end. Some
    back-ends may add their own keys, and some may not return "standard" keys if
    they have not been kept updated. Therefore use this function as follows:

        key_supported = imaging.supported_operations().get(key, False)
    """
    return _backend.supported_operations()


def adjust_image(image_data, data_type, image_spec):
    """
    Alters an encoded image in any of the following ways, returning a newly encoded
    image: resize, rotate, crop, change format, change compression, sharpen or blur,
    adjust colour profile, change colour space, apply an overlay, strip metadata.

    image_data  - the raw image data (e.g. JPG bytes)
    data_type   - optional type (file extension) of the image data
    image_spec  - a key:value dictionary of imaging operations to perform

    The defined image_spec dictionary keys/values are as follows, though not
    all back-ends support all operations, and some may support extras. Use the
    imaging.supported_operations() function to query back-end support. Most of the
    keys are intentionally the same as those used for the image templates API,
    but there are differences for icc profile and overlay image, which are
    filenames in the templates but raw profile/image bytes here.

    page:          the page number to return (for multi-page images), default 1
    width:         the new image width, or 0 to keep proportional with a new height
    height:        the new image height, or 0 to keep proportional with a new width
    size_fit:      whether to adjust the requested width and height to retain the
                   image proportions and prevent padding, True or False
    align_h:       horizontal alignment if the image is to be padded, as the edge
                   to align (L, C, or R) and position 0 to 1, default "C0.5"
    align_v:       vertical alignment if the image is to be padded, as the edge
                   to align (T, C, or B) and position 0 to 1, default "C0.5"
    rotation:      number of degrees to rotate the image clockwise, default 0.0
    flip:          flip the image horizontally or vertically, "h" or "v", default ""
    sharpen:       sharpen or blur effect to apply, from -500 (heavy blur) to 500
                   (heavy sharpen), default 0 (none)
    dpi_x:         a new horizontal DPI value to assign to the image, default 0 (no change)
    dpi_y:         a new vertical DPI value to assign to the image, default 0 (no change)
    fill:          image background colour (when rotating or specifying both width
                   and height), format "blue", "#ffffff", "rgb(0,0,0)", or special
                   values "auto" or "transparent", default white
    top:           top cropping value, 0 to 1, default 0.0 (none)
    left:          left cropping value, 0 to 1, default 0.0 (none)
    bottom:        bottom cropping value, 0 to 1, default 1.0 (none)
    right:         right cropping value, 0 to 1, default 1.0 (none)
    crop_fit:      whether to adjust cropping positions to reduce padding when both
                   width and height are specified, True or False
    overlay_data:  raw image bytes to overlay as a watermark, default None
    overlay_size:  size of the overlay relative to the base image, 0 to 1, default 1.0
    overlay_pos:   position of the overlay on the main image:
                   "N", "NE", "E","SE", "S", "SW", "W", "NW", default "C" for centre.
    overlay_opacity: opacity level of the overlay, 0 to 1, default 1.0 (opaque)
    icc_data:      raw bytes of an ICC profile to apply to the image, default None
    icc_intent:    how to apply the ICC profile: "saturation", "perceptual",
                   "absolute", or "relative", default ""
    icc_bpc:       whether to use black point compensation when applying an ICC
                   profile with the relative rendering intent, True or False
    tile:          tuple of (tile number, grid size) to produce an image tile
                   following all other adjustments, default (0, 0)
    colorspace:    changes the colour model of an image: "rgb", "gray", or "cmyk",
                   default "" (no change)
    format:        lower case image format to return, default "jpg"
    quality:       JPG quality or PNG compression type, 0 to 100, default 80
    resize_type:   resizing algorithm, 1 (fastest) to 3 (best quality), default 3
    strip:         whether to strip EXIF data and colour profiles from the image,
                   True or False, default False

    Specifying both width and height of 0 will retain the original image size.

    If the requested new width/height or cropping values define a different aspect
    ratio, and auto_size_fit is false, the image will be returned at the requested
    size, with the original image centred within it, surrounded by the fill colour.
    If auto_size_fit is true, either the width or height will be reduced so that
    there is no fill (and so then the requested size is not respected).

    When cropping the image and a target width and a height have been specified,
    the optional auto_crop_fit flag can be enabled. This will attempt to minimise
    the amount of fill colour (padding) in the final image by enlarging the
    requested crop rectangle to best fill the target. Padding will not necessarily
    be eliminated unless the auto_size_fit flag is also used.

    If a tile of the image is requested, tile number must be between 1 and
    the grid size inclusive. The grid size must be a square (4, 9, 16, etc),
    minimum size 4. Tile number 1 is top left in the grid, and the last tile is
    bottom right. The tile is generated last, after all other adjustments.

    Returns a new image, encoded in the format requested by the image_spec.

    Raises a ValueError if the supplied data is not a supported image, or for
    invalid parameter values. Other back-end specific errors may also be raised.
    """
    return _backend.adjust_image(image_data, data_type, image_spec)


def burst_pdf(pdf_data, dest_dir, dpi):
    """
    Exports every page of a PDF file as separate PNG files into a directory
    using Ghostscript. Note that this operation may take some time.

    pdf_data - the raw PDF data
    dest_dir - the full absolute path of the destination directory,
               which must exist and be writable
    dpi - the target PNG image DPI (larger values result in larger images),
          or 0 to use the default value

    Returns a boolean for whether the command succeeded. If not, some files
    may have been written to the destination directory, and it is left up to
    the caller to decide whether to remove them or not.

    Raises an EnvironmentError if Ghostscript is not installed.
    Raises a ValueError if the supplied data is not a PDF.
    Raises an IOError if the destination path is invalid.
    """
    return _backend.burst_pdf(pdf_data, dest_dir, dpi)


def get_image_profile_data(image_data, data_type):
    """
    Reads and returns all EXIF / IPTC / XMP / etc profile data from an image.

    image_data  - the raw image data
    data_type   - optional type (file extension) of the image data

    Returns a list of tuples with format (profile, property, value)
    E.g. [('exif', 'Make', 'Canon'), ('exif', 'Model', '300D')]
    or an empty list if no profile data was found in the image.

    Raises a ValueError if the supplied data is not a supported image.
    """
    return _backend.get_image_profile_data(image_data, data_type)


def get_image_dimensions(image_data, data_type):
    """
    Obtains the pixel dimensions an image in an efficient way,
    avoiding the need to decode the image.

    image_data  - the raw image data
    data_type   - optional type (file extension) of the image data

    Returns a tuple with format (width, height).

    Raises a ValueError if the supplied data is not a supported image.
    """
    return _backend.get_image_dimensions(image_data, data_type)
