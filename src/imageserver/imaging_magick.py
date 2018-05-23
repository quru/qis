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

        See imaging.imaging_init() for a description of the parameters.
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
        ImageMagick implementation of imaging.adjust_image(),
        see the function documentation there for full details.
        """
        return qismagick.adjust_image(
            image_data,
            data_type,
            page,
            new_width,
            new_height,
            1 if size_auto_fit else 0,
            align_h,
            align_v,
            rotation,
            flip,
            crop_top,
            crop_left,
            crop_bottom,
            crop_right,
            1 if crop_auto_fit else 0,
            fill_colour,
            iformat,
            rquality,
            cquality,
            sharpen,
            dpi,
            1 if strip_info else 0,
            overlay_data,
            overlay_size,
            overlay_pos,
            overlay_opacity,
            icc_profile,
            icc_intent,
            1 if icc_bpc else 0,
            colorspace,
            tile_spec[0],
            tile_spec[1]
        )


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
