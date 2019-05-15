#
# Quru Image Server
#
# Document:      test_api.py
# Date started:  28 Sep 2015
# By:            Matt Fozard
# Purpose:       Contains the image server API test suite
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
# 28Sep2015  Matt  Moved API tests out from tests.py
#

import base64
import datetime
import io
import json
import os
import pickle
import time
import unittest

from werkzeug.urls import url_quote_plus


from . import tests as main_tests

from imageserver.flask_app import app as flask_app
from imageserver.flask_app import cache_engine as cm
from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import task_engine as tm
from imageserver.flask_app import permissions_engine as pm

from imageserver.api_util import API_CODES
from imageserver.errors import DoesNotExistError
from imageserver.filesystem_manager import (
    copy_file, delete_dir, delete_file, make_dirs
)
from imageserver.filesystem_manager import (
    get_abs_path, ensure_path_exists, path_exists
)
from imageserver.filesystem_sync import (
    auto_sync_existing_file, auto_sync_file, auto_sync_folder
)
from imageserver.flask_util import internal_url_for
from imageserver.models import (
    Folder, Group, User, Image, ImageHistory,
    FolderPermission, Property, Task
)
from imageserver.util import strip_sep, unicode_to_utf8


# Module level setUp and tearDown
def setUpModule():
    main_tests.init_tests()
def tearDownModule():
    main_tests.cleanup_tests()


class ImageServerAPITests(main_tests.BaseTestCase):
    # Utility - base64 encode a UTF8 string, returning an ASCII string
    def _base64_encode(self, s):
        return base64.b64encode(bytes(s, 'utf8')).decode('ascii')

    # Utility - checks that an API response is JSON with the expected status code
    def assert_json_response_code(self, response, expected_code):
        self.assertEqual(response.status_code, expected_code)
        self.assertIn('application/json', response.headers['Content-Type'])
        obj = json.loads(response.data.decode('utf8'))
        self.assertEqual(obj['status'], expected_code)

    # API token login - bad parameters
    def test_token_login_bad_params(self):
        # Missing params
        rv = self.app.post('/api/token/')
        self.assert_json_response_code(rv, API_CODES.INVALID_PARAM)
        # Invalid username
        rv = self.app.post('/api/token/', data={
            'username': 'unclebulgaria',
            'password': 'wimbledon'
        })
        self.assert_json_response_code(rv, API_CODES.UNAUTHORISED)
        # Invalid password
        rv = self.app.post('/api/token/', data={
            'username': 'admin',
            'password': 'wimbledon'
        })
        self.assert_json_response_code(rv, API_CODES.UNAUTHORISED)

    # API token login - normal with username+password parameters
    def test_token_login(self):
        rv = self.app.get('/api/admin/groups/')
        self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
        # Login
        main_tests.setup_user_account('kryten', 'admin_all', allow_api=True)
        token = self.api_login('kryten', 'kryten')
        creds = self._base64_encode(token + ':password')
        # Try again
        rv = self.app.get('/api/admin/groups/', headers={
            'Authorization': 'Basic ' + creds
        })
        self.assert_json_response_code(rv, API_CODES.SUCCESS)

    # API token login - normal with username+password http basic auth
    def test_token_login_http_basic_auth(self):
        main_tests.setup_user_account('kryten', 'none', allow_api=True)
        creds = self._base64_encode('kryten:kryten')
        rv = self.app.post('/api/token/', headers={
            'Authorization': 'Basic ' + creds
        })
        self.assert_json_response_code(rv, API_CODES.SUCCESS)

    # API token login - account disabled
    def test_token_login_user_disabled(self):
        main_tests.setup_user_account('kryten', 'admin_users', allow_api=True)
        user = dm.get_user(username='kryten')
        self.assertIsNotNone(user)
        user.status = User.STATUS_DELETED
        dm.save_object(user)
        self.assertRaises(AssertionError, self.api_login, 'kryten', 'kryten')

    # API token login - user.allow_api flag false
    def test_token_allow_api_false(self):
        main_tests.setup_user_account('kryten', 'admin_users', allow_api=False)
        self.assertRaises(AssertionError, self.api_login, 'kryten', 'kryten')

    # Test you cannot request a new token by authenticating with an older (still valid) token
    def test_no_token_extension(self):
        main_tests.setup_user_account('kryten', 'none', allow_api=True)
        token = self.api_login('kryten', 'kryten')
        creds = self._base64_encode(token + ':password')
        # Try to get a new token with only the old token
        rv = self.app.post('/api/token/', headers={
            'Authorization': 'Basic ' + creds
        })
        self.assert_json_response_code(rv, API_CODES.UNAUTHORISED)

    # Test that tokens expire
    def test_token_expiry(self):
        old_expiry = flask_app.config['API_TOKEN_EXPIRY_TIME']
        # Enable CSRF - there have been bugs with this overring API responses
        flask_app.config['TESTING'] = False
        try:
            main_tests.setup_user_account('kryten', 'admin_users', allow_api=True)
            # Get a 1 second token
            flask_app.config['API_TOKEN_EXPIRY_TIME'] = 1
            token = self.api_login('kryten', 'kryten')
            creds = self._base64_encode(token + ':password')
            # Token should work now
            rv = self.app.get('/api/admin/users/', headers={
                'Authorization': 'Basic ' + creds
            })
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            # That 1 second expiry is anything from 1 to 2s in reality
            time.sleep(2)
            # Token should now be expired
            rv = self.app.get('/api/admin/users/', headers={
                'Authorization': 'Basic ' + creds
            })
            self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
            # Also test a POST as this could (but shouldn't) trigger CSRF
            rv = self.app.post('/api/admin/users/', headers={
                'Authorization': 'Basic ' + creds
            })
            self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
        finally:
            flask_app.config['API_TOKEN_EXPIRY_TIME'] = old_expiry
            flask_app.config['TESTING'] = True

    # Test you cannot authenticate with a bad token
    def test_bad_token(self):
        # Enable CSRF - there have been bugs with this overring API responses
        flask_app.config['TESTING'] = False
        try:
            main_tests.setup_user_account('kryten', 'admin_users', allow_api=True)
            token = self.api_login('kryten', 'kryten')
            # Tampered token
            token = ('0' + token[1:]) if token[0] != '0' else ('1' + token[1:])
            creds = self._base64_encode(token + ':password')
            rv = self.app.get('/api/admin/users/1/', headers={
                'Authorization': 'Basic ' + creds
            })
            self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
            # Blank token
            token = ''
            creds = self._base64_encode(token + ':password')
            rv = self.app.get('/api/admin/users/1/', headers={
                'Authorization': 'Basic ' + creds
            })
            self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
            # Also test a POST as this could (but shouldn't) trigger CSRF
            rv = self.app.post('/api/admin/users/', headers={
                'Authorization': 'Basic ' + creds
            })
            self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
        finally:
            flask_app.config['TESTING'] = True

    # Folder list
    def test_api_list(self):
        # Unauthorised path
        rv = self.app.get('/api/list/?path=../../../etc/')
        self.assert_json_response_code(rv, API_CODES.UNAUTHORISED)
        # Invalid path
        rv = self.app.get('/api/list/?path=non-existent')
        self.assert_json_response_code(rv, API_CODES.NOT_FOUND)
        # Valid request
        rv = self.app.get('/api/list/?path=test_images')
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(len(obj['data']), 0)
        self.assertIn('filename', obj['data'][0])
        self.assertIn('url', obj['data'][0])
        # Valid request with extra image params
        rv = self.app.get('/api/list/?path=test_images&width=500')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertIn('width=500', obj['data'][0]['url'])
        # The list should be sorted
        imlist = obj['data']
        self.assertLess(imlist[0]['filename'], imlist[1]['filename'])
        self.assertLess(imlist[1]['filename'], imlist[2]['filename'])
        self.assertLess(imlist[2]['filename'], imlist[3]['filename'])
        self.assertLess(imlist[3]['filename'], imlist[4]['filename'])

    # Folder list - v2.2.1 support paging
    def test_api_list_paging(self):
        # Maximum 1000
        rv = self.app.get('/api/list/?path=test_images&limit=1001')
        self.assert_json_response_code(rv, API_CODES.INVALID_PARAM)
        # Test limit
        rv = self.app.get('/api/list/?path=test_images&limit=3')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj1 = json.loads(rv.data.decode('utf8'))
        list1 = obj1['data']
        self.assertEqual(len(list1), 3)
        # Test start + limit
        rv = self.app.get('/api/list/?path=test_images&start=1&limit=3')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj2 = json.loads(rv.data.decode('utf8'))
        list2 = obj2['data']
        self.assertEqual(len(list2), 3)
        # So list2 should be list1 offset by 1
        self.assertNotIn(list1[0], list2)
        self.assertEqual(list2[0], list1[1])
        self.assertEqual(list2[1], list1[2])
        self.assertNotIn(list2[2], list1)
        # Start from the end
        rv = self.app.get('/api/list/?path=test_images&start=999999')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj3 = json.loads(rv.data.decode('utf8'))
        list3 = obj3['data']
        self.assertEqual(len(list3), 0)

    # v2.6.4 Folder list should now return non-image files
    # v4.1   Also tests folder list for newly created files
    def test_api_list_non_image(self):
        temp_folder = 'test_list'
        make_dirs(temp_folder)
        try:
            copy_file('test_images/cathedral.jpg', temp_folder + '/valid.jpg')
            copy_file('test_images/cathedral.jpg', temp_folder + '/badfile.docx')
            # Folder list should return 2 files, one supported, and one not, sorted
            rv = self.app.get('/api/list/?path=' + temp_folder)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertEqual(len(obj['data']), 2)
            f1 = obj['data'][0]
            f2 = obj['data'][1]
            # f1 not supported
            self.assertEqual('badfile.docx', f1['filename'])
            self.assertFalse(f1['supported'])
            self.assertEqual('', f1['url'])
            self.assertNotIn('history', f1)  # v4.1
            # f2 supported
            self.assertEqual('valid.jpg', f2['filename'])
            self.assertTrue(f2['supported'])
            self.assertIn('valid.jpg', f2['url'])
            self.assertNotIn('history', f2)  # v4.1
        finally:
            delete_dir(temp_folder, recursive=True)

    # Image details
    def test_api_details(self):
        # Unauthorised path
        rv = self.app.get('/api/details/?src=../../../etc/')
        self.assert_json_response_code(rv, API_CODES.UNAUTHORISED)
        # Try requesting a folder
        rv = self.app.get('/api/details/?src=test_images')
        assert rv.status_code == API_CODES.NOT_FOUND
        # Valid request
        rv = self.app.get('/api/details/?src=test_images/cathedral.jpg')
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['width'] == 1600, 'Did not find data.width=1600, got ' + str(obj)
        assert obj['data']['height'] == 1200

    # v4.1 Image details for a newly created file
    def test_api_details_new_file(self):
        temp_file = 'test_images/cathedral-copy.jpg'
        try:
            copy_file('test_images/cathedral.jpg', temp_file)
            rv = self.app.get('/api/details/?src=' + temp_file)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            img = json.loads(rv.data.decode('utf8'))['data']
            self.assertGreater(img['id'], 0)
            self.assertEqual(img['src'], temp_file)
            self.assertGreater(img['width'], 0)
            # v4.1 Newly found files were being returned differently, they should be standard format
            self.assertNotIn('history', img)
        finally:
            delete_file(temp_file)

    # v2.6.4 Image details for a non-image file
    def test_api_details_non_image(self):
        temp_file = 'test_images/badfile.docx'
        with open(get_abs_path(temp_file), 'w') as f:
            f.write('<docx>I am not an image</docx>')
        try:
            rv = self.app.get('/api/details/?src=' + temp_file)
            self.assert_json_response_code(rv, API_CODES.IMAGE_ERROR)
        finally:
            delete_file(temp_file)

    # Database admin API - images
    def test_data_api_images(self):
        # Get image ID
        rv = self.app.get('/api/details/?src=test_images/cathedral.jpg')
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        image_id = json.loads(rv.data.decode('utf8'))['data']['id']
        # Set API URL
        api_url = '/api/admin/images/' + str(image_id) + '/'
        # Check no access when not logged in
        rv = self.app.get(api_url)
        self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
        # Log in without edit permission
        main_tests.setup_user_account('kryten', 'none')
        self.login('kryten', 'kryten')
        # Test PUT (should fail)
        rv = self.app.put(api_url, data={
            'title': 'test title',
            'description': 'test description'
        })
        assert rv.status_code == API_CODES.UNAUTHORISED
        # Log in with edit permission
        main_tests.setup_user_account('kryten', 'admin_files')
        self.login('kryten', 'kryten')
        # Test PUT
        rv = self.app.put(api_url, data={
            'title': 'test title',
            'description': 'test description'
        })
        assert rv.status_code == API_CODES.SUCCESS
        # Test GET
        rv = self.app.get(api_url)
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['id'] == image_id
        assert obj['data']['title'] == 'test title'
        assert obj['data']['description'] == 'test description'

    # Database admin API - users
    def test_data_api_users(self):
        # Not logged in - getting details should fail
        rv = self.app.get('/api/admin/users/2/')
        self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
        #
        # Log in as std user
        #
        main_tests.setup_user_account('kryten', 'none')
        self.login('kryten', 'kryten')
        # Logged in std user - user list should fail
        rv = self.app.get('/api/admin/users/')
        assert rv.status_code == API_CODES.UNAUTHORISED
        # Logged in std user - getting another's details should fail
        rv = self.app.get('/api/admin/users/1/')
        assert rv.status_code == API_CODES.UNAUTHORISED
        # Logged in std user - getting our own details should be OK
        rv = self.app.get('/api/admin/users/2/')
        assert rv.status_code == API_CODES.SUCCESS
        # We should never send out the password
        obj = json.loads(rv.data.decode('utf8'))
        assert 'password' not in obj['data']
        #
        # Log in as user with user admin
        #
        main_tests.setup_user_account('kryten', 'admin_users')
        self.login('kryten', 'kryten')
        # Logged in - getting another's details should now work
        rv = self.app.get('/api/admin/users/1/')
        assert rv.status_code == API_CODES.SUCCESS
        # List users
        rv = self.app.get('/api/admin/users/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert len(obj['data']) > 1
        # We should never send out the password
        assert 'password' not in obj['data'][0]
        # Create a user - duplicate username
        new_user_data = {
            'first_name': 'Miles',
            'last_name': 'Davis',
            'email': '',
            'username': 'admin',  # Dupe
            'password': 'abcdefghij',
            'auth_type': User.AUTH_TYPE_PASSWORD,
            'api_user': False,
            'status': User.STATUS_ACTIVE
        }
        rv = self.app.post('/api/admin/users/', data=new_user_data)
        assert rv.status_code == API_CODES.ALREADY_EXISTS, str(rv)
        # Create a user - OK username
        new_user_data['username'] = 'miles'
        rv = self.app.post('/api/admin/users/', data=new_user_data)
        assert rv.status_code == API_CODES.SUCCESS, 'Got status ' + str(rv.status_code)
        obj = json.loads(rv.data.decode('utf8'))
        new_user_id = obj['data']['id']
        # We should never send out the password
        assert 'password' not in obj['data']
        # Update the user
        new_user_data['id'] = new_user_id
        new_user_data['first_name'] = 'Joe'
        rv = self.app.put('/api/admin/users/' + str(new_user_id) + '/', data=new_user_data)
        assert rv.status_code == API_CODES.SUCCESS
        rv = self.app.get('/api/admin/users/' + str(new_user_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['first_name'] == 'Joe'
        # We should never send out the password
        assert 'password' not in obj['data']
        # Delete a user
        rv = self.app.delete('/api/admin/users/' + str(new_user_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        rv = self.app.get('/api/admin/users/' + str(new_user_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['status'] == User.STATUS_DELETED
        # We should never send out the password
        assert 'password' not in obj['data']

    # v4.1 #12 User list API - New status filter, only return active users by default
    def test_data_api_users_status_filter(self):
        self.login('admin', 'admin')
        # Create some users
        k1 = main_tests.setup_user_account('kryten1', 'none')
        k2 = main_tests.setup_user_account('kryten2', 'none')
        k3 = main_tests.setup_user_account('kryten3', 'none')
        k4 = main_tests.setup_user_account('kryten4', 'none')
        # Delete some of them
        rv = self.app.delete('/api/admin/users/' + str(k1.id) + '/')
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        rv = self.app.delete('/api/admin/users/' + str(k2.id) + '/')
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        # List users - default filter should be active only
        rv = self.app.get('/api/admin/users/')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(len(obj['data']), 0)
        self.assertTrue(all([
            (user['status'] == User.STATUS_ACTIVE) for user in obj['data']
        ]))
        # List users with filter 0
        rv = self.app.get('/api/admin/users/?status=0')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(len(obj['data']), 0)
        self.assertTrue(all([
            (user['status'] == User.STATUS_DELETED) for user in obj['data']
        ]))
        # List users with filter any
        rv = self.app.get('/api/admin/users/?status=any')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        statuses = [user['status'] for user in obj['data']]
        self.assertIn(User.STATUS_ACTIVE, statuses)
        self.assertIn(User.STATUS_DELETED, statuses)

    # Database admin API - groups
    def test_data_api_groups(self):
        # Not logged in - getting group details should fail
        rv = self.app.get('/api/admin/groups/')
        assert rv.status_code == API_CODES.REQUIRES_AUTH
        rv = self.app.get('/api/admin/groups/' + str(Group.ID_EVERYONE) + '/')
        assert rv.status_code == API_CODES.REQUIRES_AUTH
        # Log in as std user
        main_tests.setup_user_account('kryten', 'none')
        self.login('kryten', 'kryten')
        # Logged in std user - access should be denied
        rv = self.app.get('/api/admin/groups/')
        assert rv.status_code == API_CODES.UNAUTHORISED
        rv = self.app.get('/api/admin/groups/' + str(Group.ID_EVERYONE) + '/')
        assert rv.status_code == API_CODES.UNAUTHORISED
        #
        # Log in as user with basic group access
        #
        main_tests.setup_user_account('kryten', 'admin_users')
        self.login('kryten', 'kryten')
        # Logged in basic admin - getting group details should be OK
        rv = self.app.get('/api/admin/groups/' + str(Group.ID_EVERYONE) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        # Check that permissions are included
        obj = json.loads(rv.data.decode('utf8'))
        assert 'permissions' in obj['data']
        # Check that the group's user list is included
        assert 'users' in obj['data']
        # Check that passwords aren't returned in the group's user list
        assert len(obj['data']['users']) > 0
        assert 'password' not in obj['data']['users'][0]
        # List groups
        rv = self.app.get('/api/admin/groups/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert len(obj['data']) > 0
        # Check the group list does *not* include user lists
        assert 'users' not in obj['data'][0]
        # Creating and deleting a group should fail
        new_group_data = {
            'name': 'My Group',
            'description': 'This is a test group',
            'group_type': Group.GROUP_TYPE_LOCAL
        }
        rv = self.app.post('/api/admin/groups/', data=new_group_data)
        assert rv.status_code == API_CODES.UNAUTHORISED, rv
        rv = self.app.delete('/api/admin/groups/' + str(Group.ID_EVERYONE) + '/')
        assert rv.status_code == API_CODES.UNAUTHORISED, rv
        # Updating a group should change the name/description but not the permissions
        user_group = dm.get_group(groupname='kryten-group')
        assert user_group is not None
        change_data = {
            'name': 'Kryten\'s Group',
            'description': 'Renamed group desc',
            'group_type': Group.GROUP_TYPE_LOCAL,
            'access_reports': '1',
            'access_admin_files': '1',
            'access_admin_all': '1'
        }
        rv = self.app.put('/api/admin/groups/' + str(user_group.id) + '/', data=change_data)
        assert rv.status_code == API_CODES.SUCCESS
        rv = self.app.get('/api/admin/groups/' + str(user_group.id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['name'] == 'Kryten\'s Group'            # Changed
        assert obj['data']['description'] == 'Renamed group desc'  # Changed
        assert obj['data']['permissions']['reports'] == False      # Unchanged
        assert obj['data']['permissions']['admin_files'] == False
        assert obj['data']['permissions']['admin_all'] == False
        # Check that passwords aren't returned in the group's user list
        assert len(obj['data']['users']) > 0
        assert 'password' not in obj['data']['users'][0]
        # Adding a user to Everyone should be allowed
        rv = self.app.post('/api/admin/groups/' + str(Group.ID_EVERYONE) + '/members/', data={'user_id': 3})
        assert rv.status_code == API_CODES.SUCCESS
        # But adding a user to Administrators should be blocked
        su_group = dm.get_group(Group.ID_ADMINS)
        assert su_group is not None
        rv = self.app.post('/api/admin/groups/' + str(su_group.id) + '/members/', data={'user_id': 3})
        assert rv.status_code == API_CODES.UNAUTHORISED
        #
        # Log in as user with full group access
        #
        self.login('admin', 'admin')
        # Create a group - duplicate name
        new_group_data = {
            'name': 'Public',
            'description': 'This is a test group',
            'group_type': Group.GROUP_TYPE_LOCAL
        }
        rv = self.app.post('/api/admin/groups/', data=new_group_data)
        assert rv.status_code == API_CODES.ALREADY_EXISTS, str(rv)
        # Create a group - OK name
        new_group_data['name'] = 'Company X'
        rv = self.app.post('/api/admin/groups/', data=new_group_data)
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        new_group_id = obj['data']['id']
        # Updating the group should change the name/description *and* the permissions
        new_group_data['id'] = new_group_id
        new_group_data['name'] = 'Company XYZ'
        new_group_data['description'] = 'Company XYZ\'s users'
        new_group_data['access_reports'] = '1'
        new_group_data['access_admin_users'] = '1'
        new_group_data['access_admin_all'] = '1'
        rv = self.app.put('/api/admin/groups/' + str(new_group_id) + '/', data=new_group_data)
        assert rv.status_code == API_CODES.SUCCESS
        rv = self.app.get('/api/admin/groups/' + str(new_group_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['name'] == 'Company XYZ'
        assert obj['data']['description'] == 'Company XYZ\'s users'
        assert obj['data']['permissions']['reports'] == True
        assert obj['data']['permissions']['admin_users'] == True
        assert obj['data']['permissions']['admin_all'] == True
        # Add users to the group
        assert len(obj['data']['users']) == 0
        rv = self.app.post('/api/admin/groups/' + str(new_group_id) + '/members/', data={'user_id': 1})
        assert rv.status_code == API_CODES.SUCCESS, str(rv)
        rv = self.app.post('/api/admin/groups/' + str(new_group_id) + '/members/', data={'user_id': 2})
        assert rv.status_code == API_CODES.SUCCESS
        rv = self.app.get('/api/admin/groups/' + str(new_group_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert len(obj['data']['users']) == 2
        # Delete a user from the group
        rv = self.app.delete('/api/admin/groups/' + str(new_group_id) + '/members/2/')
        assert rv.status_code == API_CODES.SUCCESS, str(rv)
        rv = self.app.get('/api/admin/groups/' + str(new_group_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert len(obj['data']['users']) == 1
        # Delete the group and remaining members
        rv = self.app.delete('/api/admin/groups/' + str(new_group_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS, str(rv)
        rv = self.app.get('/api/admin/groups/' + str(new_group_id) + '/')
        assert rv.status_code == API_CODES.NOT_FOUND
        # Deleting a system group should fail
        rv = self.app.delete('/api/admin/groups/' + str(Group.ID_EVERYONE) + '/')
        assert rv.status_code == API_CODES.INVALID_PARAM, rv

    # #2054 Bug fixes where the current user could lock themselves out
    #       or lock out the admin user
    def test_group_admin_lockout(self):
        # Create and log in as a user with full group access
        main_tests.setup_user_account('kryten', 'admin_permissions')
        self.login('kryten', 'kryten')
        db_user = dm.get_user(username='kryten', load_groups=True)
        # main_tests.setup_user_account() should have set up 1 group with the admin access
        admin_groups = [g for g in db_user.groups if g.permissions.admin_permissions]
        self.assertEqual(len(admin_groups), 1)
        admin_group = admin_groups[0]
        # Removing admin_permission flag from Administrators group would lock out the admin user
        # Removing admin_users flag from a user's only admin group would lock them out
        group_ids = [
            admin_group.id,  # Test user locking themselves out
            Group.ID_ADMINS  # Test user locking out the admin user
        ]
        for group_id in group_ids:
            db_group = dm.get_group(group_id)
            self.assertIsNotNone(db_group)
            set_users_flag = (group_id == Group.ID_ADMINS)
            group_data = {
                'name': db_group.name,
                'description': db_group.description,
                'group_type': db_group.group_type,
                'access_folios': db_group.permissions.folios,
                'access_reports': db_group.permissions.reports,
                'access_admin_users': set_users_flag,
                'access_admin_files': db_group.permissions.admin_files,
                'access_admin_folios': db_group.permissions.admin_folios,
                'access_admin_permissions': False,
                'access_admin_all': False
            }
            rv = self.app.put('/api/admin/groups/' + str(db_group.id) + '/', data=group_data)
            self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
            self.assertIn('would lock', rv.data.decode('utf8'))
            # Double check that the group data has not changed
            db_group_2 = dm.get_group(group_id)
            self.assertIsNotNone(db_group_2)
            self.assertEqual(db_group.permissions.admin_users,
                             db_group_2.permissions.admin_users)
            self.assertEqual(db_group.permissions.admin_permissions,
                             db_group_2.permissions.admin_permissions)
            self.assertEqual(db_group.permissions.admin_all,
                             db_group_2.permissions.admin_all)
        # Removing (any) user from their only admin group would lock them out
        user_groups = [
            (db_user.id, admin_group.id),  # Test user locking themselves out
            (1, Group.ID_ADMINS)           # Test user locking out the admin user
        ]
        for ug in user_groups:
            rv = self.app.delete('/api/admin/groups/' + str(ug[1]) + '/members/' + str(ug[0]) + '/')
            self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
            self.assertIn('would lock', rv.data.decode('utf8'))
            # Double check that the user is still in the group
            db_group = dm.get_group(ug[1], load_users=True)
            group_users = [u.id for u in db_group.users]
            self.assertIn(ug[0], group_users)

    # Database admin API - folderpermissions
    def test_data_api_folder_permissions(self):
        # Not logged in - getting permission details should fail
        rv = self.app.get('/api/admin/permissions/')
        assert rv.status_code == API_CODES.REQUIRES_AUTH
        rv = self.app.get('/api/admin/permissions/1/')
        assert rv.status_code == API_CODES.REQUIRES_AUTH
        # Log in as std user
        main_tests.setup_user_account('kryten', 'none')
        self.login('kryten', 'kryten')
        # Logged in std user - access should be denied
        rv = self.app.get('/api/admin/permissions/')
        assert rv.status_code == API_CODES.UNAUTHORISED
        rv = self.app.get('/api/admin/permissions/1/')
        assert rv.status_code == API_CODES.UNAUTHORISED
        #
        # Log in as user with permissions admin access
        #
        main_tests.setup_user_account('kryten', 'admin_permissions')
        self.login('kryten', 'kryten')
        # Getting permissions should be OK
        rv = self.app.get('/api/admin/permissions/1/')
        assert rv.status_code == API_CODES.SUCCESS
        # Try deleting root public permission (this should fail)
        rv = self.app.delete('/api/admin/permissions/1/')
        assert rv.status_code == API_CODES.INVALID_PARAM
        # Try creating a duplicate root public permission (this should fail)
        root_folder = dm.get_folder(folder_path='')
        pub_group = dm.get_group(Group.ID_PUBLIC)
        rv = self.app.post('/api/admin/permissions/', data={
            'folder_id': root_folder.id,
            'group_id': pub_group.id,
            'access': FolderPermission.ACCESS_VIEW
        })
        assert rv.status_code == API_CODES.ALREADY_EXISTS
        # Get default permission for test_images + public
        test_folder = dm.get_folder(folder_path='test_images')
        assert test_folder is not None
        test_fp = dm.get_nearest_folder_permission(test_folder, pub_group)
        assert test_fp is not None
        assert test_fp.folder_id == root_folder.id                 # See reset_databases()
        assert test_fp.access == FolderPermission.ACCESS_DOWNLOAD  # See reset_databases()
        # Create custom permission for test_images + public
        rv = self.app.post('/api/admin/permissions/', data={
            'folder_id': test_folder.id,
            'group_id': pub_group.id,
            'access': FolderPermission.ACCESS_EDIT
        })
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['id'] > 0
        assert obj['data']['access'] == FolderPermission.ACCESS_EDIT
        custom_p_id = obj['data']['id']
        # Re-read permission for test_images + public
        test_fp = dm.get_nearest_folder_permission(test_folder, pub_group)
        assert test_fp is not None
        assert test_fp.folder_id == test_folder.id
        assert test_fp.access == FolderPermission.ACCESS_EDIT
        # Change the custom permission
        rv = self.app.put('/api/admin/permissions/' + str(custom_p_id) + '/', data={
            'folder_id': test_folder.id,
            'group_id': pub_group.id,
            'access': FolderPermission.ACCESS_ALL
        })
        assert rv.status_code == API_CODES.SUCCESS
        obj = json.loads(rv.data.decode('utf8'))
        assert obj['data']['access'] == FolderPermission.ACCESS_ALL
        # Re-read permission for test_images + public
        test_fp = dm.get_nearest_folder_permission(test_folder, pub_group)
        assert test_fp is not None
        assert test_fp.folder_id == test_folder.id
        assert test_fp.access == FolderPermission.ACCESS_ALL
        # Delete the custom permission again
        rv = self.app.delete('/api/admin/permissions/' + str(custom_p_id) + '/')
        assert rv.status_code == API_CODES.SUCCESS
        # Re-read permission for test_images + public
        test_fp = dm.get_nearest_folder_permission(test_folder, pub_group)
        assert test_fp is not None
        assert test_fp.folder_id == root_folder.id                 # Back to default
        assert test_fp.access == FolderPermission.ACCESS_DOWNLOAD  # Back to default

    # Tests the image template API
    def test_data_api_templates(self):
        # Utility - return dict with None values removed
        def strip_dict(d):
            return dict((k, d[k]) for k in d if d[k]['value'] is not None)
        # Not logged in - getting details should fail
        rv = self.app.get('/api/admin/templates/1/')
        self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)
        # Log in as std user
        main_tests.setup_user_account('kryten', 'none')
        self.login('kryten', 'kryten')
        # Logged in - template details should be available
        rv = self.app.get('/api/admin/templates/2/')
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))['data']
        self.assertEqual(obj['name'], 'SmallJpeg')
        tdict = obj['template']
        self.assertEqual(tdict['format']['value'], 'jpg')
        self.assertEqual(tdict['width']['value'], 200)
        self.assertEqual(tdict['height']['value'], 200)
        self.assertNotIn('size_fit', tdict)
        # Invalid template ID - getting details should fail
        rv = self.app.get('/api/admin/templates/-1/')
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        # List templates
        rv = self.app.get('/api/admin/templates/')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))['data']
        self.assertEqual(len(obj), 3)  # Default, SmallJpeg and Precache
        # Std user cannot update templates
        rv = self.app.put('/api/admin/templates/2/', data={
            'name': 'should fail', 'description': '', 'template': '{}'
        })
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        rv = self.app.delete('/api/admin/templates/2/')
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # Super user can perform updates
        main_tests.setup_user_account('kryten', 'admin_all')
        self.login('kryten', 'kryten')
        # Create
        rv = self.app.post('/api/admin/templates/', data={
            'name': 'new template',
            'description': 'new template desc',
            'template': '''
                { "format": {"value": "png"}, 
                  "tile": {"value": [3, 16]}
                }'''
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))['data']
        self.assertEqual(obj['name'], 'new template')
        new_tmp_id = obj['id']
        self.assertGreater(new_tmp_id, 0)
        self.assertEqual(
            strip_dict(obj['template']),
            {'format': {'value': 'png'}, 'tile': {'value': [3, 16]}}
        )
        # We should be able to use it immediately
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=200&tmp=new template')
        self.assertEqual(rv.status_code, 200)
        self.assertIn('image/png', rv.headers['Content-Type'])
        # Update
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template',
            'description': 'new template desc',
            'template': '''{ "format": {"value": "jpg"} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))['data']
        self.assertEqual(strip_dict(obj['template']), {'format': {'value': 'jpg'}})
        # Changes should take effect immediately
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=200&tmp=new template')
        self.assertEqual(rv.status_code, 200)
        self.assertIn('image/jpeg', rv.headers['Content-Type'])
        # Validation - name must be unique
        rv = self.app.post('/api/admin/templates/', data={
            'name': 'new template', 'description': '', 'template': '''{ "format": {"value": "jpg"} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
        # Validation - name is required
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': '', 'description': '', 'template': '''{ "format": {"value": "jpg"} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        # Validation - format must be supported
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template', 'description': '', 'template': '''{ "format": {"value": "qwerty"} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        # Validation - cropping must be numbers 0 to 1
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template', 'description': '', 'template': '''{ "left": {"value": "abc"} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template', 'description': '', 'template': '''{ "left": {"value": 1.5} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        # Validation - attachment must be a bool
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template', 'description': '', 'template': '''{ "attachment": {"value": 1} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        # Validation - width must be a number
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template', 'description': '', 'template': '''{ "width": {"value": true} }'''
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        # Validation - invalid JSON should be handled (not throw a 500)
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template', 'description': '', 'template': '''this isn't JSON'''
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        # Correct versions of all the above should save OK
        # Also most strings should be lower cased on save (but not file paths)
        rv = self.app.put('/api/admin/templates/' + str(new_tmp_id) + '/', data={
            'name': 'new template', 'description': '', 'template': '''{
                "format": {"value": "JPG"},
                "fill": {"value": "BLUE"},
                "left": {"value": 0.1},
                "attachment": {"value": true},
                "width": {"value": 200},
                "height": {"value": 100},
                "overlay_src": {"value": "Mixed Case/Path.png"},
                "colorspace": {"value": "GRAY"}
            }'''
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))['data']
        self.assertEqual(strip_dict(obj['template']), {
            'format': {'value': 'jpg'},
            'fill': {'value': 'blue'},
            'left': {'value': 0.1},
            'attachment': {'value': True},
            'width': {'value': 200},
            'height': {'value': 100},
            'overlay_src': {'value': 'Mixed Case/Path.png'},
            'colorspace': {'value': 'gray'}
        })
        # Delete
        rv = self.app.delete('/api/admin/templates/' + str(new_tmp_id) + '/')
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Changes should take effect immediately
        rv = self.app.get('/image?src=test_images/cathedral.jpg&width=200&tmp=new template')
        self.assertEqual(rv.status_code, 400)

    def test_system_template_no_delete(self):
        # Get the system default template
        db_prop = dm.get_object(Property, Property.DEFAULT_TEMPLATE)
        self.assertIsNotNone(db_prop)
        db_template = dm.get_image_template(tempname=db_prop.value)
        self.assertIsNotNone(db_template)
        # Try to delete it (this shouldn't be allowed)
        self.login('admin', 'admin')
        rv = self.app.delete('/api/admin/templates/' + str(db_template.id) + '/')
        self.assert_json_response_code(rv, API_CODES.INVALID_PARAM)

    # File admin API - images
    def test_file_api_images(self):
        # Util
        def ensure_file_exists(db_image):
            ensure_path_exists(db_image.src, require_file=True)
        # Tests
        temp_folder = 'test_images_api'
        temp_image = temp_folder + '/image1.jpg'
        moved_image = None
        try:
            # Create a test folder and test image and get their IDs
            make_dirs(temp_folder)
            copy_file('test_images/cathedral.jpg', temp_image)
            rv = self.app.get('/api/details/?src=' + temp_image)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            temp_image_id = json.loads(rv.data.decode('utf8'))['data']['id']
            temp_folder_id = dm.get_folder(folder_path=temp_folder).id
            orig_folder_id = dm.get_folder(folder_path='test_images').id
            # Create a cached image, also creates a cached src-ID entry
            rv = self.app.get('/image?src=' + temp_image)
            assert rv.status_code == 200
            # Check that it does indeed create the cached src-ID
            cached_id = dm.get_or_create_image_id(temp_image, on_create=ensure_file_exists)
            assert cached_id == temp_image_id
            # Not logged in - file ops should fail
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': temp_folder + '/newname.jpg'})
            assert rv.status_code == API_CODES.REQUIRES_AUTH, str(rv)
            rv = self.app.delete('/api/admin/filesystem/images/%d/' % temp_image_id)
            assert rv.status_code == API_CODES.REQUIRES_AUTH, str(rv)
            # Log in as a standard user
            main_tests.setup_user_account('kryten', 'none')
            self.login('kryten', 'kryten')
            # File ops should still fail
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': temp_folder + '/newname.jpg'})
            assert rv.status_code == API_CODES.UNAUTHORISED, str(rv)
            rv = self.app.delete('/api/admin/filesystem/images/%d/' % temp_image_id)
            assert rv.status_code == API_CODES.UNAUTHORISED, str(rv)
            #
            # Log in as a user with file admin
            #
            main_tests.setup_user_account('kryten', 'admin_files')
            self.login('kryten', 'kryten')
            # Rename the file (in the same folder)
            renamed_image = temp_folder + '/newname.jpg'
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': renamed_image})
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            # Check returned object data
            obj = json.loads(rv.data.decode('utf8'))
            assert obj['data']['src'] == renamed_image
            # Check physical file has been renamed
            assert path_exists(temp_image) == False
            assert path_exists(renamed_image) == True
            # Check db record has been updated, and rename history added
            db_image = dm.get_image(temp_image_id, load_history=True)
            assert db_image.status == Image.STATUS_ACTIVE
            assert db_image.src == renamed_image
            assert db_image.folder.id == temp_folder_id
            assert len(db_image.history) == 2   # Create, Rename
            assert db_image.history[1].action == ImageHistory.ACTION_MOVED
            # Check the cached ID has gone for the original path
            got_cached_id = True
            try: cached_id = dm.get_or_create_image_id(temp_image, on_create=ensure_file_exists)
            except DoesNotExistError: got_cached_id = False
            assert got_cached_id == False
            # Check the cached image has gone for the old path
            rv = self.app.get('/image?src=' + temp_image)
            assert rv.status_code == 404
            # Create a new cached image, also creates a cached src-ID entry
            rv = self.app.get('/image?src=' + renamed_image)
            assert rv.status_code == 200
            # Try renaming the test file without a file extension (this should fail)
            invalid_filename = temp_folder + '/newname'
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': invalid_filename})
            assert rv.status_code == API_CODES.INVALID_PARAM, str(rv)
            # Try renaming the test file with '.' in the path (this should fail)
            invalid_filename = temp_folder + '/.newname.jpg'
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': invalid_filename})
            assert rv.status_code == API_CODES.INVALID_PARAM, str(rv)
            # Try renaming the test file with '..' in the path (this should fail)
            invalid_filename = temp_folder + '/..newname.jpg'
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': invalid_filename})
            assert rv.status_code == API_CODES.INVALID_PARAM, str(rv)
            # Try moving the test file into a non-existent folder (this should fail)
            invalid_path = 'non_existent_folder/newname.jpg'
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': invalid_path})
            assert rv.status_code == API_CODES.NOT_FOUND, str(rv) + '\n' + rv.data.decode('utf8')
            # Try moving the test file over an existing image (this should fail)
            existing_image = 'test_images/dorset.jpg'
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': existing_image})
            assert rv.status_code == API_CODES.ALREADY_EXISTS, str(rv)
            # Move the test file into the original folder
            moved_image = 'test_images/newname.jpg'
            rv = self.app.put('/api/admin/filesystem/images/%d/' % temp_image_id,
                              data={'path': moved_image})
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            # Check returned object data
            obj = json.loads(rv.data.decode('utf8'))
            assert obj['data']['src'] == moved_image
            assert obj['data']['folder']['id'] == orig_folder_id
            # Check physical file has been moved
            assert path_exists(renamed_image) == False
            assert path_exists(moved_image) == True
            # Check db record has been updated (folder changed), and move history added
            db_image = dm.get_image(temp_image_id, load_history=True)
            assert db_image.status == Image.STATUS_ACTIVE
            assert db_image.src == moved_image
            assert db_image.folder.id == orig_folder_id
            assert len(db_image.history) == 3
            assert db_image.history[2].action == ImageHistory.ACTION_MOVED
            # Check the cached ID has gone for the old path
            got_cached_id = True
            try: cached_id = dm.get_or_create_image_id(renamed_image, on_create=ensure_file_exists)
            except DoesNotExistError: got_cached_id = False
            assert got_cached_id == False
            # Check the cached image has gone for the old path
            rv = self.app.get('/image?src=' + renamed_image)
            assert rv.status_code == 404
            # Create another new cached image, also creates a cached src-ID entry
            rv = self.app.get('/image?src=' + moved_image)
            assert rv.status_code == 200
            # Delete the test file
            rv = self.app.delete('/api/admin/filesystem/images/%d/' % temp_image_id)
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            # Check returned object data
            obj = json.loads(rv.data.decode('utf8'))
            assert obj['data']['status'] == Image.STATUS_DELETED
            # Check physical file has been deleted
            assert path_exists(moved_image) == False
            # Check db record status, and delete history added
            db_image = dm.get_image(temp_image_id, load_history=True)
            assert db_image.status == Image.STATUS_DELETED
            assert len(db_image.history) == 4
            assert db_image.history[3].action == ImageHistory.ACTION_DELETED
            # Check the cached ID has gone
            cached_id = dm.get_or_create_image_id(moved_image, on_create=ensure_file_exists)
            assert cached_id == 0
            # Check that cached images are gone
            rv = self.app.get('/image?src=' + moved_image)
            assert rv.status_code == 404
        finally:
            delete_file(temp_image)
            delete_dir(temp_folder, recursive=True)
            if moved_image:
                delete_file(moved_image)

    # File admin API - folders
    def test_file_api_folders(self):
        temp_folder = '/test_folders_api'
        try:
            # Not logged in - folder ops should fail
            rv = self.app.post('/api/admin/filesystem/folders/', data={'path': temp_folder})
            assert rv.status_code == API_CODES.REQUIRES_AUTH, str(rv)
            rv = self.app.get('/api/admin/filesystem/folders/1/')
            assert rv.status_code == API_CODES.REQUIRES_AUTH, str(rv)
            rv = self.app.put('/api/admin/filesystem/folders/1/', data={'path': temp_folder})
            assert rv.status_code == API_CODES.REQUIRES_AUTH, str(rv)
            rv = self.app.delete('/api/admin/filesystem/folders/1/')
            assert rv.status_code == API_CODES.REQUIRES_AUTH, str(rv)
            # Log in as a standard user
            main_tests.setup_user_account('kryten', 'none')
            self.login('kryten', 'kryten')
            # v1.40 Viewable folder should be readable
            rv = self.app.get('/api/admin/filesystem/folders/?path=test_images')
            assert rv.status_code == API_CODES.SUCCESS, str(rv.data)
            # Other ops should still fail
            active_folder = dm.get_folder(folder_path='test_images')
            assert active_folder is not None
            rv = self.app.post('/api/admin/filesystem/folders/', data={'path': temp_folder})
            assert rv.status_code == API_CODES.UNAUTHORISED, str(rv)
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % active_folder.id, data={'path': temp_folder})
            assert rv.status_code == API_CODES.UNAUTHORISED, str(rv)
            rv = self.app.delete('/api/admin/filesystem/folders/%d/' % active_folder.id)
            assert rv.status_code == API_CODES.UNAUTHORISED, str(rv)
            #
            # Log in as a user with file admin
            #
            main_tests.setup_user_account('kryten', 'admin_files')
            self.login('kryten', 'kryten')
            # Create a new folder branch
            rv = self.app.post('/api/admin/filesystem/folders/', data={'path': temp_folder + '/a/b/'})
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            json_folder_b = json.loads(rv.data.decode('utf8'))['data']
            assert json_folder_b['id'] > 0
            assert json_folder_b['path'] == temp_folder + '/a/b'
            assert path_exists(temp_folder + '/a/b', require_directory=True)
            db_folder_a = dm.get_folder(folder_path=temp_folder + '/a/')
            assert db_folder_a is not None
            # v1.40 New GET methods should return 1 level of sub-tree
            rv = self.app.get('/api/admin/filesystem/folders/?path=' + temp_folder)
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            obj = json.loads(rv.data.decode('utf8'))
            assert 'parent' in obj['data']
            assert obj['data']['parent']['path'] == os.path.sep
            assert 'children' in obj['data']
            assert len(obj['data']['children']) == 1               # should have "a"
            assert 'children' not in obj['data']['children'][0]    # but not "b"
            assert 'parent' not in obj['data']['children'][0]      # and no link back/recursion
            # Things that shouldn't be allowed (TTSBA) - create a duplicate folder
            rv = self.app.post('/api/admin/filesystem/folders/', data={'path': '/test_images/'})
            assert rv.status_code == API_CODES.ALREADY_EXISTS, str(rv)
            # TTSBA - Move folder to an existing path
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % json_folder_b['id'],
                              data={'path': '/test_images/'})
            assert rv.status_code == API_CODES.ALREADY_EXISTS, str(rv)
            # TTSBA - Move folder to a relative path
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % json_folder_b['id'],
                              data={'path': temp_folder + '/a/../c'})
            assert rv.status_code == API_CODES.INVALID_PARAM, str(rv)
            # TTSBA - Move folder to a hidden folder
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % json_folder_b['id'],
                              data={'path': temp_folder + '/a/.b'})
            assert rv.status_code == API_CODES.INVALID_PARAM, str(rv)
            # TTSBA - Delete the root folder
            db_folder_root = dm.get_folder(folder_path='')
            assert db_folder_root is not None
            rv = self.app.delete('/api/admin/filesystem/folders/%d/' % db_folder_root.id)
            assert rv.status_code == API_CODES.INVALID_PARAM, str(rv)
            # TTSBA - Move/rename the root folder
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % db_folder_root.id, data={'path': 'some_other_name'})
            assert rv.status_code == API_CODES.INVALID_PARAM, str(rv)
            # Add images to a and b so we can test that path changes affect those too
            copy_file('test_images/cathedral.jpg', temp_folder + '/a/image_a.jpg')
            copy_file('test_images/dorset.jpg', temp_folder + '/a/b/image_b.jpg')
            db_image_a = auto_sync_file(temp_folder + '/a/image_a.jpg', dm, tm)
            db_image_b = auto_sync_file(temp_folder + '/a/b/image_b.jpg', dm, tm)
            assert db_image_a.folder.id == db_folder_a.id
            assert db_image_b.folder.id == json_folder_b['id']
            # Cache an image
            rv = self.app.get('/image?src=' + db_image_a.src)
            assert rv.status_code == 200
            image_a_src_old = db_image_a.src
            # Rename folder a
            renamed_folder = temp_folder + '/parrot'
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % db_folder_a.id, data={'path': renamed_folder})
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            obj = json.loads(rv.data.decode('utf8'))
            assert obj['data']['path'] == renamed_folder
            assert 'children' not in obj['data']  # v1.40 Do not return sub-trees any more
            assert 'parent' not in obj['data']    # v1.40 Do not return sub-trees any more
            assert path_exists(temp_folder + '/a/') == False
            assert path_exists(renamed_folder) == True
            db_folder_a = dm.get_folder(folder_id=db_folder_a.id)
            assert db_folder_a.path == renamed_folder
            # This should have moved image a
            db_image_a = dm.get_image(db_image_a.id, load_history=True)
            assert db_image_a.folder.id == db_folder_a.id
            assert db_image_a.src == strip_sep(renamed_folder + '/image_a.jpg', leading=True)
            assert db_image_a.history[-1].action == ImageHistory.ACTION_MOVED
            assert path_exists(db_image_a.src, require_file=True) == True
            rv = self.app.get('/image?src=' + image_a_src_old)
            assert rv.status_code == 404
            rv = self.app.get('/image?src=' + db_image_a.src)
            assert rv.status_code == 200
            # This should also have moved sub-folder b with it
            assert path_exists(renamed_folder + '/b/') == True
            db_folder_b = dm.get_folder(folder_id=json_folder_b['id'])
            assert db_folder_b.path == renamed_folder + '/b'
            # Which should have moved image b too
            db_image_b = dm.get_image(db_image_b.id, load_history=True)
            assert db_image_b.folder.id == db_folder_b.id
            assert db_image_b.src == strip_sep(renamed_folder + '/b/image_b.jpg', leading=True)
            assert db_image_b.history[-1].action == ImageHistory.ACTION_MOVED
            assert path_exists(db_image_b.src, require_file=True) == True
            # Delete parrot (was folder a)
            rv = self.app.delete('/api/admin/filesystem/folders/%d/' % db_folder_a.id)
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            obj = json.loads(rv.data.decode('utf8'))
            assert obj['data']['id'] == db_folder_a.id
            assert obj['data']['status'] == Folder.STATUS_DELETED
            assert 'children' not in obj['data']  # v1.40 Do not return sub-trees any more
            assert 'parent' not in obj['data']    # v1.40 Do not return sub-trees any more
            db_folder_a = dm.get_folder(folder_id=db_folder_a.id)
            assert db_folder_a.status == Folder.STATUS_DELETED
            assert path_exists(db_folder_a.path) == False
            # This should have deleted image a
            db_image_a = dm.get_image(db_image_a.id, load_history=True)
            assert db_image_a.status == Image.STATUS_DELETED
            assert db_image_a.history[-1].action == ImageHistory.ACTION_DELETED
            assert path_exists(db_image_a.src) == False
            rv = self.app.get('/image?src=' + db_image_a.src)
            assert rv.status_code == 404
            # This should have deleted sub-folder b with it
            db_folder_b = dm.get_folder(folder_id=db_folder_b.id)
            assert db_folder_b.status == Folder.STATUS_DELETED
            assert path_exists(db_folder_b.path) == False
            # Which should have deleted image b too
            db_image_b = dm.get_image(db_image_b.id, load_history=True)
            assert db_image_b.status == Image.STATUS_DELETED
            assert db_image_b.history[-1].action == ImageHistory.ACTION_DELETED
            assert path_exists(db_image_b.src) == False
            rv = self.app.get('/image?src=' + db_image_b.src)
            assert rv.status_code == 404
        finally:
            delete_dir(temp_folder, recursive=True)

    # #2517 File admin API - ignore // in folders
    def test_file_api_folders_double_sep(self):
        temp_folder = '/test_folders_api'
        main_tests.setup_user_account('kryten', 'admin_files')
        self.login('kryten', 'kryten')
        test_cases = ['/a//b', '/a///b']
        try:
            for fpath in test_cases:
                # Creating a//b or a///b should create a/b
                rv = self.app.post(
                    '/api/admin/filesystem/folders/',
                    data={'path': temp_folder + fpath}
                )
                self.assert_json_response_code(rv, API_CODES.SUCCESS)
                json_folder = json.loads(rv.data.decode('utf8'))['data']
                self.assertEqual(json_folder['path'], temp_folder + '/a/b')  # not /a//b
                db_folder = dm.get_folder(folder_path=temp_folder + '/a/b')  # not /a//b
                self.assertIsNotNone(db_folder)
                self.assertEqual(json_folder['id'], db_folder.id)
                dm.delete_folder(db_folder, purge=True)
                delete_dir(temp_folder + fpath)
        finally:
            delete_dir(temp_folder, recursive=True)

    # v4.1 #12 Folder list API - New status filter, only return active folders by default
    def test_file_api_folders_status_filter(self):
        self.login('admin', 'admin')
        tf1 = '/test_folder_1'
        tf2 = '/test_folder_2'
        try:
            # Create some test folders
            rv = self.app.post('/api/admin/filesystem/folders/', data={'path': tf1})
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            rv = self.app.post('/api/admin/filesystem/folders/', data={'path': tf2})
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            tf2jobj = json.loads(rv.data.decode('utf8'))['data']
            # Delete one of them
            rv = self.app.delete('/api/admin/filesystem/folders/' + str(tf2jobj['id']) + '/')
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            # List folders - default filter should be active only
            rv = self.app.get('/api/admin/filesystem/folders/?path=/')
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertGreater(len(obj['data']['children']), 0)
            self.assertTrue(all([
                (folder['status'] == Folder.STATUS_ACTIVE) for folder in obj['data']['children']
            ]))
            # List folders with filter 0
            rv = self.app.get('/api/admin/filesystem/folders/?path=/&status=0')
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertGreater(len(obj['data']['children']), 0)
            self.assertTrue(all([
                (folder['status'] == Folder.STATUS_DELETED) for folder in obj['data']['children']
            ]))
            # List folders with filter any
            rv = self.app.get('/api/admin/filesystem/folders/?path=/&status=any')
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))
            statuses = [folder['status'] for folder in obj['data']['children']]
            self.assertIn(Folder.STATUS_ACTIVE, statuses)
            self.assertIn(Folder.STATUS_DELETED, statuses)
        finally:
            delete_dir(tf1)
            delete_dir(tf2)

    # Task admin API
    def test_tasks_api(self):
        test_folder = 'test_tasks_api_folder'
        task_url = '/api/admin/tasks/'
        purge_url = task_url + 'purge_deleted_folder_data/'

        try:
            # Create test folder in the database
            db_folder = dm.get_or_create_folder(test_folder)
            # and delete (flag) it
            dm.delete_folder(db_folder, purge=False)
            # Folder should still exist but with deleted flag
            db_folder = dm.get_folder(folder_path=test_folder)
            self.assertIsNotNone(db_folder)
            self.assertEqual(db_folder.status, Folder.STATUS_DELETED)

            # Not logged in - cannot run tasks
            rv = self.app.post(purge_url, data={'path': ''})
            self.assertEqual(rv.status_code, API_CODES.REQUIRES_AUTH)

            # Logged in as admin (non superuser) user - cannot run tasks with API
            main_tests.setup_user_account('kryten', 'admin_files')
            self.login('kryten', 'kryten')
            rv = self.app.post(purge_url, data={'path': ''})
            self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)

            # Have the system start a task owned by the user though
            user_task = tm.add_task(
                dm.get_user(username='kryten'),
                'Testing user task access',
                'uncache_image',
                {'image_id': 1},
                Task.PRIORITY_NORMAL,
                'debug', 'error', 1
            )
            # A user can query their own task
            rv = self.app.get(task_url + str(user_task.id) + '/')
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            # Another (non super) user cannot query it
            main_tests.setup_user_account('taskuser', 'admin_files')
            self.login('taskuser', 'taskuser')
            rv = self.app.get(task_url + str(user_task.id) + '/')
            self.assert_json_response_code(rv, API_CODES.UNAUTHORISED)
            # Prevent this task running during some later test
            tm.cancel_task(user_task)

            # Logged in as superuser - task should launch with API
            main_tests.setup_user_account('kryten', 'admin_all')
            self.login('kryten', 'kryten')
            rv = self.app.post(purge_url, data={'path': ''})
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            task_obj = json.loads(rv.data.decode('utf8'))['data']
            # Do not return the task user password
            self.assertIsNotNone(task_obj['user'])
            self.assertNotIn('password', task_obj['user'])

            # Test duplicate task isn't allowed
            rv = self.app.post(purge_url, data={'path': ''})
            self.assert_json_response_code(rv, API_CODES.ALREADY_EXISTS)

            # Test checking task progress
            rv = self.app.get(task_url + str(task_obj['id']) + '/')
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            task_obj_2 = json.loads(rv.data.decode('utf8'))['data']
            self.assertEqual(task_obj_2['id'], task_obj['id'])
            self.assertEqual(task_obj_2['funcname'], 'purge_deleted_folder_data')
            # Do not return the task user password
            self.assertIsNotNone(task_obj_2['user'])
            self.assertNotIn('password', task_obj_2['user'])

        finally:
            # After error, delete (proper) the test folder
            db_folder = dm.get_folder(folder_path=test_folder)
            if db_folder:
                dm.delete_folder(db_folder, purge=True)

    # Task properties API
    def test_properties_api(self):
        # Super user access is required
        main_tests.setup_user_account('kryten', 'admin_permissions')
        self.login('kryten', 'kryten')
        rv = self.app.get('/api/admin/properties/' + Property.DEFAULT_TEMPLATE + '/')
        self.assert_json_response_code(rv, API_CODES.UNAUTHORISED)
        self.login('admin', 'admin')
        rv = self.app.get('/api/admin/properties/' + Property.DEFAULT_TEMPLATE + '/')
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        prop_obj = json.loads(rv.data.decode('utf8'))['data']
        self.assertEqual(prop_obj, {
            'key': Property.DEFAULT_TEMPLATE,
            'value': 'default'
        })
        # Try an update too
        rv = self.app.put('/api/admin/properties/' + Property.DEFAULT_TEMPLATE + '/', data=prop_obj)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)

    # Test image API access (folder permissions)
    def test_folder_permissions(self):
        temp_image   = 'test_images/fptest_image.jpg'
        temp_image2  = 'test_images/fptest_image_2.jpg'
        temp_image3  = '/fptest_image_2.jpg'
        temp_folder  = 'test_images/fp-test_folder'
        temp_folder2 = 'test_images/fp-test_folder_2'
        temp_folder3 = '/fp-test_folder_2'

        # Helper to change user permissions
        def setup_fp_user(root_access, test_folder_access=None):
            db_group = dm.get_group(groupname='kryten-group')
            db_folder = dm.get_folder(folder_path='')
            # Set root folder access
            rf_fp = dm.get_folder_permission(db_folder, db_group)
            if not rf_fp: rf_fp = FolderPermission(db_folder, db_group, 0)
            rf_fp.access = root_access
            dm.save_object(rf_fp)
            # Set or clear test_images folder access
            if test_folder_access is not None:
                db_folder = dm.get_folder(folder_path='test_images')
                tf_fp = dm.get_folder_permission(db_folder, db_group)
                if not tf_fp: tf_fp = FolderPermission(db_folder, db_group, 0)
                tf_fp.access = test_folder_access
                dm.save_object(tf_fp)
            else:
                db_folder = dm.get_folder(folder_path='test_images')
                tf_fp = dm.get_folder_permission(db_folder, db_group)
                if tf_fp is not None: dm.delete_object(tf_fp)
            pm.reset_folder_permissions()
            # v1.23 Also clear cached permissions for the task server process
            cm.clear()

        try:
            # Create a temp file we can rename, move, delete
            copy_file('test_images/cathedral.jpg', temp_image)
            db_image = auto_sync_existing_file(temp_image, dm, tm)
            # Reset user permissions to None
            main_tests.set_default_public_permission(FolderPermission.ACCESS_NONE)
            main_tests.set_default_internal_permission(FolderPermission.ACCESS_NONE)
            main_tests.setup_user_account('kryten', 'none')
            self.login('kryten', 'kryten')
            setup_fp_user(FolderPermission.ACCESS_NONE)
            # Folder list API requires view permission
            rv = self.app.get('/api/list/?path=test_images')
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_VIEW)
            rv = self.app.get('/api/list/?path=test_images')
            assert rv.status_code == API_CODES.SUCCESS
            # Image details API requires view permission
            setup_fp_user(FolderPermission.ACCESS_NONE)
            rv = self.app.get('/api/details/?src=' + db_image.src)
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_VIEW)
            rv = self.app.get('/api/details/?src=' + db_image.src)
            assert rv.status_code == API_CODES.SUCCESS
            # Image data API - read - requires view permission
            setup_fp_user(FolderPermission.ACCESS_NONE)
            rv = self.app.get('/api/admin/images/%d/' % db_image.id)
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_VIEW)
            rv = self.app.get('/api/admin/images/%d/' % db_image.id)
            assert rv.status_code == API_CODES.SUCCESS
            # Image data API - write - requires edit permission
            rv = self.app.put('/api/admin/images/%d/' % db_image.id,
                              data={'title': '', 'description': ''})
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_EDIT)
            rv = self.app.put('/api/admin/images/%d/' % db_image.id,
                              data={'title': '', 'description': ''})
            assert rv.status_code == API_CODES.SUCCESS
            # Image file API - rename - requires upload permission
            rv = self.app.put('/api/admin/filesystem/images/%d/' % db_image.id,
                              data={'path': temp_image2})
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_UPLOAD)
            rv = self.app.put('/api/admin/filesystem/images/%d/' % db_image.id,
                              data={'path': temp_image2})
            assert rv.status_code == API_CODES.SUCCESS
            # Image file API - move - requires delete (source) and upload (dest) permissions
            rv = self.app.put('/api/admin/filesystem/images/%d/' % db_image.id,
                              data={'path': temp_image3})
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_UPLOAD, FolderPermission.ACCESS_DELETE)
            rv = self.app.put('/api/admin/filesystem/images/%d/' % db_image.id,
                              data={'path': temp_image3})
            assert rv.status_code == API_CODES.SUCCESS
            # Image file API - delete - requires delete permission
            rv = self.app.delete('/api/admin/filesystem/images/%d/' % db_image.id)
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_DELETE)
            rv = self.app.delete('/api/admin/filesystem/images/%d/' % db_image.id)
            assert rv.status_code == API_CODES.SUCCESS
            # Image file API - create folder - requires create folder permission
            setup_fp_user(FolderPermission.ACCESS_NONE, FolderPermission.ACCESS_DELETE)
            rv = self.app.post('/api/admin/filesystem/folders/',
                               data={'path': temp_folder})
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_NONE, FolderPermission.ACCESS_CREATE_FOLDER)
            rv = self.app.post('/api/admin/filesystem/folders/',
                               data={'path': temp_folder})
            assert rv.status_code == API_CODES.SUCCESS
            folder_json = json.loads(rv.data.decode('utf8'))
            folder_id = folder_json['data']['id']
            # Image file API - rename folder - requires create folder permission
            setup_fp_user(FolderPermission.ACCESS_NONE, FolderPermission.ACCESS_DELETE)
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % folder_id,
                              data={'path': temp_folder2})
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_NONE, FolderPermission.ACCESS_CREATE_FOLDER)
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % folder_id,
                              data={'path': temp_folder2})
            assert rv.status_code == API_CODES.SUCCESS, 'Got '+str(rv.status_code)
            # Image file API - move folder - requires delete folder (source) and create folder (dest) permissions
            setup_fp_user(FolderPermission.ACCESS_CREATE_FOLDER, FolderPermission.ACCESS_CREATE_FOLDER)
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % folder_id,
                              data={'path': temp_folder3})
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_CREATE_FOLDER, FolderPermission.ACCESS_DELETE_FOLDER)
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % folder_id,
                              data={'path': temp_folder3})
            assert rv.status_code == API_CODES.SUCCESS, 'Got '+str(rv.status_code)
            # Image file API - delete folder - requires delete folder permission
            rv = self.app.delete('/api/admin/filesystem/folders/%d/' % folder_id)
            assert rv.status_code == API_CODES.UNAUTHORISED
            setup_fp_user(FolderPermission.ACCESS_DELETE_FOLDER)
            rv = self.app.delete('/api/admin/filesystem/folders/%d/' % folder_id)
            assert rv.status_code == API_CODES.SUCCESS, 'Got '+str(rv.status_code)
        finally:
            delete_file(temp_image)
            delete_file(temp_image2)
            delete_file(temp_image3)
            delete_dir(temp_folder)
            delete_dir(temp_folder2)
            delete_dir(temp_folder3)
            main_tests.set_default_public_permission(FolderPermission.ACCESS_DOWNLOAD)
            main_tests.set_default_internal_permission(FolderPermission.ACCESS_DOWNLOAD)

    # CSRF protection should be active for web sessions but not for API tokens
    def test_csrf(self):
        main_tests.setup_user_account('deleteme', 'none')
        deluser = dm.get_user(username='deleteme')
        self.assertIsNotNone(deluser)
        try:
            main_tests.setup_user_account('kryten', 'admin_users', allow_api=True)
            self.login('kryten', 'kryten')
            # Enable CSRF
            flask_app.config['TESTING'] = False
            # Web operations should be blocked without a CSRF token
            rv = self.app.delete('/api/admin/users/' + str(deluser.id) + '/')
            self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
            self.assertIn('missing CSRF token', rv.data.decode('utf8'))  # HTML
            # But allowed if caller has an API token
            token = self.api_login('kryten', 'kryten')
            creds = self._base64_encode(token + ':password')
            rv = self.app.delete('/api/admin/users/' + str(deluser.id) + '/', headers={
                'Authorization': 'Basic ' + creds
            })
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
        finally:
            flask_app.config['TESTING'] = True

    # Test unicode characters in filenames, especially dashes!
    def test_unicode_filenames(self):
        temp_dir = '\u00e2 te\u00dft \u2014 of \u00e7har\u0292'
        temp_filename = temp_dir + '.jpg'
        temp_file = os.path.join(temp_dir, temp_filename)
        temp_file2 = os.path.join(temp_dir, 're\u00f1\u00e3med.jpg')
        temp_new_dir = os.path.join(temp_dir, 'New F\u00f6lder')
        try:
            with flask_app.test_request_context():
                list_url = internal_url_for('api.imagelist', path=temp_dir, attributes=1)
                details_url = internal_url_for('api.imagedetails', src=temp_file)

            # Create test folder and file
            make_dirs(temp_dir)
            copy_file('test_images/thames.jpg', temp_file)
            # Test directory listing
            rv = self.app.get(list_url)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            obj = json.loads(rv.data.decode('utf8'))
            assert len(obj['data']) == 1
            entry = obj['data'][0]
            assert url_quote_plus(temp_dir, safe='/') in entry['url'], 'Returned URL is \'' + entry['url'] + '\''
            assert unicode_to_utf8(entry['filename']) == unicode_to_utf8(temp_filename)
            # Test viewing details
            rv = self.app.get(details_url)
            assert rv.status_code == API_CODES.SUCCESS
            obj = json.loads(rv.data.decode('utf8'))
            assert unicode_to_utf8(obj['data']['src']) == unicode_to_utf8(temp_file), \
                   'Returned src is \'' + obj['data']['src'] + '\''
            # Test data API - images
            main_tests.setup_user_account('kryten', 'admin_files')
            self.login('kryten', 'kryten')
            db_img = dm.get_image(src=temp_file)
            assert db_img is not None
            rv = self.app.get('/api/admin/images/%d/' % db_img.id)
            assert rv.status_code == API_CODES.SUCCESS, rv.data
            obj = json.loads(rv.data.decode('utf8'))
            assert unicode_to_utf8(obj['data']['src']) == unicode_to_utf8(temp_file), \
                   'Returned src is \'' + obj['data']['src'] + '\''
            # Test file API - rename the image
            rv = self.app.put('/api/admin/filesystem/images/%d/' % db_img.id, data={'path': temp_file2})
            assert rv.status_code == API_CODES.SUCCESS, rv.data
            assert path_exists(temp_file2, require_file=True)
            # Test file API - create a unicode sub-folder
            rv = self.app.post('/api/admin/filesystem/folders/', data={'path': temp_new_dir})
            assert rv.status_code == API_CODES.SUCCESS, str(rv)
            assert path_exists(temp_new_dir, require_directory=True)
        finally:
            delete_dir(temp_dir, recursive=True)

    # Test that bad filenames are filtered by the APIs
    def test_bad_filenames(self):
        try:
            main_tests.setup_user_account('kryten', 'admin_files')
            self.login('kryten', 'kryten')
            # Create a folder
            rv = self.app.post('/api/admin/filesystem/folders/', data={
                'path': '/bell\x07/etc/* | more/'
            })
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            json_folder = json.loads(rv.data.decode('utf8'))['data']
            self.assertGreater(json_folder['id'], 0)
            # The bell byte, *, | and surrounding spaces should be gone
            self.assertEqual(json_folder['path'], '/bell/etc/more')
            self.assertTrue(path_exists('/bell/etc/more', require_directory=True))
            # Rename it
            rv = self.app.put('/api/admin/filesystem/folders/%d/' % json_folder['id'], data={
                'path': '/bell/etc/m\xf6re\x07bells'
            })
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            json_folder = json.loads(rv.data.decode('utf8'))['data']
            # The bell byte should be gone, the umlaut o remaining
            self.assertEqual(json_folder['path'], '/bell/etc/m\xf6rebells')
            # Put a file in there
            copy_file('test_images/cathedral.jpg', '/bell/etc/m\xf6rebells/cathedral.jpg')
            db_img = auto_sync_file('/bell/etc/m\xf6rebells/cathedral.jpg', dm, tm)
            self.assertIsNotNone(db_img)
            # Rename the file
            rv = self.app.put('/api/admin/filesystem/images/%d/' % db_img.id, data={
                'path': '/bell/etc/m\xf6rebells/cath\xebdral*\x09echo>\'hi\'.jpg'
            })
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            json_file = json.loads(rv.data.decode('utf8'))['data']
            # The tab, *, > and ' should be gone, the umlaut e remaining
            self.assertEqual(json_file['src'], 'bell/etc/m\xf6rebells/cath\xebdralechohi.jpg')
        finally:
            delete_dir('/bell', recursive=True)

    # Flask by default encodes JSON dates in the awful RFC1123 format, so we override that
    def test_json_date_encoding(self):
        # Create a dummy task with a date on it
        dt_time = datetime.datetime(2100, 1, 1, 12, 13, 15)
        task = Task(
            None, 'Unit test dummy task', 'noop',
            pickle.dumps({}, protocol=pickle.HIGHEST_PROTOCOL),
            Task.PRIORITY_NORMAL, 'debug', 'error', 0
        )
        task.status = Task.STATUS_COMPLETE
        task.keep_until = dt_time
        db_task = dm.save_object(task, refresh=True)
        try:
            # Get the task with the API
            self.login('admin', 'admin')
            rv = self.app.get('/api/admin/tasks/' + str(db_task.id) + '/')
            self.assertEqual(rv.status_code, 200)
            api_obj = json.loads(rv.data.decode('utf8'))['data']
            # Date format should be ISO8601
            self.assertEqual(api_obj['keep_until'], '2100-01-01T12:13:15Z')
        finally:
            dm.delete_object(db_task)

    # v1.23 Tasks can now store a result - None, object, or Exception
    def test_json_exception_encoding(self):
        # Create a dummy task with an exception result
        task = Task(
            None, 'Unit test dummy task', 'noop',
            pickle.dumps({}, protocol=pickle.HIGHEST_PROTOCOL),
            Task.PRIORITY_NORMAL, 'debug', 'error', 0
        )
        task.status = Task.STATUS_COMPLETE
        task.result = pickle.dumps(ValueError('Warp failure'), protocol=pickle.HIGHEST_PROTOCOL)
        db_task = dm.save_object(task, refresh=True)
        try:
            # Get the task with the API
            self.login('admin', 'admin')
            rv = self.app.get('/api/admin/tasks/' + str(db_task.id) + '/')
            self.assertEqual(rv.status_code, 200)
            res = json.loads(rv.data.decode('utf8'))['data']['result']
            self.assertIn('exception', res)
            self.assertEqual(res['exception']['type'], 'ValueError')
            self.assertEqual(res['exception']['message'], 'Warp failure')
        finally:
            dm.delete_object(db_task)

    # v2.6.1 Some of the APIs were inconsistent in not having a trailing slash.
    #        Added support to make this consistent but kept compatibility.
    def test_trailing_slashes(self):
        test_get_urls = [
            ("/api/list", "?path=test_images"),
            ("/api/details", "?src=test_images/cathedral.jpg"),
        ]
        test_post_urls = [
            "/api/token",
            "/api/upload",
        ]
        for url_parts in test_get_urls:
            # Test without the slash (legacy)
            url = url_parts[0] + url_parts[1]
            rv = self.app.get(url)
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            # Test with the slash (intended use from now on)
            url = url_parts[0] + "/" + url_parts[1]
            rv = self.app.get(url)
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        self.login('admin', 'admin')
        for url in test_post_urls:
            # To keep it simple, just check that the return is neither a 301 or a 404
            rv = self.app.post(url)
            self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
            rv = self.app.post(url + "/")
            self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)

    # v4.1 #10 Deleting a group twice should give 200 then 404
    def test_group_double_delete(self):
        self.login('admin', 'admin')
        group_data = {
            'name': 'Group DD test',
            'description': 'This is a test group',
            'group_type': Group.GROUP_TYPE_LOCAL
        }
        rv = self.app.post('/api/admin/groups/', data=group_data)
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        group_id = obj['data']['id']
        api_url = '/api/admin/groups/' + str(group_id) + '/'
        rv = self.app.delete(api_url)
        self.assert_json_response_code(rv, API_CODES.SUCCESS)
        rv = self.app.delete(api_url)
        self.assert_json_response_code(rv, API_CODES.NOT_FOUND)

    # v4.1 #10 Deleting a disk file twice should give 200 then 404
    #         (the db record exists status:0 but the lack of disk file should take precedence)
    def test_file_double_delete(self):
        temp_file = 'test_file_dd.jpg'
        try:
            copy_file('test_images/cathedral.jpg', temp_file)
            db_image = auto_sync_file(temp_file, dm, tm)
            self.assertIsNotNone(db_image)
            api_url = '/api/admin/filesystem/images/' + str(db_image.id) + '/'
            self.login('admin', 'admin')
            rv = self.app.delete(api_url)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            rv = self.app.delete(api_url)
            self.assert_json_response_code(rv, API_CODES.NOT_FOUND)
        finally:
            delete_file(temp_file)

    # v4.1 #10 Deleting a disk folder twice should give 200 then 404
    #         (the db record exists status:0 but the lack of disk folder should take precedence)
    def test_folder_double_delete(self):
        temp_folder = 'test_folder_dd'
        make_dirs(temp_folder)
        try:
            db_folder = auto_sync_folder(temp_folder, dm, tm)
            self.assertIsNotNone(db_folder)
            api_url = '/api/admin/filesystem/folders/' + str(db_folder.id) + '/'
            self.login('admin', 'admin')
            rv = self.app.delete(api_url)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            rv = self.app.delete(api_url)
            self.assert_json_response_code(rv, API_CODES.NOT_FOUND)
        finally:
            delete_dir(temp_folder)

    # v4.1 #10 Moving a deleted file should give a 404
    #         (the db record exists status:0 but there is no disk file to move)
    def test_move_deleted_file(self):
        temp_file = 'test_file_mdf.jpg'
        renamed_temp_file = 'renamed_file_mdf.jpg'
        try:
            copy_file('test_images/cathedral.jpg', temp_file)
            db_image = auto_sync_file(temp_file, dm, tm)
            self.assertIsNotNone(db_image)
            api_url = '/api/admin/filesystem/images/' + str(db_image.id) + '/'
            self.login('admin', 'admin')
            rv = self.app.delete(api_url)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            rv = self.app.put(api_url, data={'path': renamed_temp_file})
            self.assert_json_response_code(rv, API_CODES.NOT_FOUND)
        finally:
            delete_file(temp_file)
            delete_file(renamed_temp_file)

    # v4.1 #10 Moving a deleted folder should give a 404
    #         (the db record exists status:0 but there is no disk folder to move)
    def test_move_deleted_folder(self):
        temp_folder = 'test_folder_mdf'
        renamed_temp_folder = 'renamed_folder_mdf'
        make_dirs(temp_folder)
        try:
            db_folder = auto_sync_folder(temp_folder, dm, tm)
            self.assertIsNotNone(db_folder)
            api_url = '/api/admin/filesystem/folders/' + str(db_folder.id) + '/'
            self.login('admin', 'admin')
            rv = self.app.delete(api_url)
            self.assert_json_response_code(rv, API_CODES.SUCCESS)
            rv = self.app.put(api_url, data={'path': renamed_temp_folder})
            self.assert_json_response_code(rv, API_CODES.NOT_FOUND)
        finally:
            delete_dir(temp_folder)
            delete_dir(renamed_temp_folder)

    # v4.1 #10 Flask 401 errors should return JSON not HTML
    def test_api_no_token(self):
        rv = self.app.get('/api/admin/users/')
        self.assert_json_response_code(rv, API_CODES.REQUIRES_AUTH)

    # v4.1 #10 Flask 400 errors should return JSON not HTML
    def test_api_bad_request(self):
        self.login('admin', 'admin')
        rv = self.app.post(
            '/api/admin/users/',
            data={'foo': 'bar'},
            headers={'Content-Type': 'invalid'}
        )
        self.assert_json_response_code(rv, API_CODES.INVALID_PARAM)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertIn('this server could not understand', obj['message'])

    # v4.1 #10 Flask 404 errors should return JSON not HTML
    def test_api_not_found(self):
        rv = self.app.get('/api/non-existent')
        self.assert_json_response_code(rv, API_CODES.NOT_FOUND)

    # v4.1 #10 Flask 405 errors should return JSON not HTML
    def test_method_not_allowed(self):
        rv = self.app.delete('/api/upload')
        self.assert_json_response_code(rv, 405)

    # v4.1 #10 Flask 413 errors should return JSON not HTML
    def test_data_too_large(self):
        old_MAX_CONTENT_LENGTH = flask_app.config['MAX_CONTENT_LENGTH']
        try:
            flask_app.config['MAX_CONTENT_LENGTH'] = 100
            rv = self.app.post('/api/upload/', data={
                'files': io.BytesIO(b'test' * 200),
                'path': 'test_images'
            })
            self.assert_json_response_code(rv, 413)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertIn('exceeds the capacity limit', obj['message'])
        finally:
            flask_app.config['MAX_CONTENT_LENGTH'] = old_MAX_CONTENT_LENGTH

    # v4.1 #10 Missing slashes redirect should return JSON not an HTML 301
    def test_missing_slash(self):
        self.login('admin', 'admin')
        rv = self.app.get('/api/admin/users')  # Should have a trailing /
        self.assert_json_response_code(rv, 301)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertTrue(obj['data'].endswith('/users/'))

    # v4.1 #11 Make an attempt to filter out secrets from error messages
    def test_error_message_redaction(self):
        import imageserver.views_util
        imageserver.views_util._safe_error_str_replacements = None
        # The IMAGES_BASE_DIR setting is just one thing that could be sensitive
        flask_app.config['IMAGES_BASE_DIR'] = '/some/sensitive/path'
        dummy_error = 'Permission denied for ' + flask_app.config['IMAGES_BASE_DIR']
        with unittest.mock.patch('imageserver.api.views_api.auto_sync_file') as mockfileio:
            mockfileio.side_effect = OSError(dummy_error)
            rv = self.app.get('/api/details/?src=test_images/cathedral.jpg')
            self.assert_json_response_code(rv, API_CODES.INTERNAL_ERROR)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertIn('Permission denied for', obj['message'])
            # The setting value should have been replaced with the setting name
            self.assertNotIn(flask_app.config['IMAGES_BASE_DIR'], obj['message'])
            self.assertIn('IMAGES_BASE_DIR', obj['message'])


class WebPageTests(main_tests.BaseTestCase):
    def test_token_to_web(self):
        # Get an API token
        main_tests.setup_user_account('tokenuser', allow_api=True)
        token = self.api_login('tokenuser', 'tokenuser')
        # Should still have an anonymous web session
        rv = self.app.get('/upload/')
        self.assertEqual(rv.status_code, 302)  # Redirect to login
        # Load the token-to-web-login page
        rv = self.app.get('/api/tokenlogin/?token=' + token)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Should now have a logged-in web session
        rv = self.app.get('/upload/')
        self.assertEqual(rv.status_code, 200)

    def test_token_to_web_no_token(self):
        rv = self.app.get('/api/tokenlogin/')
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        self.assertIn('No token value supplied', rv.data.decode('utf8'))
        # Should still be logged out
        rv = self.app.get('/upload/')
        self.assertEqual(rv.status_code, 302)

    def test_token_to_web_invalid_token(self):
        rv = self.app.get('/api/tokenlogin/?token=not-a-valid-token')
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)  # Match /api/token/ with bad credentials
        self.assertIn('Invalid or expired token', rv.data.decode('utf8'))
        # Should still be logged out
        rv = self.app.get('/upload/')
        self.assertEqual(rv.status_code, 302)

    def test_token_to_web_post(self):
        rv = self.app.post('/api/tokenlogin/')
        self.assertEqual(rv.status_code, API_CODES.METHOD_UNSUPPORTED)

    def test_token_to_web_deleted_user(self):
        for i in range(2):
            cm.clear()
            user = main_tests.setup_user_account('tokenuser', allow_api=True)
            token = self.api_login('tokenuser', 'tokenuser')
            if i == 0:
                # Soft delete
                user.status = User.STATUS_DELETED
                dm.save_object(user)
                rv = self.app.get('/api/tokenlogin/?token=' + token)
                self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
                self.assertIn('tokenuser is disabled/deleted', rv.data.decode('utf8'))
            else:
                # Hard delete - also tests a valid token containing a bad user ID
                dm.delete_object(user)
                rv = self.app.get('/api/tokenlogin/?token=' + token)
                self.assertEqual(rv.status_code, API_CODES.INTERNAL_ERROR)
            # Should still be logged out
            rv = self.app.get('/upload/')
            self.assertEqual(rv.status_code, 302)

    def test_token_to_web_redirect(self):
        # Get an API token
        main_tests.setup_user_account('tokenuser', allow_api=True)
        token = self.api_login('tokenuser', 'tokenuser')
        # Test we get a redirect if we pass the 'next' parameter
        rv = self.app.get('/api/tokenlogin/?token=' + token + '&next=https://www.quru.com/')
        self.assertEqual(rv.status_code, 302)
        self.assertIn('https://www.quru.com/', rv.location)

    def test_token_to_web_redirect_invalid_token(self):
        # For bad tokens we'll return an error rather than continue with the redirect
        rv = self.app.get('/api/tokenlogin/?token=not-a-valid-token&next=https://www.quru.com/')
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)  # Match /api/token/ with bad credentials
        self.assertIn('Invalid or expired token', rv.data.decode('utf8'))
