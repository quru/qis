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
# 07Jun2018  Matt  Moved imaging tests into test_imaging.py, added Pillow tests
#

import json
import os
import shutil
import subprocess
import time
import timeit
import unittest
from unittest import mock

import flask
from werkzeug.http import http_date

# Do not use the base or any other current environment settings,
# as we'll be clearing down the database
TESTING_SETTINGS = 'unit_tests'
os.environ['QIS_SETTINGS'] = TESTING_SETTINGS

print("Importing imageserver libraries")

# Assign global managers, same as the main app uses
from imageserver.flask_app import app as flask_app
from imageserver.flask_app import logger as lm
from imageserver.flask_app import cache_engine as cm
from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import image_engine as im
from imageserver.flask_app import stats_engine as sm
from imageserver.flask_app import task_engine as tm
from imageserver.flask_app import permissions_engine as pm
from imageserver.flask_app import launch_aux_processes, _stop_aux_processes

from imageserver.api_util import API_CODES
from imageserver.errors import AlreadyExistsError
from imageserver.filesystem_manager import (
    get_abs_path, copy_file, delete_dir, delete_file
)
from imageserver.filesystem_manager import get_abs_path, path_exists, make_dirs
from imageserver.filesystem_sync import (
    auto_sync_existing_file, auto_sync_folder
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
from imageserver.util import secure_filename
from imageserver import imaging


# Module level setUp and tearDown
def setUpModule():
    init_tests()
def tearDownModule():
    cleanup_tests()


# Utility - resets the database and cache, and optionally starts the aux processes
def init_tests(launch_aux=True):
    cm.clear()
    reset_databases()
    if launch_aux:
        launch_aux_processes()
        time.sleep(1)


# Utility - cleans up after tests have finished
def cleanup_tests():
    _stop_aux_processes()
    # The aux processes have a 1 second shutdown response
    time.sleep(1.5)
    # In case there are other test modules following on,
    # tell the test app that its aux server connections are now invalid
    lm._client_close()
    sm._client_close()


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
    # Default the public and internal root folder permissions to allow View + Download
    set_default_public_permission(FolderPermission.ACCESS_DOWNLOAD, False)
    set_default_internal_permission(FolderPermission.ACCESS_DOWNLOAD, False)
    # Set some standard image generation settings
    reset_default_image_template(False)
    # As we have wiped the data, invalidate the internal caches' data versions
    pm._foliop_data_version = 0
    pm._fp_data_version = 0
    pm.reset()
    im._templates._data_version = 0
    im.reset_templates()


def set_default_public_permission(access, clear_cache=True):
    default_fp = dm.get_object(FolderPermission, 1)
    assert default_fp.group_id == Group.ID_PUBLIC
    default_fp.access = access
    dm.save_object(default_fp)
    if clear_cache:
        pm.reset_folder_permissions()


def set_default_internal_permission(access, clear_cache=True):
    default_fp = dm.get_object(FolderPermission, 2)
    assert default_fp.group_id == Group.ID_EVERYONE
    default_fp.access = access
    dm.save_object(default_fp)
    if clear_cache:
        pm.reset_folder_permissions()


def reset_default_image_template(clear_cache=True):
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
    if clear_cache:
        im.reset_templates()


# Utility - selects or switches the Pillow / ImageMagick imaging back end
def select_backend(back_end):
    imaging.init(
        back_end,
        flask_app.config['GHOSTSCRIPT_PATH'],
        flask_app.config['TEMP_DIR'],
        flask_app.config['PDF_BURST_DPI']
    )
    # VERY IMPORTANT! Clear any images cached from the previous back end
    cm.clear()
    # The image manager does not expect the back end to change,
    # we need to clear its internal caches too
    im._memo_image_formats_all = None
    im._memo_image_formats_supported = None
    im._memo_supported_ops = None


# Utility - create/reset and return a test user having a certain system permission.
#           the returned user is a member of the standard "everyone" group and also
#           a separate group that is used for setting the custom system permission.
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
        test_group = dm.get_group(groupname=login_name+'-group', _db_session=db_session)
        if not test_group:
            test_group = Group(
                login_name + '-group',
                'Test group',
                Group.GROUP_TYPE_LOCAL
            )
            dm.create_group(test_group, _db_session=db_session)
        test_group.permissions = SystemPermissions(
            test_group, False, False, False, False, False, False, False
        )
        # Wipe folder and folio permissions
        del test_group.folder_permissions[:]
        del test_group.folio_permissions[:]
        # Apply permissions for requested test type
        if user_type == 'none':
            pass
        elif user_type == 'folios':
            test_group.permissions.folios = True
        elif user_type == 'admin_users':
            test_group.permissions.admin_users = True
        elif user_type == 'admin_files':
            test_group.permissions.admin_files = True
        elif user_type == 'admin_folios':
            test_group.permissions.admin_folios = True
        elif user_type == 'admin_permissions':
            test_group.permissions.admin_users = True
            test_group.permissions.admin_permissions = True
        elif user_type == 'admin_all':
            test_group.permissions.admin_all = True
        else:
            raise ValueError('Unimplemented test user type ' + user_type)
        dm.save_object(test_group, _db_session=db_session)
        everyone_group = dm.get_group(Group.ID_EVERYONE, _db_session=db_session)
        testuser.groups = [everyone_group, test_group]
        dm.save_object(testuser, _db_session=db_session)
        db_session.commit()
        return testuser
    finally:
        db_session.close()
        # Clear old cached user permissions
        pm.reset()


class FlaskTestCase(unittest.TestCase):
    def setUp(self):
        # Reset the app configuration before each test and create a Flask test client
        self.reset_settings()
        self.app = flask_app.test_client()

    def reset_settings(self):
        flask_app.config.from_object(flask.Flask.default_config)
        flask_app.config.from_object('imageserver.conf.base_settings')
        flask_app.config.from_object('imageserver.conf.' + TESTING_SETTINGS)


class BaseTestCase(FlaskTestCase):
    # Utility - perform a log in via the web page
    def login(self, usr, pwd):
        rv = self.app.post('/login/', data={
            'username': usr,
            'password': pwd
        })
        # 302 = success redirect, 200 = login page with error message
        self.assertEqual(
            rv.status_code, 302,
            'Login failed with response: ' + self.get_login_error(rv.data.decode('utf8'))
        )

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
    # folder via the file upload API. Returns the app.post() return value.
    def file_upload(self, app, src_file_path, dest_folder, overwrite='1'):
        return self.multi_file_upload(app, [src_file_path], dest_folder, overwrite)

    # Utility - uploads multiple files (provide the full paths) to an image server
    # folder via the file upload API. Returns the app.post() return value.
    def multi_file_upload(self, app, src_file_paths, dest_folder, overwrite='1'):
        files = []
        try:
            files = [open(path, 'rb') for path in src_file_paths]
            return app.post('/api/upload/', data={
                'files': files,
                'path': dest_folder,
                'overwrite': overwrite
            })
        finally:
            for fp in files:
                fp.close()

    # Utility - deletes a file from the image repository, and purges its data record
    # from the database. If the path does not exist or there is no data record then
    # the function continues silently without raising an error.
    def delete_image_and_data(self, rel_path):
        delete_file(rel_path)
        db_img = dm.get_image(src=rel_path)
        if db_img is not None:
            dm.delete_image(db_img, True)

    # Utility - waits for a file path (relative to IMAGES_BASE_DIR else absolute)
    # to exist, or else raises a timeout and fails the test
    def wait_for_path_existence(self, fpath, path_relative, timeout_secs):
        abs_path = get_abs_path(fpath) if path_relative else fpath
        start_time = time.time()
        while not os.path.exists(abs_path) and time.time() < (start_time + timeout_secs):
            time.sleep(1)
        self.assertTrue(
            os.path.exists(abs_path),
            'Path \'%s\' was not created within %.1f seconds' % (fpath, timeout_secs)
        )

    # Utility - return the interesting bit of a failed login page
    def get_login_error(self, html):
        fromidx = html.find("<div class=\"error")
        toidx = html.find("</div>", fromidx)
        return html[fromidx:toidx + 6]


class ImageServerBackgroundTaskTests(BaseTestCase):
    # Test xref parameter
    def test_xref_parameter(self):
        inner_server = None
        try:
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
            temp_env['FLASK_ENV'] = 'production'
            rs_path = 'src/runserver.py' if os.path.exists('src/runserver.py') else 'runserver.py'
            inner_server = subprocess.Popen('python ' + rs_path, cwd='.', shell=True, env=temp_env)
            time.sleep(2)
            # Set the xref base URL so that we will generate image A if we pass 50 as width
            flask_app.config['XREF_TRACKING_URL'] = \
                'http://127.0.0.1:5000' + \
                '/image?src=test_images/cathedral.jpg&strip=0&dpi=0&format=jpg&quality=75&colorspace=rgb&width='
            # Call a different image B passing in the xref of 50
            rv = self.app.get('/image?src=test_images/dorset.jpg&xref=50')
            assert rv.status_code == 200
            # Wait a little for the background xref handling thread to complete
            time.sleep(3)
            # Now the test image A should have been created
            cache_img = cm.get(test_image_attrs.get_cache_key())
            assert cache_img is not None, 'Failed to find ' + test_image_attrs.get_cache_key() + '. xref URL did not appear to be invoked.'
        finally:
            # Kill the temporary server subprocess
            if inner_server:
                inner_server.terminate()
                time.sleep(1)

    # Tests that the anonymous stats upload task works
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
            time.sleep(15)
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
        time.sleep(15)
        # Now check the cache again for a base for the 500 version
        base = im._get_base_image(w500_attrs)
        assert base is not None, 'Auto-pyramid did not generate a smaller image'
        # And it shouldn't be the original image either
        assert len(base.data()) < orig_len
        assert base.attrs().width() is not None
        assert base.attrs().width() < 1600 and base.attrs().width() >= 500


class ImageServerMiscTests(BaseTestCase):
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
            self.delete_image_and_data('test_images/test_image.jpg')

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
        rv = self.app.get('/image?src=%2Fetc%2Fpasswd')
        self.assertEqual(rv.status_code, 404)
        rv = self.app.get('/original?src=%2Fetc%2Fpasswd')
        self.assertEqual(rv.status_code, 404)
        # Also try leading // to see if the code only strips one of them
        rv = self.app.get('/image?src=//etc/passwd')
        self.assertEqual(rv.status_code, 404)
        rv = self.app.get('/original?src=//etc/passwd')
        self.assertEqual(rv.status_code, 404)
        rv = self.app.get('/image?src=%2F%2Fetc%2Fpasswd')
        self.assertEqual(rv.status_code, 404)
        rv = self.app.get('/original?src=%2F%2Fetc%2Fpasswd')
        self.assertEqual(rv.status_code, 404)

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
        rv = self.app.get('/image?src=swëdish/dørset.jpg')
        self.assertEqual(rv.status_code, 404)
        self.assertIn('swëdish/dørset.jpg', rv.data.decode('utf8'))
        rv = self.app.get('/original?src=swëdish/dørset.jpg')
        self.assertEqual(rv.status_code, 404)
        self.assertIn('swëdish/dørset.jpg', rv.data.decode('utf8'))

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
            overlay_src='ovsrc123'  # So the overlay params get kept
        )
        ov_hash = str(hash('ovsrc123'))
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
        ov_hash = str(hash('ovsrc123'))
        i = ImageAttrs('', 1, overlay_src='ovsrc123', overlay_opacity=0.9, overlay_size=0.9)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1,Y' + ov_hash + ',YO0.9,YS0.9')
        i = ImageAttrs('', 1, overlay_src='ovsrc123', overlay_opacity=0, overlay_size=1)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        i = ImageAttrs('', 1, overlay_src='ovsrc123', overlay_opacity=1, overlay_size=0)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1')
        # No ICC name cancels ICC params
        i = ImageAttrs('', 1, icc_profile='icc123', icc_intent='relative', icc_bpc=True)
        i.normalise_values()
        self.assertEqual(i.get_cache_key(), 'IMG:1,Picc123,Nrelative,C')
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
        try_attrs = ImageAttrs('test_images/dorset.jpg', image_id, iformat='gif', width=500, rotation=90)  # Format
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
        # Should now be able to use the 800 as a base for a 500
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

    # Test changing the default template values
    def test_default_template_settings(self):
        try:
            db_def_temp = dm.get_image_template(tempname='Default')
            # Get img1 with explicit format and quality params
            img1 = self.app.get('/image?src=test_images/dorset.jpg&width=800&format=png&quality=50')
            self.assertEqual(img1.status_code, 200)
            self.assertIn('image/png', img1.headers['Content-Type'])
            # Get img2 with no params but with defaults set to be the same as img1
            db_def_temp.template['format']['value'] = 'png'
            db_def_temp.template['quality']['value'] = 50
            dm.save_object(db_def_temp)
            im.reset_templates()
            img2 = self.app.get('/image?src=test_images/dorset.jpg&width=800')
            self.assertEqual(img2.status_code, 200)
            self.assertIn('image/png', img2.headers['Content-Type'])
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
            # Test format from template
            update_db_template(db_template, {'format': {'value': 'png'}})
            self.assertIn(template, im.get_template_names())
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.status_code, 200)
            self.assertIn('image/png', rv.headers['Content-Type'])
            # Switch back to JPG as Pillow support for strip=1/0 with PNG isn't there yet
            update_db_template(db_template, {'format': {'value': ''}})
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template)
            self.assertEqual(rv.status_code, 200)
            self.assertIn('image/jpeg', rv.headers['Content-Type'])
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
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template+'&format=gif&attach=0')
            self.assertEqual(rv.status_code, 200)
            self.assertIn('image/gif', rv.headers['Content-Type'])
            self.assertIsNone(rv.headers.get('Content-Disposition'))
            template_gif_len = len(rv.data)   # at 500x500
            rv = self.app.get('/image?src=test_images/thames.jpg&tmp='+template+'&format=gif&width=600&height=600&attach=0')
            self.assertEqual(rv.status_code, 200)
            template_gif_len2 = len(rv.data)  # at 600x600
            self.assertGreater(template_gif_len2, template_gif_len)
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
        image_path = 'test_images/qis_uploadfile.jpg'
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

    # File upload
    def test_file_upload(self):
        self.login('admin', 'admin')
        # Copy a test file to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis_uploadfile.jpg'
        shutil.copy(src_file, dst_file)
        try:
            # Upload
            rv = self.file_upload(self.app, dst_file, 'test_images', '0')
            self.assertEqual(rv.status_code, 200)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 1)
            self.assertIn('/tmp/qis_uploadfile.jpg', obj)
            imgdata = obj['/tmp/qis_uploadfile.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile.jpg')
            self.assertGreater(imgdata['id'], 0)
            self.assertNotIn('history', imgdata)  # v4.1
            # Make sure it works
            rv = self.app.get('/image?src=test_images/qis_uploadfile.jpg')
            self.assertEqual(rv.status_code, 200)
            db_img = dm.get_image(src='test_images/qis_uploadfile.jpg')
            self.assertIsNotNone(db_img, 'Upload did not create image data')
        finally:
            # Remove the test files
            os.remove(dst_file)
            self.delete_image_and_data('test_images/qis_uploadfile.jpg')

    # v2.7.1 File upload - with overwrite as rename
    def test_file_upload_overwrite_rename(self):
        self.login('admin', 'admin')
        # Copy a test file to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis_uploadfile.jpg'
        shutil.copy(src_file, dst_file)
        try:
            # Have the upload file exist already
            copy_file('test_images/cathedral.jpg', 'test_images/qis_uploadfile.jpg')
            # Upload
            rv = self.file_upload(self.app, dst_file, 'test_images', 'rename')
            self.assertEqual(rv.status_code, 200)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 1)
            self.assertIn('/tmp/qis_uploadfile.jpg', obj)
            imgdata = obj['/tmp/qis_uploadfile.jpg']
            self.assertGreater(imgdata['id'], 0)
            # Make sure it was renamed with -001 appended
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile-001.jpg')
            # Make sure it works
            rv = self.app.get('/image?src=test_images/qis_uploadfile-001.jpg')
            self.assertEqual(rv.status_code, 200)
        finally:
            # Remove the test files
            os.remove(dst_file)
            self.delete_image_and_data('test_images/qis_uploadfile.jpg')
            self.delete_image_and_data('test_images/qis_uploadfile-001.jpg')

    # Multiple file uploads - expecting success
    def test_file_upload_multi(self):
        self.login('admin', 'admin')
        # Copy test files to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file1 = '/tmp/qis_uploadfile1.jpg'
        dst_file2 = '/tmp/qis_uploadfile2.jpg'
        shutil.copy(src_file, dst_file1)
        shutil.copy(src_file, dst_file2)
        try:
            rv = self.multi_file_upload(
                self.app,
                [dst_file1, dst_file2],
                'test_images',
                '0'
            )
            self.assertEqual(rv.status_code, 200)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 2)
            imgdata = obj['/tmp/qis_uploadfile1.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile1.jpg')
            self.assertGreater(imgdata['id'], 0)
            self.assertTrue(path_exists('test_images/qis_uploadfile1.jpg'))
            imgdata = obj['/tmp/qis_uploadfile2.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile2.jpg')
            self.assertGreater(imgdata['id'], 0)
            self.assertTrue(path_exists('test_images/qis_uploadfile2.jpg'))
        finally:
            # Remove the test files
            os.remove(dst_file1)
            os.remove(dst_file2)
            self.delete_image_and_data('test_images/qis_uploadfile1.jpg')
            self.delete_image_and_data('test_images/qis_uploadfile2.jpg')

    # Multiple file uploads - with overwrite no
    def test_file_upload_multi_overwrite_no(self):
        self.login('admin', 'admin')
        # Copy test files to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file1 = '/tmp/qis_uploadfile1.jpg'
        dst_file2 = '/tmp/qis_uploadfile2.jpg'
        shutil.copy(src_file, dst_file1)
        shutil.copy(src_file, dst_file2)
        try:
            # Make one of the files exist already
            copy_file('test_images/cathedral.jpg', 'test_images/qis_uploadfile2.jpg')
            # Test 1 file success, 1 file failure
            rv = self.multi_file_upload(
                self.app,
                [dst_file1, dst_file2],
                'test_images',
                '0'  # This will break now on dst_file2
            )
            self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertEqual(obj['status'], API_CODES.ALREADY_EXISTS)
            obj = obj['data']
            self.assertEqual(len(obj), 2)
            # First entry should be image info
            imgdata = obj['/tmp/qis_uploadfile1.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile1.jpg')
            self.assertGreater(imgdata['id'], 0)
            # Second entry should be error info
            imgdata = obj['/tmp/qis_uploadfile2.jpg']
            self.assertNotIn('id', imgdata)
            self.assertIn('error', imgdata)
            self.assertEqual(imgdata['error']['status'], API_CODES.ALREADY_EXISTS)
            self.assertIn('already exists', imgdata['error']['message'])
        finally:
            # Remove the test files
            os.remove(dst_file1)
            os.remove(dst_file2)
            self.delete_image_and_data('test_images/qis_uploadfile1.jpg')
            self.delete_image_and_data('test_images/qis_uploadfile2.jpg')

    # Multiple file uploads - with overwrite yes
    def test_file_upload_multi_overwrite_yes(self):
        self.login('admin', 'admin')
        # Copy test files to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file1 = '/tmp/qis_uploadfile1.jpg'
        dst_file2 = '/tmp/qis_uploadfile2.jpg'
        shutil.copy(src_file, dst_file1)
        shutil.copy(src_file, dst_file2)
        try:
            # Make both files exist already
            copy_file('test_images/cathedral.jpg', 'test_images/qis_uploadfile1.jpg')
            copy_file('test_images/cathedral.jpg', 'test_images/qis_uploadfile2.jpg')
            # Test overwrites
            rv = self.multi_file_upload(
                self.app,
                [dst_file1, dst_file2],
                'test_images',
                '1'
            )
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 2)
            # Both entries should be image info
            imgdata = obj['/tmp/qis_uploadfile1.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile1.jpg')
            self.assertGreater(imgdata['id'], 0)
            imgdata = obj['/tmp/qis_uploadfile2.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile2.jpg')
            self.assertGreater(imgdata['id'], 0)
        finally:
            # Remove the test files
            os.remove(dst_file1)
            os.remove(dst_file2)
            self.delete_image_and_data('test_images/qis_uploadfile1.jpg')
            self.delete_image_and_data('test_images/qis_uploadfile2.jpg')

    # v2.7.1 Multiple file uploads - with dupe filenames (from different source directories)
    def test_file_upload_multi_dupe_filenames(self):
        self.login('admin', 'admin')
        # Copy test files to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_dir1 = '/tmp/qis_temp1'
        dst_dir2 = '/tmp/qis_temp2'
        dst_file1 = dst_dir1 + '/qis_uploadfile.jpg'  # } same
        dst_file2 = dst_dir2 + '/qis_uploadfile.jpg'  # } filenames
        os.mkdir(dst_dir1)
        os.mkdir(dst_dir2)
        shutil.copy(src_file, dst_file1)
        shutil.copy(src_file, dst_file2)
        try:
            rv = self.multi_file_upload(
                self.app,
                [dst_file1, dst_file2],
                'test_images',
                '0'
            )
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 2)
            # Both entries should be image info with one file renamed
            imgdata = obj[dst_file1]
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile.jpg')
            self.assertGreater(imgdata['id'], 0)
            imgdata = obj[dst_file2]
            self.assertEqual(imgdata['src'], 'test_images/qis_uploadfile-001.jpg')
            self.assertGreater(imgdata['id'], 0)
        finally:
            # Remove the test files
            shutil.rmtree(dst_dir1)
            shutil.rmtree(dst_dir2)
            self.delete_image_and_data('test_images/qis_uploadfile.jpg')
            self.delete_image_and_data('test_images/qis_uploadfile-001.jpg')

    # v2.7.1 Multiple file uploads - with filenames that accidentally get converted to dupes
    def test_file_upload_multi_dupe_filenames_via_chars(self):
        self.login('admin', 'admin')
        # Copy test files to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file1 = '/tmp/qis_upload.jpg'
        dst_file2 = '/tmp/?qis_upload?.jpg'
        shutil.copy(src_file, dst_file1)
        shutil.copy(src_file, dst_file2)
        # Check that secure_filename() will make filenames the same during upload
        self.assertEqual(secure_filename(dst_file1), secure_filename(dst_file2))
        try:
            rv = self.multi_file_upload(
                self.app,
                [dst_file1, dst_file2],
                'test_images',
                '0'
            )
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 2)
            # Both entries should be image info with one file renamed
            imgdata = obj['/tmp/qis_upload.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_upload.jpg')
            self.assertGreater(imgdata['id'], 0)
            imgdata = obj['/tmp/?qis_upload?.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis_upload-001.jpg')
            self.assertGreater(imgdata['id'], 0)
        finally:
            # Remove the test files
            os.remove(dst_file1)
            os.remove(dst_file2)
            self.delete_image_and_data('test_images/qis_upload.jpg')
            self.delete_image_and_data('test_images/qis_upload-001.jpg')

    # File uploads
    def test_file_upload_unicode(self):
        self.login('admin', 'admin')
        # Copy a test file to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis uplo\xe4d f\xefle.jpg'
        shutil.copy(src_file, dst_file)
        try:
            # Upload
            rv = self.file_upload(self.app, dst_file, 'test_images', '0')
            self.assertEqual(rv.status_code, 200)
            obj = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(len(obj), 1)
            self.assertIn('/tmp/qis uplo\xe4d f\xefle.jpg', obj)
            imgdata = obj['/tmp/qis uplo\xe4d f\xefle.jpg']
            self.assertEqual(imgdata['src'], 'test_images/qis uplo\xe4d f\xefle.jpg')
            self.assertGreater(imgdata['id'], 0)
            # Make sure it works
            rv = self.app.get('/image?src=test_images/qis uplo\xe4d f\xefle.jpg')
            self.assertEqual(rv.status_code, 200)
            db_img = dm.get_image(src='test_images/qis uplo\xe4d f\xefle.jpg')
            self.assertIsNotNone(db_img, 'Upload did not create image data')
        finally:
            # Remove the test files
            os.remove(dst_file)
            self.delete_image_and_data('test_images/qis uplo\xe4d f\xefle.jpg')

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
        pm.reset_folder_permissions()
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
            # Reset the default permission to None
            set_default_public_permission(FolderPermission.ACCESS_NONE)
            set_default_internal_permission(FolderPermission.ACCESS_NONE)
            # test_images should not be viewable
            rv = self.app.get('/image?src=test_images/cathedral.jpg')
            assert rv.status_code == API_CODES.UNAUTHORISED
            # Set a user's group to allow view for root folder
            setup_user_account('kryten', 'none')
            db_group = dm.get_group(groupname='kryten-group')
            db_folder = dm.get_folder(folder_path='')
            dm.save_object(FolderPermission(db_folder, db_group, FolderPermission.ACCESS_VIEW))
            pm.reset_folder_permissions()
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
            pm.reset_folder_permissions()
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
            set_default_internal_permission(FolderPermission.ACCESS_DOWNLOAD)

    # Test image and page access (folder permissions)
    def test_folder_permissions(self):
        temp_file = '/tmp/qis_uploadfile.jpg'
        temp_image_path = 'test_images/qis_uploadfile.jpg'
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
            # Reset the default permission to None
            set_default_public_permission(FolderPermission.ACCESS_NONE)
            set_default_internal_permission(FolderPermission.ACCESS_NONE)
            # Create test user with no permission overrides, log in
            setup_user_account('kryten', 'none')
            self.login('kryten', 'kryten')
            db_group = dm.get_group(groupname='kryten-group')
            db_folder = dm.get_folder(folder_path='')
            db_test_folder = dm.get_folder(folder_path='test_images')
            # Run numbered tests - first with no permission
            fp = FolderPermission(db_folder, db_group, FolderPermission.ACCESS_NONE)
            fp = dm.save_object(fp, refresh=True)
            pm.reset_folder_permissions()
            test_pages((False, False, False, False, False, False))
            # Also test permission tracing (ATPT)
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_NONE, 'Trace is ' + _trace_to_str(ptrace)
            # With view permission
            fp.access = FolderPermission.ACCESS_VIEW
            dm.save_object(fp)
            pm.reset_folder_permissions()
            test_pages((True, True, True, False, False, False))
            # ATPT
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_VIEW, 'Trace is ' + _trace_to_str(ptrace)
            # With download permission
            fp.access = FolderPermission.ACCESS_DOWNLOAD
            dm.save_object(fp)
            pm.reset_folder_permissions()
            test_pages((True, True, True, True, False, False))
            # ATPT
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_DOWNLOAD, 'Trace is ' + _trace_to_str(ptrace)
            # With edit permission
            fp.access = FolderPermission.ACCESS_EDIT
            dm.save_object(fp)
            pm.reset_folder_permissions()
            test_pages((True, True, True, True, True, False))
            # ATPT
            with self.app as this_session:
                this_session.get('/')
                ptrace = pm._trace_folder_permissions(db_test_folder, get_session_user(), check_consistency=True)
                assert ptrace['access'] == FolderPermission.ACCESS_EDIT, 'Trace is ' + _trace_to_str(ptrace)
            # With upload permission
            fp.access = FolderPermission.ACCESS_UPLOAD
            dm.save_object(fp)
            pm.reset_folder_permissions()
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
            self.delete_image_and_data(temp_image_path)
            set_default_public_permission(FolderPermission.ACCESS_DOWNLOAD)
            set_default_internal_permission(FolderPermission.ACCESS_DOWNLOAD)

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

    # Test the ETag header behaves as it should
    def test_etag_variations(self):
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

    # v4.1 #11 Make an attempt to filter out secrets from error messages
    def test_error_message_redaction(self):
        import imageserver.views_util
        imageserver.views_util._safe_error_str_replacements = None
        # The XREF setting is just one thing that could be sensitive, should not appear in errors
        flask_app.config['XREF_TRACKING_URL'] = 'https://my.internal.service/'
        dummy_error = 'Failed to invoke URL ' + flask_app.config['XREF_TRACKING_URL']
        for api in ['/image', '/original']:
            with mock.patch('imageserver.views.invoke_http_async') as mockhttp:
                mockhttp.side_effect = Exception(dummy_error)
                rv = self.app.get(api + '?src=test_images/cathedral.jpg&xref=1')
                self.assertEqual(rv.status_code, 500)
                err_msg = rv.data.decode('utf8')
                self.assertIn('Failed to invoke URL', err_msg)
                # The setting value should have been replaced with the setting name
                self.assertNotIn(flask_app.config['XREF_TRACKING_URL'], err_msg)
                self.assertIn('XREF_TRACKING_URL', err_msg)


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
        header1 = cm._get_slot_header(1, True)
        self.assertEqual(len(header1), SLOT_HEADER_SIZE)
        header2 = cm._get_slot_header(MAX_OBJECT_SLOTS, True)
        self.assertEqual(len(header2), SLOT_HEADER_SIZE)


class UtilityTests(unittest.TestCase):
    def test_image_attrs_serialisation(self):
        ia = ImageAttrs('some/path', -1, page=2, iformat='gif', template='smalljpeg',
                        width=2000, height=1000, size_fit=False,
                        fill='black', colorspace='rgb', strip=False,
                        tile_spec=(3, 16))
        ia_dict = ia.to_dict()
        self.assertEqual(ia_dict['template'], 'smalljpeg')
        self.assertEqual(ia_dict['fill'], 'black')
        self.assertEqual(ia_dict['page'], 2)
        self.assertEqual(ia_dict['size_fit'], False)
        self.assertEqual(ia_dict['format'], 'gif')
        self.assertEqual(ia_dict['colorspace'], 'rgb')
        self.assertEqual(ia_dict['width'], 2000)
        self.assertEqual(ia_dict['height'], 1000)
        self.assertEqual(ia_dict['tile'], (3, 16))
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
            'width': {'value': 2000},
            'height': {'value': 1000},
            'tile': {'value': (3, 16)},
            'expiry_secs': {'value': 50000},
            'record_stats': {'value': True}
        })
        self.assertEqual(ta.name(), 'abcdef')
        self.assertEqual(ta.get_image_attrs().filename(), 'abcdef')
        self.assertEqual(ta.get_image_attrs().tile_spec(), (3, 16))
        self.assertEqual(ta.expiry_secs(), 50000)
        self.assertEqual(ta.record_stats(), True)
        self.assertIsNone(ta.attachment())
        # Test values dict
        ta_dict = ta.get_values_dict()
        self.assertEqual(ta_dict['filename'], 'abcdef')
        self.assertEqual(ta_dict['width'], 2000)
        self.assertEqual(ta_dict['height'], 1000)
        self.assertEqual(ta_dict['tile'], (3, 16))
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
