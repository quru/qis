#
# Quru Image Server
#
# Document:      imaging_magick.py
# Date started:  07 Mar 2011
# By:            Matt Fozard
# Purpose:       Provides an interface to the ImageMagick image processing library
# Requires:      qismagick (qismagick.so must be located somewhere in the PYTHONPATH)
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
# 18Jul2011  Matt  Added get_image_profile_data
# 27Oct2011  Matt  Added get_image_dimensions
# 20Nov2012  Matt  Added get_library_info
# 23Nov2012  Matt  Added burst_pdf
# 15Apr2013  Matt  Added init() function with configuration options
# 18Apr2013  Matt  Added colorspace parameter to adjust_image
# 29Apr2013  Matt  Added flip parameter to adjust_image
# 06May2013  Matt  Pass through DPI value for init() and burst_pdf()
# 13Jun2013  Matt  Added image overlay parameters to adjust_image
# 22Aug2013  Matt  Added align parameters to adjust_image
# 10Dec2015  Matt  qismagick 2.0 - pass through data formats for identification
#                  of ambiguous file types (plain TIFF vs RAW TIFF)
# 05Jun2018  Matt  qismagick 4.0 - imaging operations are now a dict,
#                  add supported operations function
#

# TODO Consider testing/setting MAGICK_THREAD_LIMIT environment variable under mod_wsgi

_qismagick_import_error = None
try:
    import qismagick
except Exception as e:
    _qismagick_import_error = e


class ImageMagickBackend(object):
    """
    Implements a back-end for imaging.py using the qismagick.so C library.
    """
    def __init__(self, gs_path, temp_files_path, pdf_default_dpi):
        """
        Initialises the ImageMagick library. This function must be called once
        before the other functions can be used.

        See imaging.init() for a description of the parameters.
        An ImportError is raised if the ImageMagick library failed to load.
        """
        global _qismagick_import_error
        if _qismagick_import_error:
            raise ImportError("Failed to import qismagick.so: " + str(_qismagick_import_error))
        qismagick.init(gs_path, temp_files_path, pdf_default_dpi)

    def get_version_info(self):
        """
        Returns a string with the ImageMagick library version information.
        """
        return qismagick.get_library_info()

    def supported_file_types(self):
        """
        Returns which image types are supported by the ImageMagick back-end.
        See the function documentation for imaging.supported_file_types() for
        more information.
        """
        return None

    def supported_operations(self):
        """
        Returns which imaging operations are supported by the ImageMagick back-end.
        See the function documentation for imaging.supported_operations() and
        imaging.adjust_image() for more information.
        """
        return {
            'page': True,
            'width': True,
            'height': True,
            'size_fit': True,
            'align_h': True,
            'align_v': True,
            'rotation': True,
            'flip': True,
            'sharpen': True,
            'dpi_x': True,
            'dpi_y': True,
            'fill': True,
            'top': True,
            'left': True,
            'bottom': True,
            'right': True,
            'crop_fit': True,
            'overlay_data': True,
            'overlay_size': True,
            'overlay_pos': True,
            'overlay_opacity': True,
            'icc_data': True,
            'icc_intent': True,
            'icc_bpc': True,
            'tile': True,
            'colorspace': True,
            'format': True,
            'quality': True,
            'resize_type': True,
            'resize_gamma': True,
            'strip': True
        }

    def adjust_image(self, image_data, data_type, image_spec):
        """
        ImageMagick implementation of imaging.adjust_image(),
        see the function documentation there for full details.
        """
        return qismagick.adjust_image(image_data, data_type, image_spec)

    def burst_pdf(self, pdf_data, dest_dir, dpi):
        """
        ImageMagick implementation of imaging.burst_pdf(),
        see the function documentation there for full details.
        """
        return qismagick.burst_pdf(pdf_data, dest_dir, dpi)

    def get_image_profile_data(self, image_data, data_type):
        """
        ImageMagick implementation of imaging.get_image_profile_data(),
        see the function documentation there for full details.
        """
        return qismagick.get_image_profile_data(image_data, data_type)

    def get_image_dimensions(self, image_data, data_type):
        """
        ImageMagick implementation of imaging.get_image_dimensions(),
        see the function documentation there for full details.
        """
        return qismagick.get_image_dimensions(image_data, data_type)
