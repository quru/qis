#
# Quru Image Server
#
# Document:      test_imaging.py
# Date started:  07 June 2018
# By:            Matt Fozard
# Purpose:       Tests imaging operations
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
# 07Jun2018  Matt  Moved imaging tests out from tests.py, added Pillow tests
#

import binascii
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from . import tests as main_tests

from imageserver import imaging
from imageserver.api_util import API_CODES
from imageserver.flask_app import app as flask_app
from imageserver.flask_app import cache_engine as cm
from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import image_engine as im
from imageserver.flask_app import task_engine as tm
from imageserver.filesystem_manager import (
    get_abs_path, delete_dir, delete_file, path_exists
)
from imageserver.filesystem_sync import auto_sync_file, auto_sync_existing_file
from imageserver.image_attrs import ImageAttrs
from imageserver.models import Image, ImageTemplate


# Utility - returns a tuple of (width, height) of a PNG image
def get_png_dimensions(png_data):
    if png_data[1:6] != b'PNG\r\n':
        raise ValueError('Provided data is not a PNG image')
    wbin = png_data[16:20]
    hbin = png_data[20:24]
    return (int(binascii.hexlify(wbin), 16), int(binascii.hexlify(hbin), 16))


# Utility - returns the first of paths+app_name that exists, else app_name
def get_app_path(app_name, paths):
    app_path = app_name
    for p in paths:
        try_path = os.path.join(p, app_name)
        if os.path.exists(try_path):
            app_path = try_path
            break
    return app_path


# Possible paths to ImageMagick binaries, in order of preference
IMAGEMAGICK_PATHS = [
    "/usr/local/bin/",  # Installed from source
    "/usr/bin/",        # Installed from rpm
    ""                  # Default / first found in the PATH
]

# At some point from 9.14 to 9.16 Ghostscript draws thicker lines than before
GS_LINES_VERSION = 914
# http://www.imagemagick.org/script/changelog.php
# "2011-11-07 6.7.3-4 RotateImage() now uses distorts rather than shears."
# Note: based on the change log, this number is a guess rather than a known fact
MAGICK_ROTATION_VERSION = 673


# TODO this and compare_images - convert to pillow if we can
def compare_images(img_path1, img_path2):
    diff_temp_fd, diff_temp_nm = tempfile.mkstemp('.png')
    os.close(diff_temp_fd)

    # Generate diff image
    p = subprocess.Popen([
            get_app_path('compare', IMAGEMAGICK_PATHS),
            "-colorspace", "RGB",
            img_path1,
            img_path2,
            diff_temp_nm
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output = p.communicate()
    errmsg = (output[1] or output[0])
    errmsg = errmsg.decode('utf8')
    if errmsg:
        raise ValueError('Compare generation error: ' + errmsg)

    # Get metrics about the diff image
    p = subprocess.Popen([
            get_app_path('compare', IMAGEMAGICK_PATHS),
            "-colorspace", "RGB",
            "-metric", "PSNR",
            img_path1,
            img_path2,
            diff_temp_nm
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output = p.communicate()
    result = output[1].decode('utf8').strip()
    os.remove(diff_temp_nm)
    # ImageMagick compare switched "identical" PSNR to 0 in 6.9.5-4 and to "inf" in 6.9.7-10
    psnr = float(result) if result not in ('0', 'inf') else 1000
    return psnr


# TODO Add CommonTests that should be run for both back ends
#      have a list of [im, pil] or [pil] auto detected
#      use a test_fn with loop on the list to switch back end and run a _test_fn


@unittest.skipIf(
    not imaging.imaging_backend_supported('pillow'),
    'Pillow imaging is not installed'
)
class PillowTests(main_tests.BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super(PillowTests, cls).setUpClass()
        main_tests.init_tests()
        # Switch to the Pillow back end
        imaging.imaging_init(
            'pillow',
            flask_app.config['GHOSTSCRIPT_PATH'],
            flask_app.config['TEMP_DIR'],
            flask_app.config['PDF_BURST_DPI']
        )

    # TODO write me


@unittest.skipIf(
    not imaging.imaging_backend_supported('imagemagick'),
    'ImageMagick imaging is not installed'
)
class ImageMagickTests(main_tests.BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super(ImageMagickTests, cls).setUpClass()
        main_tests.init_tests()
        # Switch to the ImageMagick back end
        imaging.imaging_init(
            'imagemagick',
            flask_app.config['GHOSTSCRIPT_PATH'],
            flask_app.config['TEMP_DIR'],
            flask_app.config['PDF_BURST_DPI']
        )

    # TODO this and compare_images - convert to pillow if we can
    # Utility - asserts that an image matches an image file on disk
    # "Typical values for the PSNR in lossy image and video compression are between 30 and 50"
    # http://en.wikipedia.org/wiki/Peak_signal-to-noise_ratio
    def assertImageMatch(self, img_data, match_file, tolerance=46):
        if os.path.exists(match_file):
            static_img = match_file
        else:
            static_img = os.path.join('tests/images', match_file)
            if not os.path.exists(static_img):
                static_img = os.path.join('src/tests/images', match_file)
            if not os.path.exists(static_img):
                raise ValueError('Test image not found: ' + match_file)
        temp_img = '/tmp/qis_img.tmp'
        try:
            with open(temp_img, 'wb') as f:
                f.write(img_data)
            psnr = compare_images(temp_img, static_img)
            self.assertGreaterEqual(psnr, tolerance)
        except Exception:
            # Save the unmatched image for evaluation
            compare_name = os.path.split(static_img)[1]
            shutil.copy(temp_img, '/tmp/match-test-fail-' + compare_name)
            raise
        finally:
            os.remove(temp_img)

    # Utility - invoke ImageMagick convert command, wait for completion,
    #           and return a boolean indicating success
    def call_im_convert(self, args_list):
        args_list.insert(0, get_app_path('convert', IMAGEMAGICK_PATHS))
        return subprocess.call(args_list) == 0

    # Utility - invoke ImageMagick composite command, wait for completion,
    #           and return a boolean indicating success
    def call_im_composite(self, args_list):
        args_list.insert(0, get_app_path('composite', IMAGEMAGICK_PATHS))
        return subprocess.call(args_list) == 0

    # Utility - returns the ImageMagick library version as an integer, e.g. 654 for v6.5.4
    def imagemagick_version(self):
        # Assumes format "ImageMagick version: 654, Ghostscript delegate: 9.10"
        return int(imaging.imaging_get_version_info()[21:24])

    # Utility - returns the Ghostscript application version as an integer, e.g. 910 for v9.10
    def gs_version(self):
        # Assumes format "ImageMagick version: 654, Ghostscript delegate: 9.10"
        return int(float(imaging.imaging_get_version_info()[-4:]) * 100)

    # Utility - invoke Ghostscript gs command, wait for completion,
    #           and return a boolean indicating success
    def call_gs(self, args_list):
        args_list.insert(0, flask_app.config['GHOSTSCRIPT_PATH'])
        return subprocess.call(args_list) == 0

    # Utility - check that the keyword args/values are present in the given
    # dictionary of image properties (from ImageManager.get_image_properties)
    def check_image_properties_dict(self, props, profile, **kwargs):
        self.assertIn(profile, props)
        profile_dict = dict(props[profile])
        for k in kwargs:
            self.assertEqual(profile_dict[k], kwargs[k])

    # Compares a server generated image with the version generated by Imagemagick convert
    def compare_convert(self, img_url, magick_params):
        return self._compare_im_fn(self.call_im_convert, img_url, magick_params)

    # Compares a server generated image with the version generated by Imagemagick composite
    def compare_composite(self, img_url, magick_params):
        return self._compare_im_fn(self.call_im_composite, img_url, magick_params)

    # Back end to the above 2
    def _compare_im_fn(self, im_fn, img_url, magick_params):
        tempfile = magick_params[-1]
        # Generate image with IM
        assert im_fn(magick_params), 'ImageMagick call failed'
        # Generate the same with the image server
        rv = self.app.get(img_url)
        assert rv.status_code == 200, 'Failed to generate image: ' + rv.data.decode('utf8')
        self.assertImageMatch(rv.data, tempfile)
        if os.path.exists(tempfile):
            os.remove(tempfile)

    # Test serving of plain image
    def test_serve_plain_image(self):
        rv = self.app.get('/image?src=test_images/cathedral.jpg')
        self.assertEqual(rv.status_code, 200)
        self.assertIn('image/jpeg', rv.headers['Content-Type'])
        # knowing length requires 'keep original' values in settings
        self.assertEqual(len(rv.data), 648496)
        self.assertEqual(rv.headers.get('Content-Length'), '648496')

    # Test serving of public image with public width (but not height) limit
    def test_public_width_limit(self):
        flask_app.config['PUBLIC_MAX_IMAGE_WIDTH'] = 800
        flask_app.config['PUBLIC_MAX_IMAGE_HEIGHT'] = 0
        # Being within the limit should be OK
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=600')
        self.assertEqual(rv.status_code, 200)
        # Complete but small images should still be OK
        rv = self.app.get('/image?src=test_images/quru470.png')
        self.assertEqual(rv.status_code, 200)
        # Requesting full image should apply the limits as default width/height
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, _h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 800)
        # Requesting large version of image should be denied
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=900')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('exceeds', rv.data.decode('utf8'))
        # height 680 --> width of 907 (so deny)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&height=680')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('exceeds', rv.data.decode('utf8'))
        # rotated 90 deg, height 680 --> width 510 (allowed)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&height=680&angle=90')
        self.assertEqual(rv.status_code, 200)
        # Being logged in should not enforce any restriction
        self.login('admin', 'admin')
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=900')
        self.assertEqual(rv.status_code, 200)
        (w, _h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 900)

    # Test serving of public image with public width+height limit
    def test_public_width_and_height_limit(self):
        flask_app.config['PUBLIC_MAX_IMAGE_WIDTH'] = 800
        flask_app.config['PUBLIC_MAX_IMAGE_HEIGHT'] = 400
        # Being at the limit should be OK
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=800&height=400')
        self.assertEqual(rv.status_code, 200)
        # Anything over the limit, not (with no rotate/crop cleverness this time)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=800&height=410')
        self.assertEqual(rv.status_code, 400)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=810&height=400')
        self.assertEqual(rv.status_code, 400)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=810&height=410')
        self.assertEqual(rv.status_code, 400)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=810&height=410&angle=90')
        self.assertEqual(rv.status_code, 400)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=810&height=410&left=0.2&right=0.8&top=0.2&bottom=0.8')
        self.assertEqual(rv.status_code, 400)

    # Test serving of public image without any width/height defined
    def test_public_image_defaults(self):
        flask_app.config['PUBLIC_MAX_IMAGE_WIDTH'] = 800
        flask_app.config['PUBLIC_MAX_IMAGE_HEIGHT'] = 800
        # Landscape image should be width limited
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertLess(h, w)
        self.assertEqual(w, 800)
        # Portrait image should be height limited
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertLess(w, h)
        self.assertEqual(h, 800)
        # Explicitly enabling padding should give the exact limit
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&autosizefit=0')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 800)
        self.assertEqual(h, 800)
        # Small images should be unaffected
        rv = self.app.get('/image?src=test_images/quru470.png&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 470)
        self.assertEqual(h, 300)
        # Being logged in should not enforce any restriction
        self.login('admin', 'admin')
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 1600)
        self.assertEqual(h, 1200)

    # Test serving of public image with a template and lower public limits
    def test_template_public_image_lower_limits(self):
        flask_app.config['PUBLIC_MAX_IMAGE_WIDTH'] = 100
        flask_app.config['PUBLIC_MAX_IMAGE_HEIGHT'] = 100
        # Just template should serve at the template size (not be limited)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 200)
        self.assertEqual(h, 200)
        # Size beyond the template size should error
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png&width=250')
        self.assertEqual(rv.status_code, 400)
        # Size between limit and template size should be ok
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png&width=150')
        self.assertEqual(rv.status_code, 200)
        # Size lower than limit should be ok
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png&width=75')
        self.assertEqual(rv.status_code, 200)

    # Test serving of public image with a template and higher public limits
    def test_template_public_image_higher_limits(self):
        flask_app.config['PUBLIC_MAX_IMAGE_WIDTH'] = 500
        flask_app.config['PUBLIC_MAX_IMAGE_HEIGHT'] = 500
        # Just template should serve at the template size (as normal)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 200)
        self.assertEqual(h, 200)
        # Size beyond the limit should error
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png&width=600')
        self.assertEqual(rv.status_code, 400)
        # Size between template size and limit should be ok
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png&width=400')
        self.assertEqual(rv.status_code, 200)
        # Size lower than template size should be ok
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=smalljpeg&format=png&width=100')
        self.assertEqual(rv.status_code, 200)

    # Test serving of public image with a template without any width/height defined
    def test_template_public_image_defaults(self):
        flask_app.config['PUBLIC_MAX_IMAGE_WIDTH'] = 800
        flask_app.config['PUBLIC_MAX_IMAGE_HEIGHT'] = 800
        # Create a blank template
        dm.save_object(ImageTemplate('Blank', '', {}))
        im.reset_templates()
        # Just template should serve at the image size (below limit)
        rv = self.app.get('/image?src=test_images/quru470.png&tmp=blank&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 470)
        self.assertEqual(h, 300)
        # Just template should serve at the limit size (image larger than limit)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=blank&format=png')
        self.assertEqual(rv.status_code, 200)
        (w, h) = get_png_dimensions(rv.data)
        self.assertEqual(w, 800)
        self.assertEqual(h, 600)
        # Up to limit should be ok
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=blank&format=png&width=600')
        self.assertEqual(rv.status_code, 200)
        # Over the limit should error
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=blank&format=png&width=900')
        self.assertEqual(rv.status_code, 400)

    # Test serving of original image
    def test_serve_original_image(self):
        rv = self.app.get('/original?src=test_images/cathedral.jpg')
        assert rv.status_code == 200
        assert 'image/jpeg' in rv.headers['Content-Type'], 'HTTP headers do not specify image/jpeg'
        assert len(rv.data) == 648496, 'Returned original image length is incorrect'
        assert rv.headers.get('Content-Length') == '648496'

    # Test stripping of metadata
    def test_info_strip(self):
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=200&strip=0')
        assert rv.status_code == 200
        orig_len = len(rv.data)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=200&strip=1')
        assert rv.status_code == 200
        assert len(rv.data) < orig_len, 'Stripped image is not smaller than the original'

    # #4705 Test that stripping of RGB colour profiles does not cause major colour loss
    def test_rgb_profile_strip(self):
        rv = self.app.get('/image?src=test_images/profile-pro-photo.jpg&width=900&height=600&format=png&quality=9&strip=0')
        assert rv.status_code == 200
        orig_len = len(rv.data)
        rv = self.app.get('/image?src=test_images/profile-pro-photo.jpg&width=900&height=600&format=png&quality=9&strip=1')
        assert rv.status_code == 200
        assert len(rv.data) < orig_len, 'Stripped image is not smaller than the original'
        # Now ensure it looks correct (not all dark and dull)
        self.assertImageMatch(rv.data, 'strip-rgb-profile.png')

    # Test attachment option
    def test_attach_image(self):
        rv = self.app.get('/image?src=test_images/cathedral.jpg&attach=1')
        assert rv.status_code == 200
        assert rv.headers.get('Content-Disposition') is not None
        assert 'attachment' in rv.headers['Content-Disposition']
        assert 'filename="cathedral.jpg"' in rv.headers['Content-Disposition']
        # Repeat for original
        rv = self.app.get('/original?src=test_images/cathedral.jpg&attach=1')
        assert rv.status_code == 200
        assert rv.headers.get('Content-Disposition') is not None
        assert 'attachment' in rv.headers['Content-Disposition']
        assert 'filename="cathedral.jpg"' in rv.headers['Content-Disposition']

    # Test simple resize
    def test_resize_image(self):
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=500')
        assert rv.status_code == 200
        image_dims = get_png_dimensions(rv.data)
        assert image_dims[0] == 500  # Should be 500x375
        assert image_dims[1] == 375
        # Test with and without auto-size-fit
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=500&height=500')
        assert rv.status_code == 200
        image_dims = get_png_dimensions(rv.data)
        assert image_dims[0] == 500  # Should be 500x500
        assert image_dims[1] == 500
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=500&height=500&autosizefit=1')
        assert rv.status_code == 200
        image_dims = get_png_dimensions(rv.data)
        assert image_dims[0] == 500  # Should be 500x375 again
        assert image_dims[1] == 375
        # 0 means "keep original size"
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=0&height=0')
        assert rv.status_code == 200
        image_dims = get_png_dimensions(rv.data)
        assert image_dims[0] == 1600
        assert image_dims[1] == 1200

    # v1.24 #2219 http://www.4p8.com/eric.brasseur/gamma.html
    def test_resize_image_gamma(self):
        rv = self.app.get('/image?src=test_images/gamma_dalai_lama_gray_tft.jpg&format=png&width=150')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'gamma_dalai_lama_150.png')

    # Test the alignment within a filled image
    def test_align_centre_param(self):
        # Get default padded image
        url = '/image?src=test_images/cathedral.jpg&format=png&strip=0&width=600&height=400&left=0.2&right=0.8&fill=white'
        rv = self.app.get(url)
        assert rv.status_code == 200
        default_size = len(rv.data)
        # Check default mode is centre aligned
        rv = self.app.get(url + '&halign=C0.5&valign=C0.5')
        assert rv.status_code == 200
        assert len(rv.data) == default_size

    # Test the alignment within a filled image
    def test_align_param(self):
        url = '/image?src=test_images/cathedral.jpg&format=png&strip=0&width=600&height=400&left=0.2&right=0.8&fill=white'
        # Align right
        rv = self.app.get(url + '&halign=R1')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'align-right.png')
        # Check image does not get chopped off
        rv = self.app.get(url + '&halign=L1')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'align-right.png')
        # Align left-ish
        rv = self.app.get(url + '&halign=L0.1')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'align-left-10.png')

    # Test error handling on alignment parameters
    def test_align_invalid_params(self):
        url = '/image?src=test_images/cathedral.jpg&width=600&height=400&left=0.2&right=0.8'
        # Try some invalid values
        rv = self.app.get(url + '&halign=L1.1')
        assert rv.status_code == 400
        rv = self.app.get(url + '&halign=0')
        assert rv.status_code == 400
        rv = self.app.get(url + '&halign=T0')
        assert rv.status_code == 400
        rv = self.app.get(url + '&halign=LR0')
        assert rv.status_code == 400
        rv = self.app.get(url + '&valign=B1.01')
        assert rv.status_code == 400
        rv = self.app.get(url + '&valign=Z0.5')
        assert rv.status_code == 400
        rv = self.app.get(url + '&valign=L1')
        assert rv.status_code == 400
        rv = self.app.get(url + '&valign=T0.1.2')
        assert rv.status_code == 400

    # Test resized, cropped, filled image
    def test_cropped_image(self):
        url = '/image?src=test_images/cathedral.jpg&format=png&width=500&height=500&top=0.1&bottom=0.9&left=0.1&right=0.9&fill=0000ff'
        rv = self.app.get(url)
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'crop-test-1.png')
        # Test that auto-crop-fit takes effect
        url += '&autocropfit=1'
        rv = self.app.get(url)
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'crop-test-2.png')

    # Test tiled image
    def test_tiled_image(self):
        # Empty the cache prior to testing base image creation
        test_img = auto_sync_file('test_images/cathedral.jpg', dm, tm)
        assert test_img is not None and test_img.status == Image.STATUS_ACTIVE
        im._uncache_image(ImageAttrs(test_img.src, test_img.id))
        # Test by comparing tiles vs the equivalent crops
        url_topleft_crop = '/image?src=test_images/cathedral.jpg&format=png&right=0.5&bottom=0.5'
        url_botright_crop = '/image?src=test_images/cathedral.jpg&format=png&left=0.5&top=0.5'
        url_topleft_tile = '/image?src=test_images/cathedral.jpg&format=png&tile=1:4'
        url_botright_tile = '/image?src=test_images/cathedral.jpg&format=png&tile=4:4'
        # Get all
        rv_topleft_crop = self.app.get(url_topleft_crop)
        rv_botright_crop = self.app.get(url_botright_crop)
        rv_topleft_tile = self.app.get(url_topleft_tile)
        rv_botright_tile = self.app.get(url_botright_tile)
        # Check success
        assert rv_topleft_crop.status_code == 200
        assert rv_botright_crop.status_code == 200
        assert rv_topleft_tile.status_code == 200
        assert rv_botright_tile.status_code == 200
        # Check matches
        assert len(rv_topleft_crop.data) == len(rv_topleft_tile.data)
        assert len(rv_botright_crop.data) == len(rv_botright_tile.data)
        # Also check a tile of a resized crop
        url = '/image?src=test_images/cathedral.jpg&format=png&left=0.24&right=0.8&width=600&tile=1:4'
        rv = self.app.get(url)
        assert rv.status_code == 200
        tile_dims = get_png_dimensions(rv.data)
        assert tile_dims[0] == 600 / 2            # tile 1:4 == 1 of 2 wide x 2 high
        # v1.12.1094 Check the tile creation also created a base image ready for the other tiles
        image_obj = auto_sync_existing_file('test_images/cathedral.jpg', dm, tm)
        tile_base_attrs = ImageAttrs(
            # the same but without the tile spec
            image_obj.src, image_obj.id, iformat='png', left=0.24, right=0.8, width=600
        )
        im.finalise_image_attrs(tile_base_attrs)
        base_img = cm.get(tile_base_attrs.get_cache_key())
        assert base_img is not None

    # Test rotated image
    def test_rotated_image(self):
        im.reset_image(ImageAttrs('test_images/cathedral.jpg'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=500&angle=-90')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'rotated.png')
        # Regression - test that floats are allowed
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=100&angle=45.5')
        assert rv.status_code == 200

    # Test flipped image
    def test_flipped_image(self):
        im.reset_image(ImageAttrs('test_images/dorset.jpg'))
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=500&flip=h')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'flip-h.png')
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=500&angle=90&flip=v')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'flip-v-rotated.png')

    # Test multi-page handling
    def test_page_param(self):
        img_url = '/image?src=test_images/multipage.tif&format=png&width=800&strip=1'
        rv = self.app.get(img_url + '&page=1')
        assert rv.status_code == 200
        page_1_len = len(rv.data)
        rv = self.app.get(img_url + '&page=2')
        assert rv.status_code == 200
        assert len(rv.data) != page_1_len
        self.assertImageMatch(rv.data, 'multi-page-2.png')

    # Test change of format
    def test_format_image(self):
        test_url = '/image?src=test_images/cathedral.jpg&width=500&format=png'
        rv = self.app.get(test_url)
        assert rv.status_code == 200
        assert 'image/png' in rv.headers['Content-Type'], 'HTTP headers do not specify image/png'
        self.assertImageMatch(rv.data, 'width-500.png')

    # Progressive JPG tests
    def test_pjpeg_format(self):
        bl_rv = self.app.get('/image?src=test_images/dorset.jpg&strip=0&quality=100')
        prog_rv = self.app.get('/image?src=test_images/dorset.jpg&strip=0&quality=100&format=pjpg')
        self.assertEqual(bl_rv.status_code, 200)
        self.assertEqual(prog_rv.status_code, 200)
        # Test the returned mime type is correct
        self.assertIn('image/jpeg', prog_rv.headers['Content-Type'])
        # Test the image looks like the original baseline JPG
        orig_file = os.path.join(
            os.path.abspath(flask_app.config['IMAGES_BASE_DIR']),
            'test_images',
            'dorset.jpg'
        )
        self.assertImageMatch(prog_rv.data, orig_file)
        # For this image, progressive encoding is smaller than baseline
        self.assertLess(len(prog_rv.data), len(bl_rv.data))
        # Returned filenames should end in .jpg, not .pjpg
        prog_rv = self.app.get('/image?src=test_images/dorset.jpg&strip=0&quality=100&format=pjpg&attach=1')
        self.assertEqual(prog_rv.status_code, 200)
        self.assertIn('filename="dorset.jpg"', prog_rv.headers['Content-Disposition'])
        # The pjpg images should be cached as pjpg, also check pjpeg ==> pjpg
        prog_attrs = ImageAttrs('test_images/dorset.jpg', 1, iformat='pjpeg')
        prog_attrs.normalise_values()
        self.assertIn('Fpjpg', prog_attrs.get_cache_key())

    # Issue #528 - converting a PNG with transparency to JPG should not alter the image dimensions
    def test_alpha_png_to_jpeg(self):
        test_url = '/image?src=/test_images/quru470.png&width=300&height=300&format=jpg&quality=100'
        rv = self.app.get(test_url)
        assert rv.status_code == 200
        # We should of course get a 300x300 image (and not a 300x469!)
        self.assertImageMatch(rv.data, 'quru300.jpg')

    # Issue #648 - crop + rotate should do the right thing
    def test_crop_and_rotate(self):
        cm.clear()
        test_url = '/image?src=/test_images/dorset.jpg&angle=45&top=0.2&bottom=0.8&format=png'
        rv = self.app.get(test_url)
        assert rv.status_code == 200
        # convert dorset.jpg -rotate 45 -quality 75 dorset-45.png
        # convert dorset-45.png -gravity center -crop x60% output.png
        if self.imagemagick_version() < MAGICK_ROTATION_VERSION:
            # On RHEL 6, IM 654 to 672 gives a blurry old thing
            self.assertImageMatch(rv.data, 'rotate-crop-im654.png')
        else:
            # Produced with IM 684, sharp
            self.assertImageMatch(rv.data, 'rotate-crop.png')

    # Issue #648 - crop + rotate + resize should also do the right thing
    def test_crop_and_rotate_and_resize(self):
        cm.clear()
        test_url = '/image?src=/test_images/dorset.jpg&angle=45&top=0.2&bottom=0.8&width=450&height=450&format=png'
        rv = self.app.get(test_url)
        assert rv.status_code == 200
        # Given dorset.jpg rotated at 45 deg (see above)...
        # convert dorset-45.png -gamma 0.454545 -gravity center -crop x60% -resize 450x450 -extent 450x450 -gamma 2.2 output.png
        if self.imagemagick_version() < MAGICK_ROTATION_VERSION:
            self.assertImageMatch(rv.data, 'rotate-crop-450-im654.png')
        else:
            self.assertImageMatch(rv.data, 'rotate-crop-450.png')

    # Issue #513 - performing sequence of cropping + rotation should give consistent results
    def test_crop_and_rotate_sequence(self):
        cm.clear()
        # Load a cropped image with no rotation
        test_url = '/image?src=/test_images/dorset.jpg&angle=0&top=0.2&bottom=0.8&width=450&height=450&format=png'
        rv = self.app.get(test_url)
        assert rv.status_code == 200
        # Load the same with rotation
        # With issue #513 this incorrectly used the former as a base image (resulting
        # in the crop occurring before rotation rather than the documented sequence)
        test_url = '/image?src=/test_images/dorset.jpg&angle=45&top=0.2&bottom=0.8&width=450&height=450&format=png'
        rv = self.app.get(test_url)
        assert rv.status_code == 200
        # Check the result is what we expect (same as for test_crop_and_rotate_and_resize)
        if self.imagemagick_version() < MAGICK_ROTATION_VERSION:
            self.assertImageMatch(rv.data, 'rotate-crop-450-im654.png')
        else:
            self.assertImageMatch(rv.data, 'rotate-crop-450.png')

    # Test certain blank parameters are allowed - compatibility with existing applications
    def test_blank_params(self):
        # Angle just makes fill apply
        rv = self.app.get('/image?src=test_images/cathedral.jpg&angle=45&width=&height=&fill=&left=&right=&bottom=&top=')
        assert rv.status_code == 200

    # Test that the resize settings take effect
    def test_resize_system_setting(self):
        flask_app.config['IMAGE_RESIZE_QUALITY'] = 3
        img1 = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=800')
        self.assertEqual(img1.status_code, 200)
        self.assertIn('image/png', img1.headers['Content-Type'])
        # Delete img from cache
        im.reset_image(ImageAttrs('test_images/dorset.jpg'))
        # Re-generate it as img2 with resize quality 1
        flask_app.config['IMAGE_RESIZE_QUALITY'] = 1
        img2 = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=800')
        self.assertEqual(img2.status_code, 200)
        self.assertIn('image/png', img2.headers['Content-Type'])
        self.assertLess(len(img2.data), len(img1.data))

    # Test that PDF files can be read and converted
    # Also tests the page and dpi parameters
    # NOTE: Requires Ghostscript 9.04 or above (for PNG DownScaleFactor support)
    def test_pdf_support(self):
        tempfile = '/tmp/qis_pdf_image.png'
        pdfrelfile = 'test_images/pdftest.pdf'
        pdfabsfile = get_abs_path(pdfrelfile)
        pdfurl = '/image?src=' + pdfrelfile + '&format=png&quality=75&strip=0&page=7'
        # Reset
        def pdf_reset():
            try: os.remove(tempfile)
            except: pass
        # Test getting "image" dimensions - should be using PDF_BURST_DPI setting, default 150
        pdf_props = im.get_image_properties(pdfrelfile)
        assert pdf_props, 'Failed to read PDF properties'
        assert pdf_props['width'] in [1237, 1238], 'Converted image width is ' + str(pdf_props['width'])
        assert pdf_props['height'] == 1650, 'Converted image height is ' + str(pdf_props['height'])
        # Test dpi parameter takes effect for conversions
        rv = self.app.get(pdfurl + '&dpi=75')
        assert rv.status_code == 200, 'Failed to generate image from PDF'
        assert 'image/png' in rv.headers['Content-Type']
        png_size = get_png_dimensions(rv.data)
        assert png_size[0] in [618, 619], 'Converted image width is ' + str(pdf_props['width'])
        assert png_size[1] == 825, 'Converted image height is ' + str(pdf_props['height'])
        # Runs gs -dBATCH -dNOPAUSE -dNOPROMPT -sDEVICE=png16m -r450 -dDownScaleFactor=3 -dFirstPage=7 -dLastPage=7 -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dUseCropBox -sOutputFile=/tmp/qis_pdf_image.png ../images/test_images/pdftest.pdf
        pdf_reset()
        gs_params = [
            '-dBATCH', '-dNOPAUSE', '-dNOPROMPT',
            '-sDEVICE=png16m',
            '-r150', '-dDOINTERPOLATE',
            '-dFirstPage=7', '-dLastPage=7',
            '-dTextAlphaBits=4', '-dGraphicsAlphaBits=4',
            '-dUseCropBox',
            '-sOutputFile=' + tempfile,
            pdfabsfile
        ]
        assert self.call_gs(gs_params), 'Ghostcript conversion failed'
        rv = self.app.get(pdfurl + '&dpi=150')
        assert rv.status_code == 200, 'Failed to generate image from PDF'
        assert 'image/png' in rv.headers['Content-Type']
        self.assertImageMatch(rv.data, tempfile)
        pdf_reset()

    # Tests PDF bursting
    def test_pdf_bursting(self):
        # At 150 DPI the result varies between 1237x1650 and 1238x1650
        expect = (1238, 1650)

        src_file = get_abs_path('test_images/pdftest.pdf')
        dest_file = '/tmp/qis_pdftest.pdf'
        image_path = 'test_images/qis_pdftest.pdf'
        burst_path = 'test_images/qis_pdftest.pdf.d'
        # Login
        main_tests.setup_user_account('kryten', 'admin_files')
        self.login('kryten', 'kryten')
        try:
            # Upload a PDF
            shutil.copy(src_file, dest_file)
            rv = self.file_upload(self.app, dest_file, 'test_images')
            self.assertEqual(rv.status_code, 200)
            # Wait a short time for task to start
            time.sleep(15)
            # Check PDF images directory created
            assert path_exists(burst_path, require_directory=True), 'Burst folder has not been created'
            # Converting pdftest.pdf takes about 15 seconds
            time.sleep(20)
            # Check page 1 exists and looks like we expect
            rv = self.app.get('/original?src=' + burst_path + '/page-00001.png')
            assert rv.status_code == 200
            self.assertImageMatch(rv.data, 'pdf-page-1-%d.png' % expect[0])
            # Check page 1 actual dimensions - depends on PDF_BURST_DPI
            (w, h) = get_png_dimensions(rv.data)
            assert w == expect[0], 'Expected PDF dimensions of %dx%d @ 150 DPI' % expect
            assert h == expect[1], 'Expected PDF dimensions of %dx%d @ 150 DPI' % expect
            # Check page 27 exists and looks like we expect
            rv = self.app.get('/original?src=' + burst_path + '/page-00027.png')
            assert rv.status_code == 200
            # There is a thicker line in gs 9.16 than there was in 9.10
            p27_test_filename = 'pdf-page-27-%d%s.png' % (
                expect[0],
                '' if self.gs_version() < GS_LINES_VERSION else '-gs-916'
            )
            self.assertImageMatch(rv.data, p27_test_filename)
            # Check page 27 dimensions in the database
            rv = self.app.get('/api/details/?src=' + burst_path + '/page-00027.png')
            assert rv.status_code == API_CODES.SUCCESS
            obj = json.loads(rv.data.decode('utf8'))
            assert obj['data']['width'] == expect[0]
            assert obj['data']['height'] == expect[1]
        finally:
            # Delete temp file and uploaded file and burst folder
            if os.path.exists(dest_file):
                os.remove(dest_file)
            delete_file(image_path)
            delete_dir(burst_path, recursive=True)

    # Test support for reading digital camera RAW files
    # Requires qismagick v2.0.0+
    def test_nef_raw_file_support(self):
        # Get an 800w PNG copy
        rv = self.app.get('/image?src=test_images/nikon_raw.nef&format=png&width=800&strip=0')
        self.assertEqual(rv.status_code, 200)
        # Check expected result - actual (ImageMagick would only return the 160x120 jpeg preview)
        dims = get_png_dimensions(rv.data)
        self.assertEqual(dims[0], 800)
        self.assertImageMatch(rv.data, 'nikon-raw-800.png')
        # The image dimensions are really 2000x3008 (Mac Preview) or 2014x3039 (LibRaw)
        raw_props = im.get_image_properties('test_images/nikon_raw.nef', True)
        self.assertEqual(raw_props['width'], 2014)
        self.assertEqual(raw_props['height'], 3039)
        # EXIF data should be readable
        self.check_image_properties_dict(raw_props, 'TIFF', Model='NIKON D50')
        self.check_image_properties_dict(raw_props, 'EXIF', FNumber='4.2')

    # EXIF data should also be preserved for RAW file derivatives with strip=0
    # Requires qismagick v2.0.0+
    # TODO re-enable when ImageMagick keeps the meta data (or we implement manual EXIF transfer)
    @unittest.expectedFailure
    def test_nef_raw_file_converted_exif(self):
        rv = self.app.get('/image?src=test_images/nikon_raw.nef&format=png&width=800&strip=0')
        self.assertEqual(rv.status_code, 200)
        props = im.get_image_data_properties(rv.data, 'png', True)
        self.check_image_properties_dict(props, 'TIFF', Model='NIKON D50')
        self.check_image_properties_dict(props, 'EXIF', FNumber='4.2')

    # Test support for reading digital camera RAW files
    # Requires qismagick v2.0.0+
    def test_cr2_raw_file_support(self):
        # Get a full size PNG copy
        rv = self.app.get('/image?src=test_images/canon_raw.cr2&format=png&strip=0')
        self.assertEqual(rv.status_code, 200)
        # Check expected dimensions - actual
        dims = get_png_dimensions(rv.data)
        self.assertEqual(dims[0], 4770)
        self.assertEqual(dims[1], 3178)
        # Check expected dimensions - original file
        raw_props = im.get_image_properties('test_images/canon_raw.cr2', True)
        self.assertEqual(raw_props['width'], 4770)
        self.assertEqual(raw_props['height'], 3178)
        # EXIF data should be readable
        self.check_image_properties_dict(raw_props, 'TIFF', Model='Canon EOS 500D')
        self.check_image_properties_dict(raw_props, 'EXIF', FNumber='4.0')

    # EXIF data should also be preserved for RAW file derivatives with strip=0
    # Requires qismagick v2.0.0+
    # TODO re-enable when ImageMagick keeps the meta data (or we implement manual EXIF transfer)
    @unittest.expectedFailure
    def test_cr2_raw_file_converted_exif(self):
        rv = self.app.get('/image?src=test_images/canon_raw.cr2&format=png&strip=0')
        self.assertEqual(rv.status_code, 200)
        props = im.get_image_data_properties(rv.data, 'png', True)
        self.check_image_properties_dict(props, 'TIFF', Model='Canon EOS 500D')
        self.check_image_properties_dict(props, 'EXIF', FNumber='4.0')

    # Test watermarks, overlays - opacity 0
    def test_overlays_blank(self):
        # Get blank test image as reference
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&quality=75')
        self.assertEqual(rv.status_code, 200)
        original_len = len(rv.data)
        # Ensure that 0 opacity and 0 size don't error
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&quality=75&overlay=test_images/quru110.png&ovopacity=0&ovsize=0')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), original_len)

    # Test watermarks, overlays - should reject PDF as overlay image
    def test_overlays_no_pdf(self):
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&quality=75&overlay=test_images/pdftest.pdf')
        self.assertEqual(rv.status_code, 415)
        self.assertIn('not supported', rv.data.decode('utf8'))

    # Test watermarks, overlays - default overlay should be opaque, fit width, centered
    def test_overlays_default(self):
        # See http://www.imagemagick.org/Usage/annotating/#watermarking
        # composite -quality 75 -gravity center images/test_images/quru110.png images/test_images/dorset.jpg /tmp/qis_overlay_image.png
        img_url = '/image?src=test_images/dorset.jpg&format=png&quality=75&strip=0&overlay=test_images/quru110.png'
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/dorset.jpg')
        logo_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/quru110.png')
        magick_params = [
            '-quality', '75',
            '-gravity', 'center',
            logo_image,
            disk_image,
            '/tmp/qis_overlay_image.png'
        ]
        self.compare_composite(img_url, magick_params)

    # Test watermarks, overlays - compare vs ImageMagick dissolve
    def test_overlays_opacity_position(self):
        # See http://www.imagemagick.org/Usage/annotating/#watermarking
        # composite -quality 75 -dissolve 50% -gravity south images/test_images/quru110.png images/test_images/dorset.jpg /tmp/qis_overlay_image.png
        img_url = '/image?src=test_images/dorset.jpg&format=png&quality=75&strip=0&overlay=test_images/quru110.png&ovopacity=0.5&ovpos=s'
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/dorset.jpg')
        logo_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/quru110.png')
        magick_params = [
            '-quality', '75',
            '-dissolve', '50%',
            '-gravity', 'south',
            logo_image,
            disk_image,
            '/tmp/qis_overlay_image.png'
        ]
        self.compare_composite(img_url, magick_params)

    # #2319 Test watermarks, overlays - overlay should not get squished
    def test_overlays_not_squished(self):
        # where 720 is 60% of the original height of cathedral.jpg
        # convert \( images/test_images/cathedral.jpg -crop 100%x60%+0+0 \) \( images/test_images/copyright.png -resize x720 \) -gravity center -quality 75 -composite /tmp/qis_overlay_image.png
        img_url = '/image?src=test_images/cathedral.jpg&bottom=0.6&format=png&quality=75&strip=0&overlay=test_images/copyright.png'
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/cathedral.jpg')
        logo_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/copyright.png')
        magick_params = [
            '(', disk_image, '-crop', '100%x60%+0+0', ')',
            '(', logo_image, '-resize', 'x720', ')',
            '-gravity', 'center',
            '-quality', '75',
            '-composite',
            '/tmp/qis_overlay_image.png'
        ]
        self.compare_convert(img_url, magick_params)

    # #515 An RGB image onto a CMYK image used to mess up the colours of the overlay image and opacity did not work
    @unittest.skipIf(imagemagick_version(None) <= 675, 'Older ImageMagicks do not correctly set the image gamma')
    def test_overlays_rgb_on_cmyk(self):
        # composite -quality 100 -gravity center \( images/test_images/quru470.png -profile icc/sRGB.icc -profile icc/USWebCoatedSWOP.icc \) \( images/test_images/picture-cmyk.jpg -resize 500 \) /tmp/qis_overlay_image.jpg
        img_url = '/image?src=/test_images/picture-cmyk.jpg&overlay=/test_images/quru470.png&ovopacity=1&format=jpg&quality=100&width=500&strip=0&colorspace=cmyk'
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/picture-cmyk.jpg')
        logo_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/quru470.png')
        rgb_icc = os.path.join(flask_app.config['ICC_BASE_DIR'], 'sRGB.icc')
        cmyk_icc = os.path.join(flask_app.config['ICC_BASE_DIR'], 'USWebCoatedSWOP.icc')
        magick_params = [
            '-quality', '100',
            '-gravity', 'center',
            '(', logo_image, '-profile', rgb_icc, '-profile', cmyk_icc, ')',
            '(', disk_image, '-resize', '500', ')',
            '/tmp/qis_overlay_image.jpg'
        ]
        self.compare_composite(img_url, magick_params)

    # #515 A CMYK image onto RGB should correctly convert the colours of the CMYK to RGB
    @unittest.skipIf(imagemagick_version(None) <= 675, 'Older ImageMagicks do not correctly set the image gamma')
    def test_overlays_cmyk_on_rgb(self):
        rv = self.app.get('/image?src=/test_images/quru470.png&format=jpg&quality=100&overlay=/test_images/picture-cmyk.jpg&ovsize=1&ovopacity=0.5')
        self.assertEqual(rv.status_code, 200)
        self.assertImageMatch(rv.data, 'cmyk-on-rgb.jpg')

    # Test SVG overlays (requires ImageMagick compiled with librsvg)
    def test_svg_overlay(self):
        rv = self.app.get('/image?src=/test_images/blue bells.jpg&strip=0&format=png&width=800&overlay=/test_images/car.svg&ovsize=0.7&ovpos=s')
        self.assertEqual(rv.status_code, 200)
        # Different versions of rsvg (or maybe libcairo?) produce different output
        # There's no easy way of querying the library versions so try both known variations
        try:
            self.assertImageMatch(rv.data, 'svg-overlay-1.png')
        except AssertionError:
            self.assertImageMatch(rv.data, 'svg-overlay-2.png')

    # Test reading image profile data
    def test_image_profile_properties(self):
        profile_data = im.get_image_properties('test_images/cathedral.jpg', True)
        assert 'width' in profile_data and 'height' in profile_data
        assert profile_data['width'] == 1600
        assert profile_data['height'] == 1200
        assert 'EXIF' in profile_data
        assert ('Make', 'Nokia') in profile_data['EXIF']
        assert ('ExposureMode', 'Auto Exposure') in profile_data['EXIF']

    # Test ICC colour profiles and colorspace parameter
    def test_icc_profiles(self):
        tempfile = '/tmp/qis_icc_image.jpg'
        # ICC test, compares a generated image with the IM version
        def icc_test(img_url, magick_params, tolerance=46):
            # Generate ICC image with ImageMagick
            assert self.call_im_convert(magick_params), 'ImageMagick convert failed'
            # Generate the same with the image server
            rv = self.app.get(img_url)
            assert rv.status_code == 200, 'Failed to generate ICC image: ' + rv.data.decode('utf8')
            assert 'image/jpeg' in rv.headers['Content-Type']
            self.assertImageMatch(rv.data, tempfile, tolerance)
            try: os.remove(tempfile)
            except: pass
        # See doc/ICC_tests.txt for more information and expected results
        # Test 1 - picture-cmyk.jpg - convert to sRGB with colorspace parameter
        # convert images/test_images/picture-cmyk.jpg -quality 100 -intent perceptual -profile icc/sRGB.icc /tmp/qis_icc_image.jpg
        img_url = '/image?src=test_images/picture-cmyk.jpg&format=jpg&quality=100&strip=0&colorspace=srgb'
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/picture-cmyk.jpg')
        disk_rgb = os.path.join(flask_app.config['ICC_BASE_DIR'], 'sRGB.icc')
        magick_params = [
            disk_image,
            '-quality', '100',
            '-intent', 'perceptual',
            '-profile', disk_rgb,
            tempfile
        ]
        icc_test(img_url, magick_params)
        # Test 2 - picture-cmyk.jpg - convert [inbuilt] to CoatedGRACoL2006 to sRGB
        # convert images/test_images/picture-cmyk.jpg -quality 100 -intent relative -black-point-compensation -profile icc/CoatedGRACoL2006.icc -sampling-factor 1x1 -intent perceptual -profile icc/sRGB.icc /tmp/qis_icc_image.jpg
        img_url = "/image?src=test_images/picture-cmyk.jpg&format=jpg&quality=100&strip=0&icc=CoatedGRACoL2006&intent=relative&bpc=1&colorspace=srgb"
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/picture-cmyk.jpg')
        disk_rgb = os.path.join(flask_app.config['ICC_BASE_DIR'], 'sRGB.icc')
        disk_cmyk = os.path.join(flask_app.config['ICC_BASE_DIR'], 'CoatedGRACoL2006.icc')
        magick_params = [
            disk_image,
            '-quality', '100',
            '-intent', 'relative',
            '-black-point-compensation',
            '-profile', disk_cmyk,
            '-sampling-factor', '1x1',
            '-intent', 'perceptual',
            '-profile', disk_rgb,
            tempfile
        ]
        icc_test(img_url, magick_params)
        # Test 3 - dorset.jpg - convert to CMYK with UncoatedFOGRA29
        # convert images/test_images/dorset.jpg -quality 100 -profile icc/sRGB.icc -intent relative -black-point-compensation -profile icc/UncoatedFOGRA29.icc -sampling-factor 1x1 /tmp/qis_icc_image.jpg
        img_url = "/image?src=test_images/dorset.jpg&format=jpg&quality=100&strip=0&icc=UncoatedFOGRA29&intent=relative&bpc=1"
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/dorset.jpg')
        disk_rgb = os.path.join(flask_app.config['ICC_BASE_DIR'], 'sRGB.icc')
        disk_cmyk = os.path.join(flask_app.config['ICC_BASE_DIR'], 'UncoatedFOGRA29.icc')
        magick_params = [
            disk_image,
            '-quality', '100',
            '-profile', disk_rgb,
            '-intent', 'relative',
            '-black-point-compensation',
            '-profile', disk_cmyk,
            '-sampling-factor', '1x1',
            tempfile
        ]
        icc_test(img_url, magick_params, 45)
        # Test 4 - dorset.jpg - convert to GRAY
        # convert images/test_images/dorset.jpg -quality 100 -profile icc/sRGB.icc -intent perceptual -profile icc/Greyscale.icm -sampling-factor 1x1 /tmp/qis_icc_image.jpg
        img_url = "/image?src=test_images/dorset.jpg&format=jpg&quality=100&strip=0&icc=Greyscale&intent=perceptual"
        disk_image = os.path.join(flask_app.config['IMAGES_BASE_DIR'], 'test_images/dorset.jpg')
        disk_rgb = os.path.join(flask_app.config['ICC_BASE_DIR'], 'sRGB.icc')
        disk_gray = os.path.join(flask_app.config['ICC_BASE_DIR'], 'Greyscale.icm')
        magick_params = [
            disk_image,
            '-quality', '100',
            '-profile', disk_rgb,
            '-intent', 'perceptual',
            '-profile', disk_gray,
            '-sampling-factor', '1x1',
            tempfile
        ]
        icc_test(img_url, magick_params)
