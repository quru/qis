# -*- coding: utf-8 -*-
#
# Quru Image Server
#
# Document:      tests.py
# Date started:  05 Apr 2011
# By:            Matt Fozard
# Purpose:       Contains the image server development test suite
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
# 18Aug2011  Matt  Require test settings file, reset databases before running tests
# 05Oct2012  Matt  Added API tests class
# 16Nov2012  Matt  Added system permission tests
# 19Feb2013  Matt  Added folder permission tests
# 13Aug2013  Matt  Replaced file size checks with image comparison checks
# 28Sep2015  Matt  Moved API tests into test_api.py
# 26Aug2016  Matt  Moved web page tests into test_web_pages.py
#

import os

# Do not use the base or any other current environment settings,
# as we'll be clearing down the database
TESTING_SETTINGS = 'unit_tests'
os.environ['QIS_SETTINGS'] = TESTING_SETTINGS

# Possible paths to ImageMagick binaries, in order of preference
IMAGEMAGICK_PATHS = [
    "/opt/ImageMagick/bin/",  # QIS custom build (currently unused)
    "/usr/local/bin/",        # Installed from source
    ""                        # Default / first found in the PATH
]

print("Importing imageserver libraries")

import binascii
import json
import shutil
import signal
import subprocess
import tempfile
import time
import timeit
import unittest

import mock
import flask
from werkzeug.http import http_date

# Assign global managers, same as the main app uses
from imageserver.flask_app import app as flask_app
from imageserver.flask_app import logger as lm
from imageserver.flask_app import cache_engine as cm
from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import image_engine as im
from imageserver.flask_app import task_engine as tm
from imageserver.flask_app import permissions_engine as pm

from imageserver.api_util import API_CODES
from imageserver.errors import AlreadyExistsError
from imageserver.filesystem_manager import (
    get_abs_path, copy_file, delete_dir, delete_file
)
from imageserver.filesystem_manager import path_exists, make_dirs
from imageserver.filesystem_sync import (
    auto_sync_existing_file, auto_sync_file, auto_sync_folder
)
from imageserver.flask_util import internal_url_for
from imageserver.image_attrs import ImageAttrs
from imageserver.models import (
    Folder, Group, User, Image, ImageHistory, ImageTemplate,
    FolderPermission, SystemPermissions
)
from imageserver.permissions_manager import _trace_to_str
from imageserver.session_manager import get_session_user
from imageserver.scripts.cache_util import delete_image_ids
from imageserver.template_attrs import TemplateAttrs


# http://www.imagemagick.org/script/changelog.php
# "2011-11-07 6.7.3-4 RotateImage() now uses distorts rather than shears."
# Note: based on the change log, this number is a guess rather than a known fact
MAGICK_ROTATION_VERSION = 673

# At some point from 9.14 to 9.16 Ghostscript draws thicker lines than before
GS_LINES_VERSION = 914


# For nose
def setup():
    reset_databases()
    cm.clear()


def teardown():
    # Kill the aux child processes
    this_pid = os.getpid()
    p = subprocess.Popen(
        ['pgrep', '-g', str(this_pid)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output = p.communicate()
    output = (output[1] or output[0])
    child_pids = [p for p in output.split() if p != str(this_pid)]
    for pid in child_pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except:
            print("Failed to kill child process %s" % pid)


# Utility - delete and re-create the internal databases
def reset_databases():
    assert flask_app.config['TESTING'], \
        'Testing settings have not been applied, not clearing the database!'

    cm._drop_db()
    dm._drop_db()
    cm._init_db()
    dm._init_db()
    # Set the admin password to something known so we can log in
    admin_user = dm.get_user(username='admin')
    admin_user.set_password('admin')
    dm.save_object(admin_user)
    # Default the public root folder permissions to allow View + Download
    set_default_public_permission(FolderPermission.ACCESS_DOWNLOAD)
    # Set some standard image generation settings
    reset_default_image_template()


def set_default_public_permission(access):
    default_fp = dm.get_object(FolderPermission, 1)
    default_fp.access = access
    dm.save_object(default_fp)
    pm.reset()


def reset_default_image_template():
    default_it = dm.get_image_template(tempname='Default')
    # Use reasonably standard image defaults
    image_defaults = [
        ('format', 'jpg'), ('quality', 75), ('colorspace', None),
        ('dpi_x', None), ('dpi_y', None), ('strip', False),
        ('record_stats', True),
        ('expiry_secs', 60 * 60 * 24 * 7)
    ]
    # Clear default template then apply our defaults
    default_it.template = {}
    for (key, value) in image_defaults:
        default_it.template[key] = {'value': value}
    dm.save_object(default_it)
    # Clear template cache
    im.reset_templates()


# Returns the first of paths+app_name that exists, else app_name
def get_app_path(app_name, paths):
    app_path = app_name
    for p in paths:
        try_path = os.path.join(p, app_name)
        if os.path.exists(try_path):
            app_path = try_path
            break
    return app_path


# Utility - create/reset a test user having a certain system permission
def setup_user_account(login_name, user_type='none', allow_api=False):
    db_session = dm.db_get_session()
    try:
        # Get or create user
        testuser = dm.get_user(
            username=login_name,
            load_groups=True,
            _db_session=db_session
        )
        if not testuser:
            testuser = User(
                'Kryten', 'Testing Droid', 'kryten@reddwarf.galaxy',
                login_name, login_name,
                User.AUTH_TYPE_PASSWORD,
                allow_api,
                User.STATUS_ACTIVE
            )
            dm.create_user(testuser, _db_session=db_session)
        else:
            testuser.allow_api = allow_api
            testuser.status = User.STATUS_ACTIVE
        # Wipe system permissions
        testgroup = dm.get_group(groupname='Red Dwarf', _db_session=db_session)
        if not testgroup:
            testgroup = Group(
                'Red Dwarf',
                'Test group',
                Group.GROUP_TYPE_LOCAL
            )
            dm.create_group(testgroup, _db_session=db_session)
        testgroup.permissions = SystemPermissions(
            testgroup, False, False, False, False, False, False, False
        )
        # Wipe folder permissions
        del testgroup.folder_permissions[:]
        # Apply permissions for requested test type
        if user_type == 'none':
            pass
        elif user_type == 'admin_users':
            testgroup.permissions.admin_users = True
        elif user_type == 'admin_files':
            testgroup.permissions.admin_files = True
        elif user_type == 'admin_permissions':
            testgroup.permissions.admin_users = True
            testgroup.permissions.admin_permissions = True
        elif user_type == 'admin_all':
            testgroup.permissions.admin_all = True
        else:
            raise ValueError('Unimplemented test user type ' + user_type)
        dm.save_object(testgroup, _db_session=db_session)
        testuser.groups = [testgroup]
        dm.save_object(testuser, _db_session=db_session)
        db_session.commit()
    finally:
        db_session.close()
        # Clear old cached user permissions
        pm.reset()


# Utility - invoke ImageMagick convert command, wait for completion,
#           and return a boolean indicating success
def call_im_convert(args_list):
    args_list.insert(0, get_app_path('convert', IMAGEMAGICK_PATHS))
    return subprocess.call(args_list) == 0


# Utility - invoke ImageMagick composite command, wait for completion,
#           and return a boolean indicating success
def call_im_composite(args_list):
    args_list.insert(0, get_app_path('composite', IMAGEMAGICK_PATHS))
    return subprocess.call(args_list) == 0


# Utility - returns the ImageMagick library version as an integer, e.g. 654 for v6.5.4
def imagemagick_version():
    import imageserver.imagemagick as magick
    # Assumes format "ImageMagick version: 654, Ghostscript delegate: 9.10"
    return int(magick.imagemagick_get_version_info()[21:24])


# Utility - returns the Ghostscript application version as an integer, e.g. 910 for v9.10
def gs_version():
    import imageserver.imagemagick as magick
    # Assumes format "ImageMagick version: 654, Ghostscript delegate: 9.10"
    return int(float(magick.imagemagick_get_version_info()[-4:]) * 100)


def compare_images(img_path1, img_path2):
    diff_temp_fd, diff_temp_nm = tempfile.mkstemp('.png')
    os.close(diff_temp_fd)

    # Generate diff image
    p = subprocess.Popen(
        [
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
    if errmsg:
        raise ValueError('Compare generation error: ' + errmsg)

    # Get metrics about the diff image
    p = subprocess.Popen(
        [
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
    result = output[1].strip()
    os.remove(diff_temp_nm)
    # ImageMagick compare switched "identical" PSNR to 0 in 6.9.5-4 and to "inf" in 6.9.7-10
    psnr = float(result) if result not in ('0', 'inf') else 1000
    return psnr


# Utility - invoke Ghostscript gs command, wait for completion,
#           and return a boolean indicating success
def call_gs(args_list):
    args_list.insert(0, flask_app.config['GHOSTSCRIPT_PATH'])
    return subprocess.call(args_list) == 0


# Utility - return the interesting bit of a login page HTML
def get_login_error(html):
    fromidx = html.find("<div class=\"error")
    toidx = html.find("</div>", fromidx)
    return html[fromidx:toidx + 6]


# Utility - returns a tuple of (width, height) of a PNG image
def get_png_dimensions(png_data):
    if png_data[1:6] != b'PNG\r\n':
        raise ValueError('Provided data is not a PNG image')
    wbin = png_data[16:20]
    hbin = png_data[20:24]
    return (int(binascii.hexlify(wbin), 16), int(binascii.hexlify(hbin), 16))


class FlaskTestCase(unittest.TestCase):
    def setUp(self):
        # Restore original settings before each test
        self.reset_settings()
        # Create a test client for our tests
        self.app = flask_app.test_client()

    def reset_settings(self):
        flask_app.config.from_object(flask.Flask.default_config)
        flask_app.config.from_object('imageserver.conf.base_settings')
        flask_app.config.from_object('imageserver.conf.' + TESTING_SETTINGS)


class BaseTestCase(FlaskTestCase):
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
        except:
            # Save the unmatched image for evaluation
            compare_name = os.path.split(static_img)[1]
            shutil.copy(temp_img, '/tmp/match-test-fail-' + compare_name)
            raise
        finally:
            os.remove(temp_img)

    # Utility - perform a log in via the web page
    def login(self, usr, pwd):
        rv = self.app.post('/login/', data={
            'username': usr,
            'password': pwd
        })
        # 302 = success redirect, 200 = login page with error message
        self.assertEqual(rv.status_code, 302, 'Login failed with response: ' + rv.data.decode('utf8'))

    # Utility - gets an API token
    def api_login(self, usr, pwd):
        rv = self.app.post('/api/token/', data={
            'username': usr,
            'password': pwd
        })
        # 200 = success, other = error
        self.assertEqual(rv.status_code, 200)
        obj = json.loads(rv.data.decode('utf8'))
        return obj['data']['token']

    # Utility - perform a log out
    def logout(self):
        rv = self.app.get('/logout/')
        # 302 = success redirect
        self.assertEqual(rv.status_code, 302)

    # Utility - uploads a file (provide the full path) to an image server
    # folder via the file upload API. Note that Flask includes the path in
    # the filename with slashes converted to underscores.
    # Returns the app.post() return value.
    def file_upload(self, app, src_file_path, dest_folder, overwrite=1):
        with open(src_file_path, 'rb') as infile:
            rv = app.post('/api/upload/', data={
                'files': infile,
                'path': dest_folder,
                'overwrite': str(overwrite)
            })
        return rv

    # Utility - check that the keyword args/values are present in the given
    # dictionary of image properties (from ImageManager.get_image_properties)
    def check_image_properties_dict(self, props, profile, **kwargs):
        self.assertIn(profile, props)
        profile_dict = dict(props[profile])
        for k in kwargs:
            self.assertEqual(profile_dict[k], kwargs[k])

    # Compares a server generated image with the version generated by Imagemagick convert
    def compare_convert(self, img_url, magick_params):
        return self._compare_im_fn(call_im_convert, img_url, magick_params)

    # Compares a server generated image with the version generated by Imagemagick composite
    def compare_composite(self, img_url, magick_params):
        return self._compare_im_fn(call_im_composite, img_url, magick_params)

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


class ImageServerTestsSlow(BaseTestCase):
    # Test xref parameter
    def test_xref_parameter(self):
        # Make sure we have no test image A at width 50
        test_img = auto_sync_existing_file('test_images/cathedral.jpg', dm, tm)
        test_image_attrs = ImageAttrs(
            test_img.src, test_img.id, width=50,
            strip=False, dpi=0, iformat='jpg', quality=75,
            colorspace='rgb'
        )
        im.finalise_image_attrs(test_image_attrs)
        cache_img = cm.get(test_image_attrs.get_cache_key())
        assert cache_img is None, 'Test image was already in cache - cannot run test!'
        # Create a subprocess to handle the xref-generated http request
        temp_env = os.environ
        temp_env['QIS_SETTINGS'] = TESTING_SETTINGS
        rs_path = 'src/runserver.py' if os.path.exists('src/runserver.py') else 'runserver.py'
        inner_server = subprocess.Popen('python ' + rs_path, cwd='.', shell=True, env=temp_env)
        time.sleep(10)
        # Set the xref base URL so it will get generated if we pass the right thing as width
        flask_app.config['DEBUG'] = True
        flask_app.config['XREF_TRACKING_URL'] = \
            'http://127.0.0.1:5000' + \
            '/image?src=test_images/cathedral.jpg&strip=0&dpi=0&format=jpg&quality=75&colorspace=rgb&width='
        # Call a different image B passing in xref of 50
        rv = self.app.get('/image?src=test_images/dorset.jpg&xref=50')
        assert rv.status_code == 200
        # Wait a little for the background xref handling thread to complete
        time.sleep(5)
        # and kill the temporary subprocess
        inner_server.terminate()
        # Now the test image A should have been created
        cache_img = cm.get(test_image_attrs.get_cache_key())
        assert cache_img is not None, 'Failed to find ' + test_image_attrs.get_cache_key() + '. xref URL did not appear to be invoked.'


class ImageServerBackgroundTaskTests(BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super(ImageServerBackgroundTaskTests, cls).setUpClass()
        # Invoke @app.before_first_request to launch the aux servers
        flask_app.test_client().get('/')

    # Similar to test_db_auto_population, but with the emphasis
    # on auto-detecting external changes to the file system
    def test_db_auto_sync(self):
        temp_folder = 'test_auto_sync'
        temp_file_1 = temp_folder + '/image1.jpg'
        temp_file_2 = temp_folder + '/image2.jpg'
        try:
            # Create a new folder and copy 2 images into it
            make_dirs(temp_folder)
            copy_file('test_images/cathedral.jpg', temp_file_1)
            copy_file('test_images/dorset.jpg', temp_file_2)
            # View the images
            rv = self.app.get('/image?src=' + temp_file_1)
            assert rv.status_code == 200
            rv = self.app.get('/image?src=' + temp_file_2)
            assert rv.status_code == 200
            # We should now have a folder db record, 2x image db records
            db_folder = dm.get_folder(folder_path=temp_folder)
            db_file_1 = dm.get_image(src=temp_file_1, load_history=True)
            db_file_2 = dm.get_image(src=temp_file_2, load_history=True)
            assert db_folder and db_file_1 and db_file_2
            assert db_folder.status == Folder.STATUS_ACTIVE and \
                db_file_1.status == Image.STATUS_ACTIVE and \
                db_file_2.status == Image.STATUS_ACTIVE
            # Should have image creation history
            assert len(db_file_1.history) == 1
            assert len(db_file_2.history) == 1
            # Save the IDs for checking later
            prev_folder_id = db_folder.id
            prev_image_id_1 = db_file_1.id
            prev_image_id_2 = db_file_2.id
            # Delete the folder from disk
            delete_dir(temp_folder, recursive=True)
            # View 1 image original to trigger a disk read
            rv = self.app.get('/original?src=' + temp_file_1)
            assert rv.status_code == 404
            # This should have triggered a background task to delete all data for temp_folder.
            # Wait a short time for the task to complete.
            time.sleep(20)
            # The db records should all now be present but with status deleted,
            # including the folder and other image
            db_folder = dm.get_folder(folder_path=temp_folder)
            db_file_1 = dm.get_image(src=temp_file_1, load_history=True)
            db_file_2 = dm.get_image(src=temp_file_2, load_history=True)
            assert db_folder and db_file_1 and db_file_2
            assert db_folder.status == Folder.STATUS_DELETED and \
                db_file_1.status == Image.STATUS_DELETED and \
                db_file_2.status == Image.STATUS_DELETED
            # Also we should have image deletion history
            assert len(db_file_1.history) == 2
            assert len(db_file_2.history) == 2
            # Check we get 404 for images (that the cached images are cleared)
            rv = self.app.get('/image?src=' + temp_file_1)
            assert rv.status_code == 404
            rv = self.app.get('/image?src=' + temp_file_2)
            assert rv.status_code == 404
            # Restore the folder and one image
            make_dirs(temp_folder)
            copy_file('test_images/cathedral.jpg', temp_file_1)
            # View the image (this may actually be a 404 but should detect the disk changes)
            self.app.get('/image?src=' + temp_file_1)
            # These db records should now be status active (same records with same IDs)
            db_folder = dm.get_folder(folder_path=temp_folder)
            db_file_1 = dm.get_image(src=temp_file_1, load_history=True)
            db_file_2 = dm.get_image(src=temp_file_2, load_history=True)
            assert db_folder and db_file_1 and db_file_2
            assert db_folder.id == prev_folder_id and \
                db_file_1.id == prev_image_id_1 and \
                db_file_2.id == prev_image_id_2
            assert db_folder.status == Folder.STATUS_ACTIVE and \
                db_file_1.status == Image.STATUS_ACTIVE
            # And with image re-creation history
            assert len(db_file_1.history) == 3
            # But with the unviewed image still deleted at present
            assert db_file_2.status == Image.STATUS_DELETED
            assert len(db_file_2.history) == 2
        finally:
            delete_dir(temp_folder, recursive=True)

    # Test the auto-pyramid generation, which is really a specialist case of
    # test_base_image_detection with the base image generated as a background task
    def test_auto_pyramid(self):
        image_obj = auto_sync_existing_file('test_images/dorset.jpg', dm, tm)
        orig_attrs = ImageAttrs(image_obj.src, image_obj.id)
        im.finalise_image_attrs(orig_attrs)
        w500_attrs = ImageAttrs(image_obj.src, image_obj.id, width=500)
        im.finalise_image_attrs(w500_attrs)
        # Clean
        cm.clear()
        im.reset_image(orig_attrs)
        # Get the original
        rv = self.app.get('/image?src=test_images/dorset.jpg')
        assert rv.status_code == 200
        orig_len = len(rv.data)
        # Only the original should come back as base for a 500 version
        base = im._get_base_image(w500_attrs)
        assert base is None or len(base.data()) == orig_len
        # Set the minimum auto-pyramid threshold and get a tile of the image
        flask_app.config["AUTO_PYRAMID_THRESHOLD"] = 1000000
        rv = self.app.get('/image?src=test_images/dorset.jpg&tile=1:4')
        assert rv.status_code == 200
        # Wait a bit for the pyramiding to finish
        time.sleep(25)
        # Now check the cache again for a base for the 500 version
        base = im._get_base_image(w500_attrs)
        assert base is not None, 'Auto-pyramid did not generate a smaller image'
        # And it shouldn't be the original image either
        assert len(base.data()) < orig_len
        assert base.attrs().width() is not None
        assert base.attrs().width() < 1600 and base.attrs().width() >= 500

    # Tests PDF bursting
    def test_pdf_bursting(self):
        # At 150 DPI the result varies between 1237x1650 and 1238x1650
        expect = (1238, 1650)

        src_file = get_abs_path('test_images/pdftest.pdf')
        dest_file = '/tmp/qis_pdftest.pdf'
        image_path = 'test_images/tmp_qis_pdftest.pdf'
        burst_path = 'test_images/tmp_qis_pdftest.pdf.d'
        # Login
        setup_user_account('kryten', 'admin_files')
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
                '' if gs_version() < GS_LINES_VERSION else '-gs-916'
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


class ImageServerTestsRegressions(BaseTestCase):
    @unittest.expectedFailure
    def test_jpg_to_png(self):
        """
        Converting a JPG to a PNG should result in an identical output.

        Older versions of Magick had some odd colourspace / ICC profile
        related bugs that caused the PNG to be washed out.

        Compare 3 of our test images. The PSNR should be infinite but we cheat
        and use 1000 to work around any minor differences in decoding.
        """
        tempfile = '/tmp/qis_png_image.png'
        images = ["cathedral.jpg", "blue bells.jpg", "picture-cmyk.jpg"]

        try:
            for image in images:
                jpg = self.app.get(
                    '/image?src=test_images/%s&format=jpg&width=640&quality=100&colorspace=srgb&strip=0' % image
                )
                self.assertEqual(jpg.status_code, 200)
                png = self.app.get(
                    '/image?src=test_images/%s&format=png&width=640&quality=100&colorspace=srgb&strip=0' % image
                )
                self.assertEqual(png.status_code, 200)
                self.assertNotEqual(jpg.data, png.data)
                with open(tempfile, 'wb') as f:
                    f.write(png.data)
                self.assertImageMatch(jpg.data, tempfile, 1000)
        finally:
            if os.path.exists(tempfile):
                os.remove(tempfile)


class ImageServerTestsFast(BaseTestCase):
    def test_upload_usage_stats(self):
        from imageserver.tasks import upload_usage_stats

        flask_app.config['USAGE_DATA_URL'] = 'http://dummy.url/'
        with mock.patch('requests.post') as mockpost:
            upload_usage_stats(logger=lm, data_manager=dm, settings=flask_app.config)

            mockpost.assert_called_once_with(mock.ANY, data=mock.ANY, timeout=mock.ANY)
            mock_args = mockpost.call_args
            stats = json.loads(mock_args[1]['data'])
            self.assertIn('version', stats)
            self.assertIn('host_id', stats)
            self.assertIn('stats', stats)
            self.assertIn('time', stats)
            self.assertIn('hash', stats)

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
        assert image_dims[0] == 500 # Should be 500x375
        assert image_dims[1] == 375
        # Test with and without auto-size-fit
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=500&height=500')
        assert rv.status_code == 200
        image_dims = get_png_dimensions(rv.data)
        assert image_dims[0] == 500 # Should be 500x500
        assert image_dims[1] == 500
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=png&width=500&height=500&autosizefit=1')
        assert rv.status_code == 200
        image_dims = get_png_dimensions(rv.data)
        assert image_dims[0] == 500 # Should be 500x375 again
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
        url_topleft_crop  = '/image?src=test_images/cathedral.jpg&format=png&right=0.5&bottom=0.5'
        url_botright_crop = '/image?src=test_images/cathedral.jpg&format=png&left=0.5&top=0.5'
        url_topleft_tile  = '/image?src=test_images/cathedral.jpg&format=png&tile=1:4'
        url_botright_tile = '/image?src=test_images/cathedral.jpg&format=png&tile=4:4'
        # Get all
        rv_topleft_crop  = self.app.get(url_topleft_crop)
        rv_botright_crop = self.app.get(url_botright_crop)
        rv_topleft_tile  = self.app.get(url_topleft_tile)
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
        if imagemagick_version() < MAGICK_ROTATION_VERSION:
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
        if imagemagick_version() < MAGICK_ROTATION_VERSION:
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
        if imagemagick_version() < MAGICK_ROTATION_VERSION:
            self.assertImageMatch(rv.data, 'rotate-crop-450-im654.png')
        else:
            self.assertImageMatch(rv.data, 'rotate-crop-450.png')

    # Test certain blank parameters are allowed - compatibility with existing applications
    def test_blank_params(self):
        # Angle just makes fill apply
        rv = self.app.get('/image?src=test_images/cathedral.jpg&angle=45&width=&height=&fill=&left=&right=&bottom=&top=')
        assert rv.status_code == 200

    # Test basic caching
    def test_basic_caching(self):
        test_url = '/image?src=test_images/cathedral.jpg&width=413&format=png'
        rv = self.app.get(test_url)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.headers['X-From-Cache'], 'False')
        t1_usec = int(rv.headers['X-Time-Taken'])
        def get_from_cache():
            self.app.get(test_url)
        t2 = timeit.Timer(get_from_cache).timeit(1)
        self.assertLess(t2, 0.050, 'Cached png took more than 50ms to return')
        rv = self.app.get(test_url)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.headers['X-From-Cache'], 'True')
        t3_usec = int(rv.headers['X-Time-Taken'])
        # Cached internal time should be quicker than generated internal time
        self.assertLess(t3_usec, t1_usec)
        # Internal time taken (cached) should be lte total request time (cached)
        self.assertLessEqual(t3_usec / 1000000.0, t2)

    # Test cache parameter
    # v1.34 now only supported when logged in
    def test_cache_param(self):
        test_url = '/image?src=test_images/cathedral.jpg&width=123'
        test_img = auto_sync_existing_file('test_images/cathedral.jpg', dm, tm)
        test_attrs = ImageAttrs(test_img.src, test_img.id, width=123)
        im.finalise_image_attrs(test_attrs)
        # v1.34 when not logged in this param should be ignored
        cm.clear()
        rv = self.app.get(test_url + '&cache=0')
        self.assertEqual(rv.status_code, 200)
        cached_image = cm.get(test_attrs.get_cache_key())
        self.assertIsNotNone(cached_image)
        # When logged in the param should be respected
        cm.clear()
        setup_user_account('kryten', 'none')
        self.login('kryten', 'kryten')
        rv = self.app.get(test_url + '&cache=0')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.headers['X-From-Cache'], 'False')
        # Should not yet be in cache
        cached_image = cm.get(test_attrs.get_cache_key())
        self.assertIsNone(cached_image, 'Image was cached when cache=0 was specified')
        # Request with cache=1 (default)
        rv = self.app.get(test_url)
        self.assertEqual(rv.status_code, 200)
        # Should be in cache now
        cached_image = cm.get(test_attrs.get_cache_key())
        self.assertIsNotNone(cached_image)

    # Test re-cache parameter
    # v1.34 re-cache is only enabled with BENCHMARKING=True
    def test_recache_param(self):
        # So in v1.34 the param should be ignored by default
        url = '/image?src=test_images/dorset.jpg&width=50'
        rv = self.app.get(url)
        self.assertEqual(rv.status_code, 200)
        rv = self.app.get(url + '&recache=1')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.headers['X-From-Cache'], 'True')  # not re-cached
        # Now enable recache and get on with the test
        flask_app.config['BENCHMARKING'] = True
        # Create a new test image to use
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = get_abs_path('test_images/test_image.jpg')
        shutil.copy(src_file, dst_file)
        i = None
        try:
            # Get an image
            url = '/image?src=test_images/test_image.jpg&width=500'
            rv = self.app.get(url)
            self.assertEqual(rv.status_code, 200)
            self.assertEqual(rv.headers['X-From-Cache'], 'False')
            # Get it again
            rv = self.app.get(url)
            self.assertEqual(rv.status_code, 200)
            self.assertEqual(rv.headers['X-From-Cache'], 'True')
            # Get it again with re-cache
            rv = self.app.get(url + '&recache=1')
            self.assertEqual(rv.status_code, 200)
            self.assertEqual(rv.headers['X-From-Cache'], 'False')
            # Get it again
            rv = self.app.get(url)
            self.assertEqual(rv.status_code, 200)
            self.assertEqual(rv.headers['X-From-Cache'], 'True')
            # Delete the file
            os.remove(dst_file)
            # Get it again (should actually work, returned from cache)
            rv = self.app.get(url)
            self.assertEqual(rv.status_code, 200)
            # Get it again with re-cache (delete should now be detected)
            rv = self.app.get(url + '&recache=1')
            self.assertEqual(rv.status_code, 404)
            # Get it again (check the cache was cleared)
            rv = self.app.get(url)
            self.assertEqual(rv.status_code, 404)
            # Check that the database knows it's deleted
            i = dm.get_image(src='test_images/test_image.jpg', load_history=True)
            self.assertIsNotNone(i)
            self.assertEqual(i.status, Image.STATUS_DELETED)
            self.assertGreater(len(i.history), 0)
            self.assertEqual(i.history[-1].action, ImageHistory.ACTION_DELETED)
        finally:
            if os.path.exists(dst_file):
                os.remove(dst_file)
            if i:
                dm.delete_image(i, True)

    # Test no params
    def test_no_src(self):
        rv = self.app.get('/image')
        assert rv.status_code == 400
        rv = self.app.get('/original')
        assert rv.status_code == 400

    # Test 403 on insecure src param
    def test_insecure_src(self):
        # Should be permission denied unless running as root
        rv = self.app.get('/image?src=~root/../../../etc/passwd')
        self.assertEqual(rv.status_code, 403)
        rv = self.app.get('/original?src=~root/../../../etc/passwd')
        self.assertEqual(rv.status_code, 403)
        # Might be readable by anyone
        rv = self.app.get('/image?src=../../../../../../../../../etc/passwd')
        self.assertEqual(rv.status_code, 403)
        rv = self.app.get('/original?src=../../../../../../../../../etc/passwd')
        self.assertEqual(rv.status_code, 403)

    # Test 403 on insecure unicode src param
    def test_unicode_insecure_src(self):
        # Should be permission denied unless running as root
        rv = self.app.get('/image?src=~root/../../../etc/pâßßwd')
        self.assertEqual(rv.status_code, 403)
        rv = self.app.get('/original?src=~root/../../../etc/pâßßwd')
        self.assertEqual(rv.status_code, 403)
        # Might be readable by anyone
        rv = self.app.get('/image?src=../../../../../../../../../etc/pâßßwd')
        self.assertEqual(rv.status_code, 403)
        rv = self.app.get('/original?src=../../../../../../../../../etc/pâßßwd')
        self.assertEqual(rv.status_code, 403)

    # Test 404 on invalid src param
    def test_404_src(self):
        rv = self.app.get('/image?src=test_images/none_existent.jpg')
        self.assertEqual(rv.status_code, 404)
        rv = self.app.get('/original?src=test_images/none_existent.jpg')
        self.assertEqual(rv.status_code, 404)

    # #1864 Ensure unicode garbage URLs return 404 (thanks script kiddies)
    def test_unicode_404_src(self):
        rv = self.app.get('/image?src=swëdish/dørset.jpg')
        self.assertEqual(rv.status_code, 404)
        self.assertIn('swëdish/dørset.jpg', rv.data.decode('utf8'))
        rv = self.app.get('/original?src=swëdish/dørset.jpg')
        self.assertEqual(rv.status_code, 404)
        self.assertIn('swëdish/dørset.jpg', rv.data.decode('utf8'))

    # #2517 Test that a/b.jpg is /a/b.jpg is /a//b.jpg
    # #2517 Test that /a/b/c.jpg is /a//b/c.jpg is /a///b/c.jpg
    def test_src_dup_seps(self):
        test_cases = [
            {
                'try_images': [
                    'test_images/cathedral.jpg',
                    '/test_images/cathedral.jpg',
                    '/test_images//cathedral.jpg'
                ],
                'try_folders': [
                    'test_images',
                    '/test_images',
                    'test_images//'
                ]
            },
            {
                'try_images': [
                    'test_images/subfolder/cathedral.jpg',
                    '/test_images//subfolder/cathedral.jpg',
                    '/test_images///subfolder/cathedral.jpg'
                ],
                'try_folders': [
                    'test_images/subfolder',
                    'test_images//subfolder',
                    'test_images///subfolder'
                ]
            }
        ]
        # Create test_images/subfolder/cathedral.jpg
        make_dirs('test_images/subfolder')
        copy_file('test_images/cathedral.jpg', 'test_images/subfolder/cathedral.jpg')
        # Run tests
        try:
            for test_case in test_cases:
                image_ids = []
                folder_ids = []
                for image_src in test_case['try_images']:
                    rv = self.app.get('/image?src=' + image_src)
                    self.assertEqual(rv.status_code, 200)
                    rv = self.app.get('/api/v1/details/?src=' + image_src)
                    self.assertEqual(rv.status_code, 200)
                    obj = json.loads(rv.data.decode('utf8'))
                    image_ids.append(obj['data']['id'])
                for folder_path in test_case['try_folders']:
                    db_folder = dm.get_folder(folder_path=folder_path)
                    self.assertIsNotNone(db_folder)
                    folder_ids.append(db_folder.id)
                # Image IDs should all be the same
                self.assertEqual(len(image_ids), 3)
                self.assertEqual(image_ids[0], image_ids[1])
                self.assertEqual(image_ids[1], image_ids[2])
                # Folder IDs should all be the same
                self.assertEqual(len(folder_ids), 3)
                self.assertEqual(folder_ids[0], folder_ids[1])
                self.assertEqual(folder_ids[1], folder_ids[2])
        finally:
            delete_dir('test_images/subfolder', recursive=True)

    # Test buffer overflow protection on string params
    def test_overflow_params(self):
        buf = 'a' * 1025
        rv = self.app.get('/image?src=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/original?src=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&overlay=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        buf = 'a' * 257
        rv = self.app.get('/image?src=test_images/test.jpg&format=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not a valid choice', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&tmp=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not a valid choice', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&angle=1&fill=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&icc=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not a valid choice', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&ovpos=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not a valid choice', rv.data.decode('utf8'))

    # #1864 Test buffer overflow protection on unicode string params (thanks script kiddies)
    def test_unicode_overflow_params(self):
        buf = 'ø' * 1025
        rv = self.app.get('/image?src=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/original?src=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&overlay=' + buf)
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))

    # Test bad params
    def test_bad_params(self):
        rv = self.app.get('/image?src=test_images/test.jpg&width=99999')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&height=-10')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&top=1.1')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/test.jpg&bottom=-0.5')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&format=eggs')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not a valid choice', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=500&height=500&fill=spam')
        self.assertEqual(rv.status_code, 415)
        self.assertIn('unsupported fill colour', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tmp=eggs_and_spam')
        self.assertEqual(rv.status_code, 400)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&icc=eggs_and_spam')
        self.assertEqual(rv.status_code, 400)
        rv = self.app.get('/image?src=test_images/cathedral.jpg&overlay=eggs_and_spam')
        self.assertEqual(rv.status_code, 404)
        self.assertIn('not found', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&ovopacity=1.1')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&ovsize=-0.5')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&icc=AdobeRGB1998&intent=perceptive')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not a valid choice', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tile=5')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('invalid format', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tile=1:400')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tile=1:12')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not square', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tile=0:9')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&tile=10:9')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&page=-1')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&page=1024768')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('out of range', rv.data.decode('utf8'))
        rv = self.app.get('/image?src=test_images/cathedral.jpg&flip=x')
        self.assertEqual(rv.status_code, 400)
        self.assertIn('not a valid choice', rv.data.decode('utf8'))

    # #2590 Some clients request "x=1&amp;y=2" instead of "x=1&y=2"
    def test_bad_query_string(self):
        # Get an image correctly
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=100&height=100&format=png')
        self.assertEqual(rv.status_code, 200)
        self.assertIn('image/png', rv.headers['Content-Type'])
        self.assertEqual(rv.headers['X-From-Cache'], 'False')
        image_len = len(rv.data)
        # This incorrect URL should now retrieve the same image
        rv = self.app.get('/image?src=test_images/cathedral.jpg&amp;width=100&amp;height=100&amp;format=png')
        self.assertEqual(rv.status_code, 200)
        self.assertIn('image/png', rv.headers['Content-Type'])
        self.assertEqual(rv.headers['X-From-Cache'], 'True')
        self.assertEqual(len(rv.data), image_len)

    # Ensure that cache key values are normalised and handled properly
    def test_cache_keys(self):
        # Floats should be rounded to 0.0000x
        f = 0.123456789
        i = ImageAttrs(
            '', 1,
            rotation=f, top=f, left=f, bottom=f, right=f,
            overlay_size=f, overlay_opacity=f,
            overlay_src='grr'  # So the overlay params get kept
        )
        ov_hash = str(hash('grr'))
        self.assertEqual(
            i.get_cache_key(),
            'IMG:1,O0.12346,T0.12346,L0.12346,B0.12346,R0.12346,Y' + ov_hash + ',YO0.12346,YS0.12346'
        )
        # Smallest numbers should be 0.00005 not 5e-05
        f = 0.00001
        i = ImageAttrs('', 1, rotation=f, top=f, left=f, bottom=f, right=f)
        self.assertEqual(i.get_cache_key(), 'IMG:1,O0.00001,T0.00001,L0.00001,B0.00001,R0.00001')
        # Tiny values should be rounded to 0 then removed
        f = 0.0000001
        i = ImageAttrs('', 1, rotation=f, top=f, left=f, bottom=f, right=f)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        # Currently we encode 1.0 as "1.0" rather than "1"
        i = ImageAttrs('', 1, rotation=1.0)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1,O1.0')
        # Blank strings should be left out
        i = ImageAttrs(
            '', 1, iformat='', template='', align_h='', align_v='', flip='',
            fill='', overlay_src='', icc_profile='', icc_intent='',
            colorspace='', tile_spec=''
        )
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        # 0 and 1 crop marks should be left out
        i = ImageAttrs('', 1, top=0, left=0, bottom=1, right=1)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        # Rotation 0 or 360 should be left out
        i = ImageAttrs('', 1, rotation=0)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        i = ImageAttrs('', 1, rotation=360)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        # Fill should be left out when not resizing both dimensions
        i = ImageAttrs('', 1, width=200, height=200, fill='#0000ff')
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1,W200,H200,I#0000ff')
        i = ImageAttrs('', 1, width=200, fill='#0000ff')
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1,W200')
        # Hidden or 0 size overlay cancels overlay
        ov_hash = str(hash('grr'))
        i = ImageAttrs('', 1, overlay_src='grr', overlay_opacity=0.9, overlay_size=0.9)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1,Y' + ov_hash + ',YO0.9,YS0.9')
        i = ImageAttrs('', 1, overlay_src='grr', overlay_opacity=0, overlay_size=1)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        i = ImageAttrs('', 1, overlay_src='grr', overlay_opacity=1, overlay_size=0)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        # No ICC name cancels ICC params
        i = ImageAttrs('', 1, icc_profile='grr', icc_intent='relative', icc_bpc=True)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1,Pgrr,Nrelative,C')
        i = ImageAttrs('', 1, icc_profile='', icc_intent='relative', icc_bpc=True)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')

    # Test requested image attributes get applied and processed properly
    def test_image_attrs_precedence(self):
        ia = ImageAttrs('myimage.png', -1, width=789, fill='auto')
        # Apply a fictional template
        ia.apply_dict({
            'width': 100,
            'rotation': 360,
            'fill': 'red',
            'dpi_x': 300,
            'dpi_y': 300},
            override_values=False,
            normalise=False
        )
        # Ensure the template params are there
        self.assertEqual(ia.rotation(), 360)
        self.assertEqual(ia.dpi(), 300)
        # Ensure the initial parameters override the template
        self.assertEqual(ia.width(), 789)
        self.assertEqual(ia.fill(), 'auto')
        # Ensure the net parameters look good
        ia.normalise_values()
        self.assertIsNone(ia.format_raw())
        self.assertEqual(ia.format(), 'png')  # from filename, not params
        self.assertEqual(ia.width(), 789)
        self.assertEqual(ia.dpi(), 300)
        self.assertIsNone(ia.rotation())      # 360 would have no effect
        self.assertIsNone(ia.fill())          # As there's no rotation and no other filling to do
        # Check a 0 DPI does overrides the template
        ia = ImageAttrs('myimage.png', -1, dpi=0)
        ia.apply_dict({
            'dpi_x': 300,
            'dpi_y': 300},
            override_values=False,
            normalise=True
        )
        self.assertIsNone(ia.dpi())

    # Test the identification of suitable base images in cache
    def test_base_image_detection(self):
        image_obj = auto_sync_existing_file('test_images/dorset.jpg', dm, tm)
        image_id = image_obj.id
        # Clean
        orig_attrs = ImageAttrs('test_images/dorset.jpg', image_id)
        im.reset_image(orig_attrs)
        # Set up tests
        w1000_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=1000, rotation=90)
        w500_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, rotation=90)
        w100_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=100, rotation=90)
        base = im._get_base_image(im.finalise_image_attrs(w1000_attrs))
        assert base is None, 'Found an existing base image for ' + str(w1000_attrs)
        # Get an 1100 image, should provide the base for 1000
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=1100&angle=90')
        assert rv.status_code == 200
        base = im._get_base_image(im.finalise_image_attrs(w1000_attrs))
        assert base is not None and base.attrs().width() == 1100
        # Get 1000 image, should provide the base for 500
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=1000&angle=90')
        assert rv.status_code == 200
        base = im._get_base_image(im.finalise_image_attrs(w500_attrs))
        assert base is not None and base.attrs().width() == 1000
        # Get 500 image, should provide the base for 100
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=500&angle=90')
        assert rv.status_code == 200
        base = im._get_base_image(im.finalise_image_attrs(w100_attrs))
        assert base is not None and base.attrs().width() == 500
        # Make sure none of these come back for incompatible image requests
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500)  # No rotation
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='bmp', width=500, rotation=90)  # Format
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, height=500, rotation=90)  # Aspect ratio
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, rotation=90, fill='#ff0000')  # Fill
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        # But if we want to sharpen the 500px version that should be OK
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, rotation=90, sharpen=200)
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        # Adding an overlay should be OK
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, rotation=90, overlay_src='test_images/quru110.png')
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        # Tiling!
        # Creating a tile of the 500px version should use the same as a base
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, rotation=90, tile_spec=(3,9))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        # Create that tile
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=500&angle=90&tile=3:9')
        assert rv.status_code == 200
        # A different format of the tile should not use the cached tile as a base
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='jpg', width=500, rotation=90, tile_spec=(3,9))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        # But a stripped version of the same tile should
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, rotation=90, tile_spec=(3,9), strip=True)
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().tile_spec() == (3, 9)

    # Test the identification of suitable base images in cache
    def test_overlay_base_image_detection(self):
        image_obj = auto_sync_existing_file('test_images/dorset.jpg', dm, tm)
        image_id = image_obj.id
        # Clean
        orig_attrs = ImageAttrs('test_images/dorset.jpg', image_id)
        im.reset_image(orig_attrs)
        #
        # Overlays - We cannot allow an overlayed image to be use as a base, because:
        #            a) After resizing, the resulting overlay size might not be correct
        #            b) When cropping, rotating, blurring, flipping etc, the operation would already
        #               include the overlay, while normally (without a base) the overlay is done last
        #
        # The only exception is tiling, which can (and should!) use the exact same image as a base
        #
        w1000_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=1000, overlay_src='test_images/quru110.png')
        im.finalise_image_attrs(w1000_attrs)
        base = im._get_base_image(w1000_attrs)
        assert base is None, 'Found an existing base image for ' + str(w1000_attrs)
        # Get an 1100 image, which should NOT provide the base for 1000
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=1100&overlay=test_images/quru110.png')
        assert rv.status_code == 200
        base = im._get_base_image(w1000_attrs)
        assert base is None
        # Get a 500 image, we should be able to tile from it
        rv = self.app.get('/image?src=test_images/dorset.jpg&format=png&width=500&overlay=test_images/quru110.png')
        assert rv.status_code == 200
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='png', width=500, overlay_src='test_images/quru110.png', tile_spec=(1,4))
        im.finalise_image_attrs(try_attrs)
        base = im._get_base_image(try_attrs)
        assert base is not None and base.attrs().width() == 500

    # Test the identification of suitable base images in cache
    def test_flip_base_image_detection(self):
        #
        # Run some similar tests for newer parameters (flip and page)
        #
        image_obj = auto_sync_existing_file('test_images/multipage.tif', dm, tm)
        image_id = image_obj.id
        # Clean
        orig_attrs = ImageAttrs('test_images/multipage.tif', image_id)
        im.reset_image(orig_attrs)
        # Set up tests
        w500_attrs = ImageAttrs('test_images/multipage.tif', image_id, page=2, iformat='png', width=500, flip='v')
        im.finalise_image_attrs(w500_attrs)
        base = im._get_base_image(w500_attrs)
        assert base is None, 'Found an existing base image for ' + str(w500_attrs)
        # Get an 800 image, p2, flip v
        rv = self.app.get('/image?src=test_images/multipage.tif&format=png&width=800&page=2&flip=v')
        assert rv.status_code == 200
        self.assertImageMatch(rv.data, 'multi-page-2-800-flip-v.png')
        # Should be able to use the 800 as a base for a 500
        base = im._get_base_image(w500_attrs)
        assert base is not None and base.attrs().width() == 800
        # Generate the 500
        rv = self.app.get('/image?src=test_images/multipage.tif&format=png&width=500&page=2&flip=v')
        assert rv.status_code == 200
        # Make sure none of these come back for incompatible image requests
        try_attrs = ImageAttrs('test_images/multipage.tif', image_id, iformat='png', width=500)  # No page
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        try_attrs = ImageAttrs('test_images/multipage.tif', image_id, page=2, iformat='png', width=500, flip='h')  # Wrong flip
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        try_attrs = ImageAttrs('test_images/multipage.tif', image_id, page=3, iformat='png', width=500, flip='v')  # Wrong page
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is None
        # But if we want to sharpen the 500px version that should be OK
        try_attrs = ImageAttrs('test_images/multipage.tif', image_id, page=2, iformat='png', width=500, flip='v', sharpen=200)
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        # Adding an overlay should be OK
        try_attrs = ImageAttrs('test_images/multipage.tif', image_id, page=2, iformat='png', width=500, flip='v', overlay_src='test_images/quru110.png')
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        # Creating a tile of the 500px version should use the same as a base
        try_attrs = ImageAttrs('test_images/multipage.tif', image_id, page=2, iformat='png', width=500, flip='v', tile_spec=(3,9))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500

    # There was a bug where "cmyk.jpg&colorspace=rgb" would be used as a base image
    # for "cmyk.jpg&icc=some_icc&colorspace=rgb" but this was incorrect because the
    # base image is then RGB instead of CMYK.
    def test_base_image_colorspaces(self):
        # Clean
        image_obj = auto_sync_existing_file('test_images/picture-cmyk.jpg', dm, tm)
        image_id = image_obj.id
        orig_attrs = ImageAttrs('test_images/picture-cmyk.jpg', image_id)
        im.reset_image(orig_attrs)
        # Set up tests
        w200_attrs = ImageAttrs('test_images/picture-cmyk.jpg',
                                image_id, iformat='jpg', width=200, colorspace='rgb')
        icc_attrs_1 = ImageAttrs('test_images/picture-cmyk.jpg',
                                 image_id, iformat='jpg', width=500, icc_profile='CoatedGRACoL2006')
        icc_attrs_2 = ImageAttrs('test_images/picture-cmyk.jpg',
                                 image_id, iformat='jpg', width=500, icc_profile='CoatedGRACoL2006',
                                 colorspace='rgb')
        cspace_attrs = ImageAttrs('test_images/picture-cmyk.jpg',
                                  image_id, iformat='jpg', width=500, colorspace='gray')
        # Get the orig_attrs image
        rv = self.app.get('/image?src=test_images/picture-cmyk.jpg&format=jpg&width=500&colorspace=rgb')
        self.assertEqual(rv.status_code, 200)
        # Now getting a width 200 of that should be OK
        base = im._get_base_image(im.finalise_image_attrs(w200_attrs))
        self.assertIsNotNone(base)
        # Getting an ICC version should not use the RGB base
        base = im._get_base_image(im.finalise_image_attrs(icc_attrs_1))
        self.assertIsNone(base)
        # Getting an RGB of the ICC version should not use the RGB base either
        base = im._get_base_image(im.finalise_image_attrs(icc_attrs_2))
        self.assertIsNone(base)
        # Getting a GRAY version should not use the RGB base
        base = im._get_base_image(im.finalise_image_attrs(cspace_attrs))
        self.assertIsNone(base)

    # Test the correct base images are used when creating tiles
    def test_tile_base_images(self):
        orig_img = auto_sync_existing_file('test_images/cathedral.jpg', dm, tm)
        orig_attrs = ImageAttrs(orig_img.src, orig_img.id)
        orig_id = orig_img.id
        # Clean
        im.reset_image(orig_attrs)
        # Generate 2 base images
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=1000&strip=0')
        assert rv.status_code == 200
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=500&strip=0')
        assert rv.status_code == 200
        # Test base image detection
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=800, tile_spec=(2,4))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 1000
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=800, rotation=180, flip='v', tile_spec=(2,4))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 1000
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=800, height=800, size_fit=True, strip=True, tile_spec=(2,4))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 1000
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=800, height=800, size_fit=True, strip=True, overlay_src='test_images/quru110.png', tile_spec=(2,4))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 1000
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=500, tile_spec=(18,36))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=500, rotation=180, tile_spec=(18,36))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=500, rotation=180, flip='v', tile_spec=(18,36))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=500, height=500, size_fit=True, strip=True, tile_spec=(18,36))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500
        try_attrs = ImageAttrs('test_images/cathedral.jpg', orig_id, width=500, height=500, size_fit=True, strip=True, overlay_src='test_images/quru110.png', tile_spec=(18,36))
        base = im._get_base_image(im.finalise_image_attrs(try_attrs))
        assert base is not None and base.attrs().width() == 500

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

    # Test changing the default template values
    def test_default_template_settings(self):
        try:
            db_def_temp = dm.get_image_template(tempname='Default')
            # Get img1 with explicit format and quality params
            img1 = self.app.get('/image?src=test_images/dorset.jpg&width=800&format=bmp&quality=50')
            self.assertEqual(img1.status_code, 200)
            self.assertIn('image/bmp', img1.headers['Content-Type'])
            # Get img2, no params but with defaults set to be the same as img1
            db_def_temp.template['format']['value'] = 'bmp'
            db_def_temp.template['quality']['value'] = 50
            dm.save_object(db_def_temp)
            im.reset_templates()
            img2 = self.app.get('/image?src=test_images/dorset.jpg&width=800')
            self.assertEqual(img2.status_code, 200)
            self.assertIn('image/bmp', img2.headers['Content-Type'])
            self.assertEqual(len(img1.data), len(img2.data))
            # Test keeping the original image format
            db_def_temp.template['format']['value'] = ''
            db_def_temp.template['quality']['value'] = 75
            dm.save_object(db_def_temp)
            im.reset_templates()
            img3 = self.app.get('/image?src=test_images/dorset.jpg&width=805')
            self.assertEqual(img3.status_code, 200)
            self.assertIn('image/jpeg', img3.headers['Content-Type'])
            img3_size = len(img3.data)
            # Test strip
            db_def_temp.template['strip']['value'] = True
            dm.save_object(db_def_temp)
            im.reset_templates()
            img4 = self.app.get('/image?src=test_images/dorset.jpg&width=805')
            self.assertEqual(img4.status_code, 200)
            self.assertLess(len(img4.data), img3_size)
        finally:
            reset_default_image_template()

    # Test the ETag header behaves as it should
    def test_etag(self):
        rv = self.app.get('/image?src=test_images/thames.jpg&width=800')
        assert rv.headers.get('ETag') is not None
        etag_800 = rv.headers.get('ETag')
        # Test same image
        rv = self.app.get('/image?src=test_images/thames.jpg&width=800')
        assert rv.headers.get('ETag') == etag_800
        # Test equivalent image
        rv = self.app.get('/image?src=test_images/thames.jpg&width=800&angle=360&format=jpg&left=0&right=1')
        assert rv.headers.get('ETag') == etag_800
        # Test slightly different image
        rv = self.app.get('/image?src=test_images/thames.jpg&width=810')
        assert rv.headers.get('ETag') != etag_800
        etag_810 = rv.headers.get('ETag')
        rv = self.app.get('/image?src=test_images/thames.jpg')
        assert rv.headers.get('ETag') != etag_800
        assert rv.headers.get('ETag') != etag_810
        etag_thames = rv.headers.get('ETag')
        # Test very different image
        rv = self.app.get('/image?src=test_images/cathedral.jpg')
        assert rv.headers.get('ETag') != etag_800
        assert rv.headers.get('ETag') != etag_810
        assert rv.headers.get('ETag') != etag_thames

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
        assert call_gs(gs_params), 'Ghostcript conversion failed'
        rv = self.app.get(pdfurl + '&dpi=150')
        assert rv.status_code == 200, 'Failed to generate image from PDF'
        assert 'image/png' in rv.headers['Content-Type']
        self.assertImageMatch(rv.data, tempfile)
        pdf_reset()

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
    @unittest.skipIf(imagemagick_version() <= 675, 'Older ImageMagicks do not correctly set the image gamma')
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
    @unittest.skipIf(imagemagick_version() <= 675, 'Older ImageMagicks do not correctly set the image gamma')
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

    # Test image templates
    def test_templates(self):
        try:
            template = 'Unit test template'
            # Utility to update a template in the database and reset the template manager cache
            def update_db_template(db_obj, update_dict):
                db_obj.template.update(update_dict)
                dm.save_object(db_obj)
                im.reset_templates()
            # Get the default template
            db_default_template = dm.get_image_template(tempname='Default')
            # Create a temporary template to work with
            db_template = ImageTemplate(template, 'Temporary template for unit testing', {})
            db_template = dm.save_object(db_template, refresh=True)
            # Test format - first use original format in default template
            update_db_template(db_default_template, {'format': {'value': ''}})
            rv = self.app.get('/image?src=test_images/thames.jpg')
            self.assertEqual(rv.status_code, 200)
            self.assertIn('image/jpeg', rv.headers['Content-Type'])
            # Test format from template
            update_db_template(db_template, {'format': {'value': 'png'}})
            self.assertIn(template, im.get_template_names())
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.status_code, 200)
            self.assertIn('image/png', rv.headers['Content-Type'])
            original_len = len(rv.data)
            # Test cropping from template makes it smaller
            update_db_template(db_template, {'top': {'value': 0.1}, 'left': {'value': 0.1},
                                             'bottom': {'value': 0.9}, 'right': {'value': 0.9}})
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.status_code, 200)
            cropped_len = len(rv.data)
            self.assertLess(cropped_len, original_len)
            # Test stripping the EXIF data makes it smaller again 2
            update_db_template(db_template, {'strip': {'value': True}})
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.status_code, 200)
            stripped_len = len(rv.data)
            self.assertLess(stripped_len, cropped_len)
            # Test resizing it small makes it smaller again 3
            update_db_template(db_template, {'width': {'value': 500}, 'height': {'value': 500}})
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.status_code, 200)
            resized_len = len(rv.data)
            self.assertLess(resized_len, stripped_len)
            # And that auto-fitting the crop then makes it slightly larger
            update_db_template(db_template, {'crop_fit': {'value': True}})
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.status_code, 200)
            autofit_crop_len = len(rv.data)
            self.assertGreater(autofit_crop_len, resized_len)
            # Test expiry settings - from the default template first
            update_db_template(db_default_template, {'expiry_secs': {'value': 99}})
            rv = self.app.get('/image?src=test_images/thames.jpg')
            self.assertEqual(rv.headers.get('Expires'), http_date(int(time.time() + 99)))
            # Test expiry settings from template
            update_db_template(db_template, {'expiry_secs': {'value': -1}})
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.headers.get('Expires'), http_date(0))
            # Test attachment settings from template
            update_db_template(db_template, {'attachment': {'value': True}})
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertIsNotNone(rv.headers.get('Content-Disposition'))
            self.assertIn('attachment', rv.headers['Content-Disposition'])
            # Test that URL params override the template
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template+'&format=bmp&attach=0')
            self.assertEqual(rv.status_code, 200)
            self.assertIn('image/bmp', rv.headers['Content-Type'])
            self.assertIsNone(rv.headers.get('Content-Disposition'))
            template_bmp_len = len(rv.data)
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template+'&format=bmp&width=600&height=600&attach=0')
            self.assertEqual(rv.status_code, 200)
            self.assertGreater(len(rv.data), template_bmp_len)
        finally:
            reset_default_image_template()

    # Test spaces in file names - serving and caching
    def test_filename_spaces(self):
        # Test serving and cache store
        rv = self.app.get('/image?src=test_images/blue%20bells.jpg')
        assert rv.status_code == 200, 'Filename with spaces was not served'
        assert 'image/jpeg' in rv.headers['Content-Type']
        # knowing length requires 'keep original' values in settings
        assert len(rv.data) == 904256
        # Test retrieval from cache
        blue_img = auto_sync_existing_file('test_images/blue bells.jpg', dm, tm)
        blue_attrs = ImageAttrs(blue_img.src, blue_img.id)
        im.finalise_image_attrs(blue_attrs)
        blue_image = cm.get(blue_attrs.get_cache_key())
        assert blue_image is not None, 'Filename with spaces was not retrieved from cache'
        assert len(blue_image) == 904256
        # Test attachment filename
        rv = self.app.get('/original?src=test_images/blue%20bells.jpg&attach=1')
        assert rv.status_code == 200
        assert rv.headers.get('Content-Disposition') is not None
        assert 'attachment' in rv.headers['Content-Disposition']
        assert 'filename="blue bells.jpg"' in rv.headers['Content-Disposition']
        # Test spaces in overlay images
        rv = self.app.get('/image?src=test_images/dorset.jpg&width=500&overlay=test_images/blue%20bells.jpg&ovsize=0.5')
        assert rv.status_code == 200, 'Overlay with spaces was not served'

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
            assert call_im_convert(magick_params), 'ImageMagick convert failed'
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

    # Test the original URL won't serve up non-image files
    def test_original_serving_bad_files(self):
        tempfile = get_abs_path('php.ini')
        try:
            # Create a php.ini
            with open(tempfile, 'w') as tfile:
                tfile.write('QIS TEST. This is my php.ini file containing interesting info.')
            # Test we can't now serve that up
            rv = self.app.get('/original?src=php.ini')
            self.assertEqual(rv.status_code, 415)
            self.assertIn('not a supported image', rv.data.decode('utf8'))
        finally:
            os.remove(tempfile)

    # Image management database tests
    def test_db_auto_population(self):
        folder_path = 'test_images'
        image_path = folder_path + '/cathedral.jpg'
        i = dm.get_image(src=image_path)
        if i: dm.delete_image(i, True)
        # Check db auto-populates from image URL
        rv = self.app.get('/image?src=' + image_path)
        assert rv.status_code == 200
        # Test folder now exists
        f = dm.get_folder(folder_path=folder_path)
        assert f is not None
        assert f.path == '/'+folder_path
        # Test image record now exists and has correct folder
        i = dm.get_image(src=image_path)
        assert i is not None
        assert i.src == image_path
        assert i.folder.id == f.id
        assert i.width == 1600
        assert i.height == 1200
        # Reset database for i
        dm.delete_image(i, True)
        assert dm.get_image(src=image_path) is None
        # Check db auto-populates from details API
        rv = self.app.get('/api/details/?src=' + image_path)
        assert rv.status_code == 200
        i = dm.get_image(src=image_path, load_history=True)
        assert i is not None and i.width == 1600 and i.height == 1200, 'db has '+str(i)
        # Image history should be written for this one
        assert len(i.history) == 1
        assert i.history[0].action == ImageHistory.ACTION_CREATED
        # Reset
        dm.delete_image(i, True)
        assert dm.get_image(src=image_path) is None
        # Check db auto-populates from original URL
        rv = self.app.get('/original?src=' + image_path)
        assert rv.status_code == 200
        i = dm.get_image(src=image_path)
        assert i is not None and i.width == 1600 and i.height == 1200, 'db has '+str(i)
        # Reset
        dm.delete_image(i, True)
        assert dm.get_image(src=image_path) is None
        # Log in
        self.login('admin', 'admin')
        # Check db auto-populates from details page
        rv = self.app.get('/details/?src=' + image_path)
        assert rv.status_code == 200, 'Details page returned status ' + str(rv.status_code)
        i = dm.get_image(src=image_path)
        assert i is not None and i.width == 1600 and i.height == 1200, 'db has '+str(i)
        # Reset
        dm.delete_image(i, True)
        assert dm.get_image(src=image_path) is None
        # Check db auto-populates from an image upload
        temp_file = '/tmp/qis_uploadfile.jpg'
        image_path = 'test_images/tmp_qis_uploadfile.jpg'
        try:
            i = dm.get_image(src=image_path)
            assert i is None
            # Create image to upload, upload it
            src_file = get_abs_path('test_images/cathedral.jpg')
            shutil.copy(src_file, temp_file)
            rv = self.file_upload(self.app, temp_file, 'test_images')
            self.assertEqual(rv.status_code, 200)
            i = dm.get_image(src=image_path, load_history=True)
            assert i is not None and i.width == 1600 and i.height == 1200, 'after upload, db has '+str(i)
            uploaded_id = i.id
            # Check image history
            assert len(i.history) == 1
            assert i.history[0].action == ImageHistory.ACTION_CREATED
            assert i.history[0].user is not None
            assert i.history[0].user.username == 'admin'
            # Get an image and ensure it adds a cache entry for it
            rv = self.app.get('/image?src=' + image_path)
            assert rv.status_code == 200
            cache_entries = cm.search(searchfield1__eq=uploaded_id)
            assert len(cache_entries) > 0
            # Check db re-populates from a replacement image upload
            src_file = get_abs_path('test_images/dorset.jpg')
            shutil.copy(src_file, temp_file)
            rv = self.file_upload(self.app, temp_file, 'test_images')
            self.assertEqual(rv.status_code, 200)
            i = dm.get_image(src=image_path, load_history=True)
            assert i is not None and i.id == uploaded_id, 'db returned different record after re-upload: '+str(i)
            assert i.width == 1200 and i.height == 1600, 'after re-upload, db has '+str(i)
            # Check image history
            assert len(i.history) == 2
            assert i.history[1].action == ImageHistory.ACTION_REPLACED
            # Check that the cache was cleared too
            cache_entries = cm.search(searchfield1__eq=uploaded_id)
            assert len(cache_entries) == 0
        finally:
            # Delete temp file and uploaded file
            if os.path.exists(temp_file): os.remove(temp_file)
            delete_file(image_path)
        # Check db auto-populates for the now-deleted uploaded file
        im.reset_image(ImageAttrs(image_path))  # Anything to trigger auto-populate
        i = dm.get_image(src=image_path, load_history=True)
        assert i is not None
        assert i.status == Image.STATUS_DELETED
        assert len(i.history) == 3
        assert i.history[2].action == ImageHistory.ACTION_DELETED
        # Clean up
        dm.delete_image(i, True)

#    # A basic test to look for obvious memory leaks
#    def test_memory_leaks(self):
#        import gc
#        gc.collect()
#        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=500&flip=v&cache=0')
#        assert rv.status_code == 200
#        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=500&flip=v&cache=1')
#        assert rv.status_code == 200
#        rv = self.app.get('/original?src=test_images/cathedral.jpg')
#        assert rv.status_code == 200
#        rv = self.app.get('/image?src=test_images/multipage.tif&format=png&width=500&strip=1&page=2')
#        assert rv.status_code == 200
#        rv = self.app.get('/image?src=test_images/multipage.tif&format=png&width=500&strip=1&page=3')
#        assert rv.status_code == 200
#        gc.collect()
#        unreach = gc.collect()
#        assert unreach == 0, str(unreach) + ' unreachable'

    # File uploads
    def test_file_upload(self):
        self.login('admin', 'admin')
        # Copy a test file to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis_uploadfile.jpg'
        shutil.copy(src_file, dst_file)
        try:
            # Upload
            rv = self.file_upload(self.app, dst_file, 'test_images')
            self.assertEqual(rv.status_code, 200)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 1)
            self.assertIn('/tmp/qis_uploadfile.jpg', obj)
            imgdata = obj['/tmp/qis_uploadfile.jpg']
            self.assertEqual(imgdata['src'], 'test_images/tmp_qis_uploadfile.jpg')
            self.assertGreater(imgdata['id'], 0)
            # Make sure it works
            rv = self.app.get('/image?src=test_images/tmp_qis_uploadfile.jpg')
            self.assertEqual(rv.status_code, 200)
        finally:
            # Remove the test files
            os.remove(dst_file)
            delete_file('test_images/tmp_qis_uploadfile.jpg')
        # Remove the data too
        db_img = dm.get_image(src='test_images/tmp_qis_uploadfile.jpg')
        assert db_img is not None, 'Upload did not create image data'
        dm.delete_image(db_img, True)

    # File uploads
    def test_file_upload_multi(self):
        self.login('admin', 'admin')
        # Copy test files to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file1 = '/tmp/qis_uploadfile1.jpg'
        dst_file2 = '/tmp/qis_uploadfile2.jpg'
        shutil.copy(src_file, dst_file1)
        shutil.copy(src_file, dst_file2)
        try:
            # Test both files success
            with open(dst_file1, 'rb') as infile1:
                with open(dst_file2, 'rb') as infile2:
                    rv = self.app.post('/api/upload/', data={
                        'files': [infile1, infile2],
                        'path': 'test_images',
                        'overwrite': '1'
                    })
            self.assertEqual(rv.status_code, 200)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 2)
            imgdata = obj['/tmp/qis_uploadfile1.jpg']
            self.assertEqual(imgdata['src'], 'test_images/tmp_qis_uploadfile1.jpg')
            self.assertGreater(imgdata['id'], 0)
            imgdata = obj['/tmp/qis_uploadfile2.jpg']
            self.assertEqual(imgdata['src'], 'test_images/tmp_qis_uploadfile2.jpg')
            self.assertGreater(imgdata['id'], 0)
            # Test 1 file success, 1 file failure
            delete_file('test_images/tmp_qis_uploadfile1.jpg')
            with open(dst_file1, 'rb') as infile1:
                with open(dst_file2, 'rb') as infile2:
                    rv = self.app.post('/api/upload/', data={
                        'files': [infile1, infile2],
                        'path': 'test_images',
                        'overwrite': '0'  # This will break now on dst_file2
                    })
            self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertEqual(obj['status'], API_CODES.ALREADY_EXISTS)
            obj = obj['data']
            self.assertEqual(len(obj), 2)
            # First entry should be image info
            imgdata = obj['/tmp/qis_uploadfile1.jpg']
            self.assertEqual(imgdata['src'], 'test_images/tmp_qis_uploadfile1.jpg')
            self.assertGreater(imgdata['id'], 0)
            # Second entry should be error info
            imgdata = obj['/tmp/qis_uploadfile2.jpg']
            self.assertNotIn('id', imgdata)
            self.assertIn('error', imgdata)
            self.assertEqual(imgdata['error']['status'], API_CODES.ALREADY_EXISTS)
            self.assertIn('already exists', imgdata['error']['message'])
        finally:
            # Remove the test files
            for f in [dst_file1, dst_file2]:
                os.remove(f)
            delete_file('test_images/tmp_qis_uploadfile1.jpg')
            delete_file('test_images/tmp_qis_uploadfile2.jpg')
        # Remove the data too
        db_img = dm.get_image(src='test_images/tmp_qis_uploadfile1.jpg')
        dm.delete_image(db_img, True)
        db_img = dm.get_image(src='test_images/tmp_qis_uploadfile2.jpg')
        dm.delete_image(db_img, True)

    # File uploads
    def test_file_upload_unicode(self):
        self.login('admin', 'admin')
        # Copy a test file to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis uplo\xe4d f\xefle.jpg'
        shutil.copy(src_file, dst_file)
        try:
            # Upload
            rv = self.file_upload(self.app, dst_file, 'test_images')
            self.assertEqual(rv.status_code, 200)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 1)
            self.assertIn('/tmp/qis uplo\xe4d f\xefle.jpg', obj)
            imgdata = obj['/tmp/qis uplo\xe4d f\xefle.jpg']
            self.assertEqual(imgdata['src'], 'test_images/tmp_qis uplo\xe4d f\xefle.jpg')
            self.assertGreater(imgdata['id'], 0)
            # Make sure it works
            rv = self.app.get('/image?src=test_images/tmp_qis uplo\xe4d f\xefle.jpg')
            self.assertEqual(rv.status_code, 200)
        finally:
            # Remove the test files
            os.remove(dst_file)
            delete_file('test_images/tmp_qis uplo\xe4d f\xefle.jpg')
        # Remove the data too
        db_img = dm.get_image(src='test_images/tmp_qis uplo\xe4d f\xefle.jpg')
        assert db_img is not None, 'Upload did not create image data'
        dm.delete_image(db_img, True)

    # File uploads expected failures
    def test_bad_file_uploads(self):
        # Should fail if not logged in
        rv = self.app.post('/api/upload/', data={
            'files': None,
            'path': 'test_images',
            'overwrite': '1'
        })
        self.assertEqual(rv.status_code, 401)
        self.login('admin', 'admin')
        # Non-image file upload should fail (1)
        rv = self.file_upload(self.app, '/etc/hosts', 'test_images')
        self.assertEqual(rv.status_code, 400)
        # Non-image file upload should fail (2)
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis_uploadfile.doc'
        shutil.copy(src_file, dst_file)
        try:
            rv = self.file_upload(self.app, dst_file, 'test_images')
            self.assertEqual(rv.status_code, 415)
        finally:
            if os.path.exists(dst_file):
                os.remove(dst_file)
        # Too large a file should fail
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis_uploadfile.jpg'
        shutil.copy(src_file, dst_file)
        old_MAX_CONTENT_LENGTH = flask_app.config['MAX_CONTENT_LENGTH']
        try:
            flask_app.config['MAX_CONTENT_LENGTH'] = 100
            rv = self.file_upload(self.app, dst_file, 'test_images')
            self.assertEqual(rv.status_code, 413)
        finally:
            flask_app.config['MAX_CONTENT_LENGTH'] = old_MAX_CONTENT_LENGTH
            if os.path.exists(dst_file):
                os.remove(dst_file)

    # Test unicode characters in filenames, especially dashes!
    def test_unicode_filenames(self):
        temp_dir = '\u00e2 te\u00dft \u2014 of \u00e7har\u0292'
        temp_file = os.path.join(temp_dir, temp_dir + '.jpg')
        try:
            with flask_app.test_request_context():
                image_url = internal_url_for('image', src=temp_file)
                original_url = internal_url_for('original', src=temp_file)
                overlayed_image_url = internal_url_for('image', src='test_images/cathedral.jpg', width=500, overlay_src=temp_file, overlay_size=0.5)
                list_url = internal_url_for('browse', path=temp_dir)
                details_url = internal_url_for('details', src=temp_file)
                fp_admin_url = internal_url_for('admin.folder_permissions', path=temp_dir)
                fp_trace_url = internal_url_for('admin.trace_permissions', path=temp_dir)

            # Create test folder and file
            make_dirs(temp_dir)
            copy_file('test_images/thames.jpg', temp_file)
            # Test plain image views
            rv = self.app.get(image_url)
            self.assertEqual(rv.status_code, 200)
            rv = self.app.get(original_url)
            self.assertEqual(rv.status_code, 200)
            # Test image with a unicode overlay name
            rv = self.app.get(overlayed_image_url)
            self.assertEqual(rv.status_code, 200)
            # Test directory listing
            self.login('admin', 'admin')
            rv = self.app.get(list_url)
            self.assertEqual(rv.status_code, 200)
            self.assertNotIn('class="error', rv.data.decode('utf8'))
            # Test viewing details
            rv = self.app.get(details_url)
            self.assertEqual(rv.status_code, 200)
            self.assertNotIn('class="error', rv.data.decode('utf8'))
            # Test folder permission admin
            rv = self.app.get(fp_admin_url)
            self.assertEqual(rv.status_code, 200)
            self.assertNotIn('class="error', rv.data.decode('utf8'))
            # Test permissions tracing
            rv = self.app.get(fp_trace_url)
            self.assertEqual(rv.status_code, 200)
            self.assertNotIn('class="error', rv.data.decode('utf8'))
        finally:
            delete_dir(temp_dir, recursive=True)

    # Test that there are no database accesses under optimal conditions
    def test_db_accesses(self):
        test_image = 'test_images/cathedral.jpg'
        sql_info = { 'count': 0, 'last': '' }
        # Install an SQL event listener
        def on_sql(sql):
            sql_info['count'] += 1
            sql_info['last'] = sql
        dm._add_sql_listener(on_sql)
        # Check that the listener works
        dm.get_group(Group.ID_PUBLIC)
        assert sql_info['count'] == 1
        # Clear out the image caches and permissions caches
        im.reset_image(ImageAttrs(test_image))
        delete_image_ids()
        pm.reset()
        # Viewing an image will trigger SQL for the image record and folder permissions reads
        rv = self.app.get('/image?src=' + test_image)
        assert rv.status_code == 200
        last_sql_count = sql_info['count']
        assert last_sql_count > 1
        # Viewing it again should use cached data with no SQL
        rv = self.app.get('/image?src=' + test_image)
        assert rv.status_code == 200
        assert sql_info['count'] == last_sql_count, 'Unexpected SQL: ' + sql_info['last']
        # Viewing a smaller version of the same thing
        rv = self.app.get('/image?src=' + test_image + '&width=200')
        assert rv.status_code == 200
        # We expect SQL:
        # 1) Cache miss looking for an exact cached version (issues a delete)
        # 2) Cache search looking for a base image to resize (issues a select)
        # 3) Cache addition of the resized version (issues a select then an insert)
        EXPECT_SQL = 4
        assert sql_info['count'] == last_sql_count + EXPECT_SQL
        last_sql_count = sql_info['count']
        # Viewing that again should use cached data with no SQL
        rv = self.app.get('/image?src=' + test_image + '&width=200')
        assert rv.status_code == 200
        assert sql_info['count'] == last_sql_count, 'Unexpected SQL: ' + sql_info['last']

    # Test folder permission hierarchy / inheritance
    def test_folder_permissions_hierarchy(self):
        tempfile = '/rootfile.jpg'
        try:
            # Reset the default public permission to None
            set_default_public_permission(FolderPermission.ACCESS_NONE)
            # test_images should not be viewable
            rv = self.app.get('/image?src=test_images/cathedral.jpg')
            assert rv.status_code == API_CODES.UNAUTHORISED
            # Set a user's group to allow view for root folder
            setup_user_account('kryten', 'none')
            db_group = dm.get_group(groupname='Red Dwarf')
            db_folder = dm.get_folder(folder_path='')
            dm.save_object(FolderPermission(db_folder, db_group, FolderPermission.ACCESS_VIEW))
            pm.reset()
            # Log in, test_images should be viewable now
            self.login('kryten', 'kryten')
            rv = self.app.get('/image?src=test_images/cathedral.jpg')
            assert rv.status_code == 200
            # But download should be denied
            rv = self.app.get('/original?src=test_images/cathedral.jpg')
            assert rv.status_code == API_CODES.UNAUTHORISED
            # Update test group permission to allow download for test_images folder
            db_folder = dm.get_folder(folder_path='test_images')
            dm.save_object(FolderPermission(db_folder, db_group, FolderPermission.ACCESS_DOWNLOAD))
            pm.reset()
            # Download should be denied for root, but now allowed for test_images
            copy_file('test_images/cathedral.jpg', tempfile)
            rv = self.app.get('/original?src=' + tempfile)
            assert rv.status_code == API_CODES.UNAUTHORISED
            rv = self.app.get('/original?src=test_images/cathedral.jpg')
            assert rv.status_code == 200
            # For theoretical new sub-folders, /newfolder should now allow view
            # and /test_images/newfolder should allow download. This test is
            # for the upload page, which has to create - e.g. the daily uploads
            # folder - and so needs to calculate the permissions in advance.
            with self.app as this_session:
                this_session.get('/')
                assert pm.calculate_folder_permissions('/newfolder',
                    get_session_user(), folder_must_exist=False) == FolderPermission.ACCESS_VIEW
                assert pm.calculate_folder_permissions('/test_images/newfolder',
                    get_session_user(), folder_must_exist=False) == FolderPermission.ACCESS_DOWNLOAD
            # Log out, test_image should not be viewable again
            self.logout()
            rv = self.app.get('/image?src=test_images/cathedral.jpg')
            assert rv.status_code == API_CODES.UNAUTHORISED
            rv = self.app.get('/original?src=test_images/cathedral.jpg')
            assert rv.status_code == API_CODES.UNAUTHORISED
            # Set the default public permission to View
            set_default_public_permission(FolderPermission.ACCESS_VIEW)
            # test_image should be viewable now
            rv = self.app.get('/image?src=test_images/cathedral.jpg')
            assert rv.status_code == 200
        finally:
            delete_file(tempfile)
            set_default_public_permission(FolderPermission.ACCESS_DOWNLOAD)

    # Test image and page access (folder permissions)
    def test_folder_permissions(self):
        temp_file = '/tmp/qis_uploadfile.jpg'
        temp_image_path = 'test_images/tmp_qis_uploadfile.jpg'
        try:
            # 1 Folder browse page requires view permission
            # 2 Image details page requires view permission
            # 3 Image view requires view permission
            # 4 Image download requires download permission
            # 5 Image edit page required edit permission
            # 6 Image upload requires upload permission
            def test_pages(expect_pass):
                rv = self.app.get('/list/') #1
                assert rv.status_code == 200
                assert ('test_images</a>' in rv.data.decode('utf8')) if expect_pass[0] else ('permission is required' in rv.data.decode('utf8'))
                rv = self.app.get('/details/?src=test_images/cathedral.jpg') #2
                assert rv.status_code == 200
                assert ('Image width' in rv.data.decode('utf8')) if expect_pass[1] else ('permission is required' in rv.data.decode('utf8'))
                rv = self.app.get('/image?src=test_images/cathedral.jpg') #3
                assert (rv.status_code == 200) if expect_pass[2] else (rv.status_code == 403)
                rv = self.app.get('/original?src=test_images/cathedral.jpg') #4
                assert (rv.status_code == 200) if expect_pass[3] else (rv.status_code == 403)
                rv = self.app.get('/edit/?src=test_images/cathedral.jpg') #5
                assert rv.status_code == 200
                assert ('Title:' in rv.data.decode('utf8')) if expect_pass[4] else ('permission is required' in rv.data.decode('utf8'))
                rv = self.file_upload(self.app, temp_file, 'test_images') #6
                assert rv.status_code == 200 if expect_pass[5] else rv.status_code != 200
            # Create temp file for uploads
            src_file = get_abs_path('test_images/cathedral.jpg')
            shutil.copy(src_file, temp_file)
            # Reset the default public permission to None
            set_default_public_permission(FolderPermission.ACCESS_NONE)
            # Create test user with no permission overrides, log in
            setup_user_account('kryten', 'none')
            self.login('kryten', 'kryten')
            db_group = dm.get_group(groupname='Red Dwarf')
            db_folder = dm.get_folder(folder_path='')
            db_test_folder = dm.get_folder(folder_path='test_images')
            # Run numbered tests - first with no permission
            fp = FolderPermission(db_folder, db_group, FolderPermission.ACCESS_NONE)
            fp = dm.save_object(fp, refresh=True)
            pm.reset()
            test_pages((False, False, False, False, False, False))
            # Also test permission tracing (ATPT)
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_NONE, 'Trace is ' + _trace_to_str(ptrace)
            # With view permission
            fp.access = FolderPermission.ACCESS_VIEW
            dm.save_object(fp)
            pm.reset()
            test_pages((True, True, True, False, False, False))
            # ATPT
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_VIEW, 'Trace is ' + _trace_to_str(ptrace)
            # With download permission
            fp.access = FolderPermission.ACCESS_DOWNLOAD
            dm.save_object(fp)
            pm.reset()
            test_pages((True, True, True, True, False, False))
            # ATPT
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_DOWNLOAD, 'Trace is ' + _trace_to_str(ptrace)
            # With edit permission
            fp.access = FolderPermission.ACCESS_EDIT
            dm.save_object(fp)
            pm.reset()
            test_pages((True, True, True, True, True, False))
            # ATPT
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_EDIT, 'Trace is ' + _trace_to_str(ptrace)
            # With upload permission
            fp.access = FolderPermission.ACCESS_UPLOAD
            dm.save_object(fp)
            pm.reset()
            test_pages((True, True, True, True, True, True))
            # ATPT
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_UPLOAD, 'Trace is ' + _trace_to_str(ptrace)
            # Check the permissions trace updates when admin permission is granted
            setup_user_account('kryten', 'admin_files')
            self.login('kryten', 'kryten')
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_ALL, 'Trace is ' + _trace_to_str(ptrace)
        finally:
            # Delete temp file and uploaded file
            if os.path.exists(temp_file): os.remove(temp_file)
            delete_file(temp_image_path)
            set_default_public_permission(FolderPermission.ACCESS_DOWNLOAD)

    # Test that overlay obeys the permissions rules
    def test_overlay_permissions(self):
        ov_folder = 'test_overlays/'
        ov_path = ov_folder + 'overlay.png'
        try:
            # Create an overlay folder and image
            make_dirs(ov_folder)
            copy_file('test_images/quru110.png', ov_path)
            # Set the folder permissions to deny view on overlay folder
            db_ov_folder = auto_sync_folder(ov_folder, dm, tm, False)
            db_group = dm.get_group(Group.ID_PUBLIC)
            dm.save_object(FolderPermission(db_ov_folder, db_group, FolderPermission.ACCESS_NONE))
            # Check we can view our test image and NOT the overlay image
            rv = self.app.get('/image?src=test_images/cathedral.jpg')
            assert rv.status_code == 200
            rv = self.app.get('/image?src=' + ov_path)
            assert rv.status_code == 403
            # Now see if we can view the overlay inside the test image (hopefully not)
            rv = self.app.get('/image?src=test_images/cathedral.jpg&overlay=' + ov_path)
            assert rv.status_code == 403
        finally:
            delete_dir(ov_folder, True)

    # Test that the browser cache expiry headers work
    def test_caching_expiry_settings(self):
        try:
            # Utility to update the default template
            db_def_temp = dm.get_image_template(tempname='Default')
            def set_default_expiry(value):
                db_def_temp.template['expiry_secs']['value'] = value
                dm.save_object(db_def_temp)
                im.reset_templates()
            # This should work with both 'image' and 'original'
            for api in ['image', 'original']:
                img_url = '/' + api + '?src=test_images/dorset.jpg&width=800'
                set_default_expiry(-1)
                img = self.app.get(img_url)
                self.assertEqual(img.headers.get('Expires'), http_date(0))
                self.assertIn(img.headers.get('Cache-Control'), ['no-cache, public', 'public, no-cache'])
                set_default_expiry(0)
                img = self.app.get(img_url)
                self.assertIsNone(img.headers.get('Expires'))
                self.assertIsNone(img.headers.get('Cache-Control'))
                set_default_expiry(60)
                img = self.app.get(img_url)
                self.assertEqual(img.headers.get('Expires'), http_date(int(time.time() + 60)))
                self.assertIn(img.headers.get('Cache-Control'), ['public, max-age=60', 'max-age=60, public'])
        finally:
            reset_default_image_template()

    # Test that the browser cache validation headers work
    def test_etags(self):
        # Check that client caching is enabled
        self.assertGreater(im.get_default_template().expiry_secs(), 0)
        # Setup
        img_url = '/image?src=test_images/dorset.jpg&width=440&angle=90&top=0.2&tile=3:4'
        rv = self.app.get(img_url)
        assert rv.headers['X-From-Cache'] == 'False'
        assert rv.headers.get('ETag') is not None
        etag = rv.headers.get('ETag')
        # Etag should stay the same for the same cached image
        rv = self.app.get(img_url)
        assert rv.headers['X-From-Cache'] == 'True'
        assert rv.headers.get('ETag') == etag
        # Etag should be updated when the image is re-generated
        im.reset_image(ImageAttrs('test_images/dorset.jpg'))
        rv = self.app.get(img_url)
        assert rv.headers['X-From-Cache'] == 'False'
        assert rv.headers.get('ETag') is not None
        new_etag = rv.headers.get('ETag')
        assert new_etag != etag
        # Etag should stay the same for the same cached image
        rv = self.app.get(img_url)
        assert rv.headers['X-From-Cache'] == 'True'
        assert rv.headers.get('ETag') == new_etag

    # Test that browser caching still works when server side caching is off
    def test_no_server_caching_etags(self):
        # Check the expected default expires header value
        self.assertEqual(im.get_default_template().expiry_secs(), 604800)
        # Setup
        setup_user_account('kryten', 'none')
        self.login('kryten', 'kryten')  # Login to allow cache=0
        img_url = '/image?src=test_images/dorset.jpg&width=250&cache=0'
        rv = self.app.get(img_url)
        self.assertEqual(rv.headers['X-From-Cache'], 'False')
        self.assertIsNotNone(rv.headers.get('ETag'))
        self.assertEqual(rv.headers.get('Expires'), http_date(int(time.time() + 604800)))
        self.assertIn(rv.headers.get('Cache-Control'), ['public, max-age=604800', 'max-age=604800, public'])
        etag = rv.headers.get('ETag')
        # Etag should stay the same for the same re-generated image
        rv = self.app.get(img_url)
        self.assertEqual(rv.headers['X-From-Cache'], 'False')
        self.assertEqual(rv.headers.get('Expires'), http_date(int(time.time() + 604800)))
        self.assertIn(rv.headers.get('Cache-Control'), ['public, max-age=604800', 'max-age=604800, public'])
        self.assertEqual(rv.headers.get('ETag'), etag)

    # Test that etags are removed when client side caching is off
    def test_no_client_caching_etags(self):
        try:
            # Turn off client side caching in the default template
            db_def_temp = dm.get_image_template(tempname='Default')
            db_def_temp.template['expiry_secs']['value'] = -1
            dm.save_object(db_def_temp)
            im.reset_templates()
            # Run test
            for api in ['image', 'original']:
                img_url = '/' + api + '?src=test_images/dorset.jpg'
                img = self.app.get(img_url)
                self.assertIsNone(img.headers.get('ETag'))
        finally:
            reset_default_image_template()

    # Test that ETags are all different for different images with the
    # same parameters and for the same images with different parameters
    def test_etag_collisions(self):
        # Check that client caching is enabled
        self.assertGreater(im.get_default_template().expiry_secs(), 0)
        # Generate a suite of URLs
        url_list = [
            '/image?src=test_images/dorset.jpg',
            '/image?src=test_images/cathedral.jpg',
            '/image?src=test_images/blue bells.jpg',
            '/image?src=test_images/quru470.png',
        ]
        url_list2 = []
        for url in url_list:
            url_list2.append(url)
            url_list2.append(url + '&page=2')
            url_list2.append(url + '&page=2&width=200')
            url_list2.append(url + '&page=2&width=200&flip=h')
            url_list2.append(url + '&width=200&height=200')
            url_list2.append(url + '&width=200&height=200&fill=red')
        etags_list = []
        # Request all the URLs
        for url in url_list2:
            rv = self.app.get(url)
            assert rv.status_code == 200
            assert rv.headers.get('ETag') is not None
            etags_list.append(rv.headers['ETag'])
        # There should be no dupes
        assert len(etags_list) == len(set(etags_list))

    # Test that clients with an up-to-date cached image don't have to download it again
    def test_304_Not_Modified(self):
        # Check the expected default expires header value
        self.assertEqual(im.get_default_template().expiry_secs(), 604800)
        # This should work with both 'image' and 'original'
        for api in ['image', 'original']:
            # Setup
            img_url = '/' + api + '?src=test_images/dorset.jpg&width=440&angle=90&top=0.2&tile=3:4'
            rv = self.app.get(img_url)
            self.assertEqual(rv.status_code, 200)
            etag = rv.headers.get('ETag')
            # Client sending an Etag should get a 304 Not Modified if the Etag is still valid
            rv = self.app.get(img_url, headers={
                'If-None-Match': etag
            })
            self.assertEqual(rv.status_code, 304)
            # http://stackoverflow.com/a/4393499/1671320
            # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.3.5
            self.assertEqual(rv.headers.get('ETag'), etag)
            self.assertIsNotNone(rv.headers.get('Date'))
            self.assertIn(
                rv.headers.get('Expires'), [
                    http_date(int(time.time() + 604800 - 1)),  # If time() has wrapped to the next second
                    http_date(int(time.time() + 604800))       # Expected
                ]
            )
            self.assertIn(rv.headers.get('Cache-Control'), ['public, max-age=604800', 'max-age=604800, public'])
            # Flask bug? Content type gets here but is correctly absent outside of unit tests
            # self.assertIsNone(rv.headers.get('Content-Type'))
            self.assertIsNone(rv.headers.get('Content-Length'))
            self.assertIsNone(rv.headers.get('X-From-Cache'))
            self.assertIsNone(rv.headers.get('Content-Disposition'))
            self.assertEqual(rv.data, b'')
            # Now reset the image
            if api == 'image':
                im.reset_image(ImageAttrs('test_images/dorset.jpg'))
            else:
                os.utime(get_abs_path('test_images/dorset.jpg'), None)  # Touch
            # Client should get a new image and Etag when the old one is no longer valid
            rv = self.app.get(img_url, headers={
                'If-None-Match': etag
            })
            self.assertEqual(rv.status_code, 200)
            self.assertNotEqual(rv.headers.get('ETag'), etag)
            self.assertGreater(len(rv.data), 0)

    # #2668 Make sure things work properly behind a reverse proxy / load balancer
    def test_proxy_server(self):
        from imageserver.flask_ext import add_proxy_server_support
        # Set standard settings
        flask_app.config['PROXY_SERVERS'] = 0
        flask_app.config['INTERNAL_BROWSING_SSL'] = True
        flask_app.config['SESSION_COOKIE_SECURE'] = True
        # As standard, expect the X-Forwarded-For and X-Forwarded-Proto headers to be ignored
        rv = self.app.get('/login/', headers={'X-Forwarded-Proto': 'https'})
        # Should be redirecting us to HTTPS
        self.assertEqual(rv.status_code, 302)
        self.assertIn('https://', rv.data.decode('utf8'))
        # Should log localhost as the IP
        with mock.patch('imageserver.flask_app.logger.error') as mocklog:
            self.app.get(
                '/image?src=../../../notallowed',
                headers={'X-Forwarded-For': '1.2.3.4'},
                environ_base={'REMOTE_ADDR': '127.0.0.1'}
            )
            mocklog.assert_called_once_with(mock.ANY)
            self.assertIn('IP 127.0.0.1', mocklog.call_args[0][0])
        # With proxy support enabled, expect the headers to be respected
        flask_app.config['PROXY_SERVERS'] = 1
        add_proxy_server_support(flask_app, flask_app.config['PROXY_SERVERS'])
        rv = self.app.get('/login/', headers={'X-Forwarded-Proto': 'https'})
        # Should now just serve the login page
        self.assertEqual(rv.status_code, 200)
        # Should now log 1.2.3.4 as the IP
        with mock.patch('imageserver.flask_app.logger.error') as mocklog:
            self.app.get(
                '/image?src=../../../notallowed',
                headers={'X-Forwarded-For': '1.2.3.4'},
                environ_base={'REMOTE_ADDR': '127.0.0.1'}
            )
            mocklog.assert_called_once_with(mock.ANY)
            self.assertIn('IP 1.2.3.4', mocklog.call_args[0][0])

    # #2799 User names should be case insensitive
    def test_username_case(self):
        try:
            # Get 2 identical user objects, but with username in different case
            newuser = User(
                'Jango', 'Fett', 'jango@bountyhunters.info', 'jangofett', 'Tipoca',
                User.AUTH_TYPE_PASSWORD, False, User.STATUS_ACTIVE
            )
            cloneuser = User(
                'Jango', 'Fett', 'jango@bountyhunters.info', 'JangoFett', 'Tipoca',
                User.AUTH_TYPE_PASSWORD, False, User.STATUS_ACTIVE
            )
            # Create the new user
            dm.create_user(newuser)
            # We should be able to read this back with username in any case
            u = dm.get_user(username='jangofett')
            self.assertIsNotNone(u)
            u = dm.get_user(username='JangoFett')
            self.assertIsNotNone(u)
            # Creating the clone user should fail
            self.assertRaises(AlreadyExistsError, dm.create_user, cloneuser)
        finally:
            # Tidy up
            u = dm.get_user(username='jangofett')
            if u: dm.delete_object(u)
            u2 = dm.get_user(username='JangoFett')
            if u2: dm.delete_object(u2)


class ImageServerCacheTests(BaseTestCase):
    # Test basic cache
    def test_cache_engine_raw(self):
        ret = cm.raw_get('knight')
        self.assertIsNone(ret, 'Test object already in cache - reset cache and re-run tests')
        ret = cm.raw_put('knight', ImageAttrs('round/table.jpg', 1000))
        self.assertTrue(ret)
        ret = cm.raw_get('knight')
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret, ImageAttrs)
        self.assertEqual(ret.filename(), 'round/table.jpg')
        self.assertEqual(ret.database_id(), 1000)
        ret = cm.raw_delete('knight')
        self.assertTrue(ret)
        ret = cm.raw_get('knight')
        self.assertIsNone(ret)

    # Test managed cache
    def test_cache_engine(self):
        ret = cm.get('grail')
        self.assertIsNone(ret, 'Test object already in cache - reset cache and re-run tests')
        ok = cm.put('grail', 'the knights who say Ni', 0, {
            'searchfield1': -1, 'searchfield2': 100, 'searchfield3': 100,
            'searchfield4': None, 'searchfield5': None, 'metadata': 'Rockery'
        })
        self.assertTrue(ok)
        ret = cm.get('grail')
        self.assertIsNotNone(ret, 'Failed to retrieve object from cache')
        self.assertEqual(ret, 'the knights who say Ni', 'Wrong object retrieved from cache')
        # Add something else to filter out from the search
        ok = cm.put('elderberry', 'Go away', 0, {
            'searchfield1': -1, 'searchfield2': 50, 'searchfield3': 100,
            'searchfield4': None, 'searchfield5': None, 'metadata': 'Hamsters'
        })
        self.assertTrue(ok)
        # Test search
        ret = cm.search(order=None, max_rows=1, searchfield1__eq=-1, searchfield2__gt=99, searchfield3__lt=101)
        self.assertEqual(len(ret), 1, 'Failed to search cache')
        result = ret[0]
        self.assertEqual(result['key'], 'grail', 'Wrong key from cache search')
        self.assertEqual(result['metadata'], 'Rockery', 'Wrong metadata from cache search')
        ok = cm.delete('grail')
        self.assertTrue(ok)
        ret = cm.get('grail')
        self.assertIsNone(ret, 'Failed to delete object from cache')

    # Test no one has tinkered incorrectly with the caching slot allocation code
    def test_cache_slot_headers(self):
        from imageserver.cache_manager import SLOT_HEADER_SIZE
        from imageserver.cache_manager import MAX_OBJECT_SLOTS
        header1 = cm._get_slot_header(1)
        self.assertEqual(len(header1), SLOT_HEADER_SIZE)
        header2 = cm._get_slot_header(MAX_OBJECT_SLOTS)
        self.assertEqual(len(header2), SLOT_HEADER_SIZE)

    # #1589 Test hash collision detection
    def test_cache_integrity_checks(self):
        # Check normal value set/get
        ret = cm.raw_put('knight', ImageAttrs('round/table.jpg', 1001), integrity_check=True)
        self.assertTrue(ret)
        ret = cm.raw_get('knight', integrity_check=True)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret, ImageAttrs)
        self.assertEqual(ret.filename(), 'round/table.jpg')
        self.assertEqual(ret.database_id(), 1001)
        ret = cm.raw_put('knight', 'ABC123', integrity_check=True)
        self.assertTrue(ret)
        ret = cm.raw_get('knight', integrity_check=True)
        self.assertEqual(ret, 'ABC123')
        # Check that value stored without an integrity check fails at raw_get()
        _val = 'ABC123'
        ret = cm.raw_put('knight', _val, integrity_check=False)
        self.assertTrue(ret)
        with mock.patch('imageserver.flask_app.logger.error') as mocklogger:
            ret = cm.raw_get('knight', integrity_check=True)
            self.assertIsNone(ret)
            mocklogger.assert_called_once_with(mock.ANY)
        # Check that value stored under a different key fails at raw_get()
        _val = cm._get_integrity_header('thewrongkey') + 'ABC123'
        ret = cm.raw_put('knight', _val, integrity_check=False)
        self.assertTrue(ret)
        with mock.patch('imageserver.flask_app.logger.error') as mocklogger:
            ret = cm.raw_get('knight', integrity_check=True)
            self.assertIsNone(ret)
            mocklogger.assert_called_once_with(mock.ANY)
        # Check delete
        ret = cm.raw_delete('knight')
        self.assertTrue(ret)
        ret = cm.raw_get('knight')
        self.assertIsNone(ret)


class UtilityTests(unittest.TestCase):
    def test_image_attrs_serialisation(self):
        ia = ImageAttrs('some/path', -1, page=2, iformat='psd', template='smalljpeg',
                        width=1000, height=1000, size_fit=False,
                        fill='black', colorspace='rgb', strip=False)
        ia_dict = ia.to_dict()
        self.assertEqual(ia_dict['template'], 'smalljpeg')
        self.assertEqual(ia_dict['fill'], 'black')
        self.assertEqual(ia_dict['page'], 2)
        self.assertEqual(ia_dict['size_fit'], False)
        rev = ImageAttrs.from_dict(ia_dict)
        rev_dict = rev.to_dict()
        self.assertEqual(ia_dict, rev_dict)

    def test_image_attrs_bad_serialisation(self):
        bad_dict = {
            'filename': 'some/path',
            'format': 'potato'
        }
        self.assertRaises(ValueError, ImageAttrs.from_dict, bad_dict)
        bad_dict = {
            'filename': 'some/path',
            'width': '-1'
        }
        self.assertRaises(ValueError, ImageAttrs.from_dict, bad_dict)
        bad_dict = {
            'filename': ''
        }
        self.assertRaises(ValueError, ImageAttrs.from_dict, bad_dict)

    def test_template_attrs_serialisation(self):
        # Test the standard constructor
        ta = TemplateAttrs('abcdef', {
            'width': {'value': 1000},
            'height': {'value': 1000},
            'expiry_secs': {'value': 50000},
            'record_stats': {'value': True}
        })
        self.assertEqual(ta.name(), 'abcdef')
        self.assertEqual(ta.get_image_attrs().filename(), 'abcdef')
        self.assertEqual(ta.expiry_secs(), 50000)
        self.assertEqual(ta.record_stats(), True)
        self.assertIsNone(ta.attachment())
        # Test values dict
        ta_dict = ta.get_values_dict()
        self.assertEqual(ta_dict['filename'], 'abcdef')
        self.assertEqual(ta_dict['width'], 1000)
        self.assertEqual(ta_dict['expiry_secs'], 50000)
        self.assertEqual(ta_dict['record_stats'], True)

    def test_template_attrs_bad_serialisation(self):
        # Old dict format
        bad_dict = {
            'filename': 'some/path',
            'expiry_secs': 50000
        }
        self.assertRaises(ValueError, TemplateAttrs, 'badtemplate', bad_dict)
        # New dict format, bad values
        bad_dict = {
            'filename': {'value': 'some/path'},
            'expiry_secs': {'value': -2}
        }
        self.assertRaises(ValueError, TemplateAttrs, 'badtemplate', bad_dict)
        bad_dict = {
            'filename': {'value': 'some/path'},
            'expiry_secs': {'value': 'not an int'}
        }
        self.assertRaises(ValueError, TemplateAttrs, 'badtemplate', bad_dict)
        bad_dict = {
            'filename': {'value': 'some/path'},
            'expiry_secs': {'value': 50000},
            'record_stats': {'value': 'not a bool'}
        }
        self.assertRaises(ValueError, TemplateAttrs, 'badtemplate', bad_dict)
