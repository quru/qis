#
# Quru Image Server
#
# Document:      test_portfolios.py
# Date started:  02 Mar 2018
# By:            Matt Fozard
# Purpose:       Contains the image server test suite for the portfolios feature
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
#

import os
import json
import time
import urllib.parse
import zipfile
from datetime import datetime, timedelta

from . import tests as main_tests
from . import test_imaging as imaging_tests

from imageserver.flask_app import app as flask_app
from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import task_engine as tm
from imageserver.flask_app import permissions_engine as pm

from imageserver.api_util import API_CODES
from imageserver.filesystem_manager import (
    copy_file, delete_dir, make_dirs, path_exists,
    get_abs_path, get_file_info, get_portfolio_export_file_path
)
from imageserver.filesystem_sync import (
    auto_sync_existing_file, auto_sync_folder
)
from imageserver.models import (
    FolderPermission, Group, Task,
    Folio, FolioImage, FolioPermission, FolioHistory, FolioExport
)
from imageserver.util import AttrObject, to_iso_datetime


# Module level setUp and tearDown
def setUpModule():
    main_tests.init_tests()
def tearDownModule():
    main_tests.cleanup_tests()


class PortfoliosAPITests(main_tests.BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super(PortfoliosAPITests, cls).setUpClass()
        assert 'test' in flask_app.config['FOLIO_EXPORTS_DIR'], \
            'Testing settings have not been applied, main_tests should do this!'
        # Preload all the API code as some of these tests need consistent run times
        flask_app.test_client().get('/api/portfolios/')

    def setUp(self):
        super(PortfoliosAPITests, self).setUp()
        # Restore clean test data before each test
        self.reset_fixtures()

    def tearDown(self):
        super(PortfoliosAPITests, self).tearDown()
        # Clean up any exported files after each test
        export_dir = flask_app.config['FOLIO_EXPORTS_DIR']
        if 'test' in export_dir:
            delete_dir(export_dir, recursive=True)

    def reset_fixtures(self):
        # Wipe the old data
        db_session = dm.db_get_session()
        db_session.query(FolioImage).delete()
        db_session.query(FolioPermission).delete()
        db_session.query(FolioHistory).delete()
        db_session.query(FolioExport).delete()
        db_session.query(Folio).delete()
        db_session.query(Task).delete()
        db_session.commit()
        # Create private, internal and public test portfolios
        db_user = main_tests.setup_user_account('foliouser', user_type='folios')
        self.create_portfolio('private', db_user,
                              FolioPermission.ACCESS_NONE, FolioPermission.ACCESS_NONE)
        self.create_portfolio('internal', db_user,
                              FolioPermission.ACCESS_DOWNLOAD, FolioPermission.ACCESS_NONE)
        self.create_portfolio('public', db_user,
                              FolioPermission.ACCESS_DOWNLOAD, FolioPermission.ACCESS_DOWNLOAD)

    # Creates a demo portfolio with 2 images and a basic audit trail
    def create_portfolio(self, human_id, owner, internal_access, public_access):
        db_img_1 = auto_sync_existing_file('test_images/blue bells.jpg', dm, tm)
        db_img_2 = auto_sync_existing_file('test_images/cathedral.jpg', dm, tm)
        db_pub_group = dm.get_group(Group.ID_PUBLIC)
        db_normal_group = dm.get_group(Group.ID_EVERYONE)
        folio = Folio(human_id, 'Test %s Portfolio' % human_id.capitalize(), 'Description', owner)
        db_folio = dm.save_object(folio)
        dm.save_object(FolioHistory(db_folio, owner, FolioHistory.ACTION_CREATED, 'Created'))
        dm.save_object(FolioImage(db_folio, db_img_1))
        dm.save_object(FolioImage(db_folio, db_img_2))
        dm.save_object(FolioHistory(db_folio, owner, FolioHistory.ACTION_IMAGE_CHANGE, 'Added image 1'))
        dm.save_object(FolioHistory(db_folio, owner, FolioHistory.ACTION_IMAGE_CHANGE, 'Added image 2'))
        dm.save_object(FolioPermission(db_folio, db_pub_group, public_access))
        dm.save_object(FolioPermission(db_folio, db_normal_group, internal_access))

    # Publishes a portfolio and waits for the task to finish, returning the associated
    # FolioExport object. Performs a logout before returning.
    def publish_portfolio(self, folio, description, originals=True, image_params_dict=None, expiry_time=None):
        if not image_params_dict:
            image_params_dict = {}
        if not expiry_time:
            expiry_time = datetime.utcnow() + timedelta(days=365)
        api_url = '/api/portfolios/' + str(folio.id) + '/exports/'
        main_tests.setup_user_account('folioadmin', user_type='admin_folios')
        self.login('folioadmin', 'folioadmin')
        rv = self.app.post(api_url, data={
            'description': description,
            'originals': originals,
            'image_parameters': json.dumps(image_params_dict),
            'expiry_time': to_iso_datetime(expiry_time)
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS_TASK_ACCEPTED, str(rv.data))
        obj = json.loads(rv.data.decode('utf8'))
        task = tm.wait_for_task(obj['data']['task_id'], 20)
        self.assertIsNotNone(task, 'Portfolio export task was cleaned up')
        self.assertIsNotNone(task.result, 'Portfolio export task did not return a result')
        self.assertIsInstance(
            task.result, FolioExport,
            'Portfolio export task raised an exception: ' + str(task.result)
        )
        self.logout()
        return task.result

    # Tests portfolio creation and permissions
    def test_folio_create(self):
        api_url = '/api/portfolios/'
        # Must be logged in to create
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # Must have folio permission to create
        main_tests.setup_user_account('testuser')
        self.login('testuser', 'testuser')
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # So this should work
        db_owner = dm.get_user(username='foliouser')
        self.login('foliouser', 'foliouser')
        rv = self.app.post(api_url, data={
            'human_id': 'mypf1',
            'name': 'Portfolio 1',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(obj['data']['id'], 0)
        self.assertEqual(obj['data']['human_id'], 'mypf1')
        self.assertEqual(obj['data']['description'], 'This is a test portfolio')
        self.assertEqual(obj['data']['owner_id'], db_owner.id)
        # Audit trail should have a "created" entry
        db_folio = dm.get_portfolio(obj['data']['id'], load_history=True)
        self.assertIsNotNone(db_folio)
        self.assertEqual(len(db_folio.history), 1)
        self.assertEqual(db_folio.history[0].action, FolioHistory.ACTION_CREATED)

    # Test the human ID value when creating portfolios
    def test_folio_human_id(self):
        api_url = '/api/portfolios/'
        self.login('foliouser', 'foliouser')
        # Creation - blank human ID should have one allocated
        rv = self.app.post(api_url, data={
            'human_id': '',
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(len(obj['data']['human_id']), 0)
        # Creation - duplicate human ID should not be allowed
        rv = self.app.post(api_url, data={
            'human_id': 'private',          # see reset_fixtures()
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
        # Updates - blank human ID should have one allocated
        db_folio = dm.get_portfolio(human_id='public')
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        rv = self.app.put(api_url, data={
            'human_id': '',
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(len(obj['data']['human_id']), 0)
        self.assertNotEqual(obj['data']['human_id'], 'public')
        # Updates - duplicate human ID should not be allowed
        rv = self.app.put(api_url, data={
            'human_id': 'private',          # see reset_fixtures()
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
        # A human ID of all whitespace should be treated the same as a blank
        api_url = '/api/portfolios/'
        rv = self.app.post(api_url, data={
            'human_id': '  ',
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(len(obj['data']['human_id']), 0)
        self.assertNotEqual(obj['data']['human_id'].strip(), '')

    # v4.1 The human/friendly ID comes from the UI.
    # Check that it can't be used to create malicious URLs.
    def test_folio_bad_human_id(self):
        api_url = '/api/portfolios/'
        self.login('foliouser', 'foliouser')
        bad_ids = [
            '/some/path/name',
            '.',
            '..name',
            '../../../',
            '../../../name',
            'some:port',
            'name?some=query-string',
            '?some=query-string',
            '<script>',
            '%3cscript%3e',
            '%3Cscript%20',
            '%253Cscript',
            '&lt;script&gt;',
            'javascript:',
        ]
        for bad_id in bad_ids:
            rv = self.app.post(api_url, data={
                'human_id': bad_id,
                'name': 'Test portfolio',
                'description': 'This is a test portfolio',
                'internal_access': FolioPermission.ACCESS_NONE,
                'public_access': FolioPermission.ACCESS_NONE
            })
            self.assertEqual(
                rv.status_code,
                API_CODES.INVALID_PARAM,
                'Portfolio created with dangerous human ID: ' + bad_id
            )
            obj = json.loads(rv.data.decode('utf8'))
            self.assertEqual(obj['status'], API_CODES.INVALID_PARAM)
            self.assertIn('human_id', obj['message'])

    # Tests that chars in the human ID are correctly encoded in the portfolio URL
    def test_folio_human_id_urls(self):
        self.login('foliouser', 'foliouser')
        test_ids = [
            'a test @this *bold*! (but ok) + fin',        # chars that should be % encoded
            '\u00e2 te\u00dft \u2014 of \u00e7har\u0292'  # unicode is allowed in URLs these days
        ]
        for hid in test_ids:
            hid_encoded = urllib.parse.quote(hid)
            api_url = '/api/portfolios/'
            rv = self.app.post(api_url, data={
                'human_id': hid,
                'name': 'Test portfolio',
                'description': 'This is a test portfolio',
                'internal_access': FolioPermission.ACCESS_NONE,
                'public_access': FolioPermission.ACCESS_NONE
            })
            self.assertEqual(rv.status_code, API_CODES.SUCCESS, str(rv.data))
            obj = json.loads(rv.data.decode('utf8'))
            # Check the generated portfolio URL
            expect_end = '/' + hid_encoded + '/'
            self.assertTrue(
                obj['data']['url'].endswith(expect_end),
                'Folio URL {} but expected ending {}'.format(obj['data']['url'], expect_end)
            )
            # Check that it also works for accessing the portfolio
            api_url = '/portfolios/' + hid + '/'  # test client encodes the URL
            rv = self.app.get(api_url)
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)

    # Tests adding and removing images from a portfolio
    def test_folio_add_remove_image(self):
        db_folio = dm.get_portfolio(human_id='private')
        db_img = auto_sync_existing_file('test_images/thames.jpg', dm, tm)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/'
        self.login('foliouser', 'foliouser')
        # Get the initial image list
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertEqual(len(obj['data']), 2)  # see reset_fixtures()
        # Add another image
        rv = self.app.post(api_url, data={
            'image_id': db_img.id
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Get the new image list
        db_folio = dm.get_portfolio(db_folio.id, load_images=True, load_history=True)
        self.assertEqual(len(db_folio.images), 3)  # initial + 1
        # Check the audit trail was updated
        add_history = db_folio.history[-1]
        self.assertEqual(add_history.action, FolioHistory.ACTION_IMAGE_CHANGE)
        self.assertIn(db_img.src, add_history.action_info)
        # Check that we can't add a duplicate image
        rv = self.app.post(api_url, data={
            'image_id': db_img.id
        })
        self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
        # Remove the image
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/' + str(db_img.id) + '/'
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Check the image list again
        db_folio = dm.get_portfolio(db_folio.id, load_images=True, load_history=True)
        self.assertEqual(len(db_folio.images), 2)  # back to initial
        # Check the audit trail was updated again
        del_history = db_folio.history[-1]
        self.assertEqual(del_history.action, FolioHistory.ACTION_IMAGE_CHANGE)
        self.assertIn(db_img.src, del_history.action_info)
        self.assertGreater(del_history.id, add_history.id)
        # Check that we can't remove it again
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)

    # Tests adding images by src
    def test_folio_add_remove_image_src(self):
        db_folio = dm.get_portfolio(human_id='private', load_images=True)
        start_len = len(db_folio.images)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/'
        self.login('foliouser', 'foliouser')
        # Add an image by src
        rv = self.app.post(api_url, data={
            'image_src': 'test_images/thames.jpg'
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Check it worked
        db_folio = dm.get_portfolio(db_folio.id, load_images=True)
        self.assertEqual(len(db_folio.images), start_len + 1)
        # Check that we can't add a duplicate image src
        rv = self.app.post(api_url, data={
            'image_src': 'test_images/thames.jpg'
        })
        self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
        # A bad src should raise a not-found error
        rv = self.app.post(api_url, data={
            'image_src': 'this/does/not/exist.jpg'
        })
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        # Giving both an ID and a src should return invalid params
        rv = self.app.post(api_url, data={
            'image_id': 1,
            'image_src': 'test_images/thames.jpg'
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)

    # Tests handling of bad permissions when adding and removing images
    def test_folio_add_remove_image_permissions(self):
        db_folio = dm.get_portfolio(human_id='private')
        db_img = auto_sync_existing_file('test_images/thames.jpg', dm, tm)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/'
        # Must be logged in
        rv = self.app.post(api_url, data={
            'image_id': db_img.id
        })
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # Cannot change another user's portfolio
        main_tests.setup_user_account('anotherfoliouser', user_type='folios')
        self.login('anotherfoliouser', 'anotherfoliouser')
        rv = self.app.post(api_url, data={
            'image_id': db_img.id
        })
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # The portfolio owner must have view permission for the image being added
        self.login('foliouser', 'foliouser')
        db_owner = dm.get_user(username='foliouser', load_groups=True)
        # Set up the test user to belong to only one group
        db_owner.groups = [g for g in db_owner.groups if g.name == 'foliouser-group']
        dm.save_object(db_owner)
        self.assertEqual(len(db_owner.groups), 1)
        db_user_group = db_owner.groups[0]
        db_public_group = dm.get_group(Group.ID_PUBLIC)
        unauth_image_dir = '/secret_images'
        unauth_image_path = unauth_image_dir + '/cathedral.jpg'
        try:
            # Put an image into a folder that is not viewable by foliouser
            make_dirs(unauth_image_dir)
            copy_file('test_images/cathedral.jpg', unauth_image_path)
            db_folder = auto_sync_folder(unauth_image_dir, dm, tm, False)
            dm.save_object(
                FolderPermission(db_folder, db_public_group, FolderPermission.ACCESS_NONE)
            )
            fp = dm.save_object(
                FolderPermission(db_folder, db_user_group, FolderPermission.ACCESS_NONE),
                refresh=True
            )
            pm.reset_folder_permissions()
            # Now try to add that image to a portfolio
            db_img = auto_sync_existing_file(unauth_image_path, dm, tm)
            rv = self.app.post(api_url, data={
                'image_id': db_img.id
            })
            self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
            # This is a complicated test, so prove that it does work with the correct permission
            fp.access = FolderPermission.ACCESS_VIEW
            dm.save_object(fp)
            pm.reset_folder_permissions()
            rv = self.app.post(api_url, data={
                'image_id': db_img.id
            })
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        finally:
            delete_dir(unauth_image_dir, recursive=True)

    # Test image reordering
    def test_folio_reordering(self):
        # Get starting portfolio - see also reset_fixtures()
        db_folio = dm.get_portfolio(human_id='public')
        db_img = auto_sync_existing_file('test_images/tiger.svg', dm, tm)
        dm.save_object(FolioImage(db_folio, db_img))
        db_folio = dm.get_portfolio(human_id='public', load_images=True, load_history=True)
        # Check starting list, should be the order in which the images were added
        self.assertEqual(len(db_folio.images), 3)
        self.assertEqual(db_folio.images[0].image.src, 'test_images/blue bells.jpg')
        self.assertEqual(db_folio.images[1].image.src, 'test_images/cathedral.jpg')
        self.assertEqual(db_folio.images[2].image.src, 'test_images/tiger.svg')
        start_history_len = len(db_folio.history)
        # Check that non-owners don't have permission to reorder
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/' + str(db_img.id) + '/position/'
        main_tests.setup_user_account('anna')
        self.login('anna', 'anna')
        rv = self.app.put(api_url, data={
            'index': 0
        })
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # OK log in as the owner
        self.login('foliouser', 'foliouser')
        # Setting index before list start should use index 0
        rv = self.app.put(api_url, data={
            'index': -10
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(human_id='public', load_images=True, load_history=True)
        self.assertEqual(db_folio.images[0].image.src, 'test_images/tiger.svg')
        self.assertEqual(db_folio.images[1].image.src, 'test_images/blue bells.jpg')
        self.assertEqual(db_folio.images[2].image.src, 'test_images/cathedral.jpg')
        # Setting index to the middle should do as asked
        rv = self.app.put(api_url, data={
            'index': 1
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        jlist = json.loads(rv.data.decode('utf8'))['data']
        db_folio = dm.get_portfolio(human_id='public', load_images=True, load_history=True)
        self.assertEqual(db_folio.images[0].image.src, 'test_images/blue bells.jpg')
        self.assertEqual(jlist[0]['image']['src'], 'test_images/blue bells.jpg')
        self.assertEqual(db_folio.images[1].image.src, 'test_images/tiger.svg')
        self.assertEqual(jlist[1]['image']['src'], 'test_images/tiger.svg')
        self.assertEqual(db_folio.images[2].image.src, 'test_images/cathedral.jpg')
        self.assertEqual(jlist[2]['image']['src'], 'test_images/cathedral.jpg')
        # v4.1 #18 tiger.svg should now be at index 1 in both the JSON and the database
        self.assertEqual(db_folio.images[1].order_num, 1)
        self.assertEqual(jlist[1]['order_num'], 1)
        # Setting index after list end should use index len(list)-1
        rv = self.app.put(api_url, data={
            'index': 999
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        jlist = json.loads(rv.data.decode('utf8'))['data']
        db_folio = dm.get_portfolio(human_id='public', load_images=True, load_history=True)
        self.assertEqual(db_folio.images[0].image.src, 'test_images/blue bells.jpg')
        self.assertEqual(jlist[0]['image']['src'], 'test_images/blue bells.jpg')
        self.assertEqual(db_folio.images[1].image.src, 'test_images/cathedral.jpg')
        self.assertEqual(jlist[1]['image']['src'], 'test_images/cathedral.jpg')
        self.assertEqual(db_folio.images[2].image.src, 'test_images/tiger.svg')
        self.assertEqual(jlist[2]['image']['src'], 'test_images/tiger.svg')
        # v4.1 #18 tiger.svg should now be at index 2 in both the JSON and the database
        self.assertEqual(db_folio.images[2].order_num, 2)
        self.assertEqual(jlist[2]['order_num'], 2)
        # After 3 successful moves we should have 3 more audit trail entries
        self.assertEqual(len(db_folio.history), start_history_len + 3)
        self.assertEqual(db_folio.history[-1].action, FolioHistory.ACTION_IMAGE_CHANGE)
        self.assertEqual(db_folio.history[-2].action, FolioHistory.ACTION_IMAGE_CHANGE)
        self.assertEqual(db_folio.history[-3].action, FolioHistory.ACTION_IMAGE_CHANGE)
        self.assertIn(db_img.src, db_folio.history[-3].action_info)

    # Test folio discoverability
    def test_folio_listing(self):
        api_url = '/api/portfolios/'
        # Public users should only see public portfolios
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        hids = [folio['human_id'] for folio in obj['data']]
        self.assertEqual(len(hids), 1)
        self.assertEqual(hids[0], 'public')
        # Internal users should see internal + public portfolios
        main_tests.setup_user_account('janeaustin')
        self.login('janeaustin', 'janeaustin')
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        hids = [folio['human_id'] for folio in obj['data']]
        self.assertEqual(len(hids), 2)
        self.assertIn('public', hids)
        self.assertIn('internal', hids)
        # Portfolio owners should see their own + internal + public portfolios
        self.login('foliouser', 'foliouser')
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        hids = [folio['human_id'] for folio in obj['data']]
        self.assertEqual(len(hids), 3)
        self.assertIn('public', hids)
        self.assertIn('internal', hids)
        self.assertIn('private', hids)

    # Tests that the portfolio listing API contains the expected data fields
    def test_folio_listing_fields(self):
        api_url = '/api/portfolios/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertGreater(len(obj['data']), 0)
        folio = obj['data'][0]
        # Check that the viewing URL is included
        self.assertTrue('url' in folio)
        self.assertEqual(
            folio['url'],
            flask_app.config['PREFERRED_URL_SCHEME'] + '://' +
            flask_app.config['PUBLIC_HOST_NAME'] +
            flask_app.config['APPLICATION_ROOT'] +
            'portfolios/' + folio['human_id'] + '/'
        )
        # We're not expecting the image list or audit trail
        # (this is only a performance concern, not a functional one)
        self.assertFalse('images' in folio)
        self.assertFalse('history' in folio)

    # Tests viewing of portfolios
    def test_folio_viewing(self):
        # Set up test URLs
        db_public_folio = dm.get_portfolio(human_id='public')
        db_internal_folio = dm.get_portfolio(human_id='internal')
        db_private_folio = dm.get_portfolio(human_id='private')
        public_api_url = '/api/portfolios/' + str(db_public_folio.id) + '/'
        public_api_url2 = '/api/portfolios/?human_id=' + str(db_public_folio.human_id)
        public_view_url = '/portfolios/' + db_public_folio.human_id + '/'
        internal_api_url = '/api/portfolios/' + str(db_internal_folio.id) + '/'
        internal_api_url2 = '/api/portfolios/?human_id=' + str(db_internal_folio.human_id)
        internal_view_url = '/portfolios/' + db_internal_folio.human_id + '/'
        private_api_url = '/api/portfolios/' + str(db_private_folio.id) + '/'
        private_api_url2 = '/api/portfolios/?human_id=' + str(db_private_folio.human_id)
        private_view_url = '/portfolios/' + db_private_folio.human_id + '/'
        # On top of the standard test fixtures, create another private portfolio
        priv_user2 = main_tests.setup_user_account('janeaustin')
        self.create_portfolio('private2', priv_user2, FolioPermission.ACCESS_NONE, FolderPermission.ACCESS_NONE)
        db_private2_folio = dm.get_portfolio(human_id='private2')
        private2_api_url = '/api/portfolios/' + str(db_private2_folio.id) + '/'
        private2_api_url2 = '/api/portfolios/?human_id=' + str(db_private2_folio.human_id)
        private2_view_url = '/portfolios/' + db_private2_folio.human_id + '/'

        def view_pf(url, expect_json, expect_success):
            rv = self.app.get(url)
            self.assertEqual(
                rv.status_code,
                API_CODES.SUCCESS if expect_success else API_CODES.UNAUTHORISED
            )
            self.assertIn(
                'application/json' if expect_json else 'html',
                rv.headers['Content-Type']
            )

        def run_test_cases(test_cases):
            for tc in test_cases:
                # Expects (API view URL by ID, API view URL by human ID, web view URL, should succeed)
                view_pf(tc[0], True, tc[3])
                view_pf(tc[1], True, tc[3])
                view_pf(tc[2], False, tc[3])

        # Public user should be able to view public portfolio, not others
        test_cases = [
            (public_api_url, public_api_url2, public_view_url, True),
            (internal_api_url, internal_api_url2, internal_view_url, False),
            (private_api_url, private_api_url2, private_view_url, False),
        ]
        run_test_cases(test_cases)
        # Internal user should be able to view internal + public portfolio, not private
        test_cases = [
            (public_api_url, public_api_url2, public_view_url, True),
            (internal_api_url, internal_api_url2, internal_view_url, True),
            (private_api_url, private_api_url2, private_view_url, False),
        ]
        main_tests.setup_user_account('plainuser')
        self.login('plainuser', 'plainuser')
        run_test_cases(test_cases)
        # Portfolio owners should see their own + internal + public portfolios, not another private
        test_cases = [
            (public_api_url, public_api_url2, public_view_url, True),
            (internal_api_url, internal_api_url2, internal_view_url, True),
            (private_api_url, private_api_url2, private_view_url, True),
            (private2_api_url, private2_api_url2, private2_view_url, False),
        ]
        self.login('foliouser', 'foliouser')
        run_test_cases(test_cases)

    # Tests that the portfolio viewing API contains the expected data fields
    def test_folio_viewing_fields(self):
        db_public_folio = dm.get_portfolio(human_id='public')
        api_url = '/api/portfolios/' + str(db_public_folio.id) + '/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        folio = obj['data']
        self.assertGreater(len(folio['images']), 0)
        self.assertGreater(len(folio['permissions']), 0)
        self.assertGreater(len(folio['history']), 0)
        self.assertTrue('downloads' in folio)
        self.assertTrue('url' in folio)
        self.assertEqual(
            folio['url'],
            flask_app.config['PREFERRED_URL_SCHEME'] + '://' +
            flask_app.config['PUBLIC_HOST_NAME'] +
            flask_app.config['APPLICATION_ROOT'] +
            'portfolios/' + db_public_folio.human_id + '/'
        )

    # Tests that single-image parameters get stored and get applied
    def test_image_parameters(self):
        db_folio = dm.get_portfolio(human_id='private', load_images=True)
        db_img = db_folio.images[0].image
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/' + str(db_img.id) + '/'
        self.login('foliouser', 'foliouser')
        # Invalid image parameters should fail validation
        params = {'width': {'value': 'badnumber'}}
        rv = self.app.put(api_url, data={
            'image_parameters': json.dumps(params)
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        # Valid image parameters should get saved
        params = {'width': {'value': 800}, 'format': {'value': 'tif'}}
        rv = self.app.put(api_url, data={
            'image_parameters': json.dumps(params)
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # The API should return the parameters in the generated image URLs
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        folio = obj['data']
        self.assertTrue('url' in folio['images'][0])
        self.assertIn('width=800', folio['images'][0]['url'])
        self.assertIn('format=tif', folio['images'][0]['url'])
        # And again for the .../images/ endpoint
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        image_list = obj['data']
        self.assertTrue('url' in image_list[0])
        self.assertIn('width=800', image_list[0]['url'])
        self.assertIn('format=tif', image_list[0]['url'])

    # Tests deletion of portfolios
    def test_folio_delete(self):
        db_folio = dm.get_portfolio(human_id='private')
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        # Public access should be denied
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # Deleting another user's portfolio should be denied
        main_tests.setup_user_account('plainuser')
        self.login('plainuser', 'plainuser')
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # Deleting your own portfolio should work
        self.login('foliouser', 'foliouser')
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Check it's really gone
        db_folio = dm.get_portfolio(db_folio.id)
        self.assertIsNone(db_folio)

    # Tests that folio administrators can change other user's portfolios
    def test_folio_administrator_permission(self):
        db_folio = dm.get_portfolio(human_id='private')
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        main_tests.setup_user_account('folioadmin', user_type='admin_folios')
        self.login('folioadmin', 'folioadmin')
        # Edit permission
        rv = self.app.put(api_url, data={
            'human_id': db_folio.human_id,
            'name': 'Change name',
            'description': 'Change description',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Delete permission
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)

    # Tests an export of image originals
    def test_publish_originals(self):
        db_folio = dm.get_portfolio(human_id='public')
        export = self.publish_portfolio(
            db_folio, 'Test export of public portfolio', originals=True
        )
        self.assertGreater(len(export.filename), 0)
        self.assertGreater(export.filesize, 0)
        published_filepath = get_portfolio_export_file_path(export)
        self.assertTrue(path_exists(published_filepath, require_file=True))
        # Audit trail should have been updated
        db_folio = dm.get_portfolio(db_folio.id, load_images=True, load_history=True)
        self.assertEqual(db_folio.history[-1].action, FolioHistory.ACTION_PUBLISHED)
        # Check the images in the zip are in order and match the originals
        exzip = zipfile.ZipFile(get_abs_path(published_filepath), 'r')
        try:
            zip_list = exzip.infolist()
            for idx, entry in enumerate(zip_list):
                img_file_path = db_folio.images[idx].image.src
                img_info = get_file_info(img_file_path)
                self.assertIsNotNone(img_info)
                self.assertEqual(entry.filename, os.path.basename(img_file_path))
                self.assertEqual(entry.file_size, img_info['size'])
        finally:
            exzip.close()

    # Tests an export of resized images
    def test_publish_resized(self):
        db_folio = dm.get_portfolio(human_id='public', load_images=True)
        export = self.publish_portfolio(
            db_folio, 'Test export of public portfolio', originals=False,
            image_params_dict={'width': {'value': 200}}
        )
        self.assertGreater(len(export.filename), 0)
        self.assertGreater(export.filesize, 0)
        published_filepath = get_portfolio_export_file_path(export)
        self.assertTrue(path_exists(published_filepath, require_file=True))
        # Check the images in the zip have been resized
        exzip = zipfile.ZipFile(get_abs_path(published_filepath), 'r')
        try:
            zip_list = exzip.infolist()
            for idx, entry in enumerate(zip_list):
                img_file_path = db_folio.images[idx].image.src
                img_info = get_file_info(img_file_path)
                self.assertIsNotNone(img_info)
                self.assertLess(entry.file_size, img_info['size'])
        finally:
            exzip.close()

    # Tests an export with both portfolio level and single image changes
    def test_publish_mixed_changes(self):
        # Set the portfolio files as renamed and resized
        db_folio = dm.get_portfolio(human_id='internal', load_images=True)
        db_folio.images[0].filename = 'image1.jpg'
        db_folio.images[0].parameters = {'width': {'value': 100}}
        dm.save_object(db_folio.images[0])
        db_folio.images[1].filename = 'image2.jpg'
        db_folio.images[1].parameters = {'width': {'value': 100}}
        dm.save_object(db_folio.images[1])
        # Now export the portfolio as PNG files
        export = self.publish_portfolio(
            db_folio, 'Test export of internal portfolio', originals=False,
            image_params_dict={'format': {'value': 'png'}}
        )
        published_filepath = get_portfolio_export_file_path(export)
        self.assertTrue(path_exists(published_filepath, require_file=True))
        # Check the images in the zip have been renamed, resized, and saved as PNG
        exzip = zipfile.ZipFile(get_abs_path(published_filepath), 'r')
        try:
            entries = exzip.infolist()
            self.assertEqual(entries[0].filename, 'image1.png')
            self.assertEqual(entries[1].filename, 'image2.png')
            for fname in ['image1.png', 'image2.png']:
                img_file = exzip.open(fname, 'r')
                png_dims = imaging_tests.get_png_dimensions(img_file.read())
                self.assertEqual(png_dims[0], 100)
        finally:
            exzip.close()

    # Tests that the filename override can't be used to access or overwrite system files
    def test_publish_bad_filenames(self):
        db_folio = dm.get_portfolio(human_id='private', load_images=True)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/' + str(db_folio.images[0].image_id) + '/'
        self.login('foliouser', 'foliouser')
        bad_filenames = [
            '/etc/passwdx',  # Paths are not allowed
            '../etc/passwdx',
            '//etc/passwdx',
            './../etc/passwdx',
            'ütêßt.jpg',     # Only ascii is supported in zips
            'hellö.jpg'
        ]
        for bf in bad_filenames:
            rv = self.app.put(api_url, data={'filename': bf})
            self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
            obj = json.loads(rv.data.decode('utf8'))
            self.assertIn('filename not allowed', obj['message'])

    # Tests that an empty portfolio cannot be published
    def test_publish_empty(self):
        db_folio = dm.get_portfolio(human_id='public', load_images=True)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/exports/'
        for f_img in db_folio.images:
            dm.delete_object(f_img)
        self.login('foliouser', 'foliouser')
        rv = self.app.post(api_url, data={
            'description': 'Test export of empty portfolio',
            'originals': True,
            'expiry_time': to_iso_datetime(datetime.utcnow() + timedelta(days=1))
        })
        self.assertEqual(rv.status_code, API_CODES.INVALID_PARAM)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertEqual(obj['status'], API_CODES.INVALID_PARAM)
        self.assertIn('portfolio is empty', obj['message'])

    # Tests access required for publishing
    def test_publish_permissions(self):
        db_folio = dm.get_portfolio(human_id='public')
        api_url = '/api/portfolios/' + str(db_folio.id) + '/exports/'
        # Must be logged in
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # A portfolio user cannot publish another user's portfolio, even a public one
        main_tests.setup_user_account('anotherfoliouser', user_type='folios')
        self.login('anotherfoliouser', 'anotherfoliouser')
        rv = self.app.post(api_url, data={
            'description': 'Test',
            'originals': True,
            'image_parameters': '{}',
            'expiry_time': to_iso_datetime(datetime.utcnow())
        })
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)

    def test_portfolio_download(self):
        # Publish the public portfolio
        db_public_folio = dm.get_portfolio(human_id='public')
        public_export = self.publish_portfolio(db_public_folio, 'Public export', True)
        self.assertGreater(len(public_export.filename), 0)
        # Publish the internal portfolio
        db_internal_folio = dm.get_portfolio(human_id='internal')
        internal_export = self.publish_portfolio(db_internal_folio, 'Internal export', True)
        self.assertGreater(len(internal_export.filename), 0)
        # Public download of a public portfolio should be OK
        api_url = '/portfolios/public/downloads/' + public_export.filename
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Public download of an internal portfolio should not be allowed
        api_url = '/portfolios/internal/downloads/' + internal_export.filename
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # But when logged in it should work
        main_tests.setup_user_account('emilybronte')
        self.login('emilybronte', 'emilybronte')
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Check that we got back a valid zip file
        self.assertIn('application/zip', rv.headers['Content-Type'])
        self.assertIn('attachment', rv.headers['Content-Disposition'])
        temp_zip_file = '/tmp/qis_download.zip'
        try:
            with open(temp_zip_file, 'wb') as f:
                f.write(rv.data)
            dlzip = zipfile.ZipFile(temp_zip_file, 'r')
            try:
                entries = dlzip.infolist()
                # These should match what reset_fixtures() does
                self.assertEqual(entries[0].filename, 'blue bells.jpg')
                self.assertEqual(entries[1].filename, 'cathedral.jpg')
            finally:
                dlzip.close()
        finally:
            os.remove(temp_zip_file)
        # Check the audit trail was updated
        db_internal_folio = dm.get_portfolio(db_internal_folio.id, load_history=True)
        self.assertEqual(db_internal_folio.history[-1].action, FolioHistory.ACTION_DOWNLOADED)
        self.assertEqual('emilybronte', db_internal_folio.history[-1].user.username)

    # Tests that the download filename cannot be used to access other files
    # Note that Flask by default treats %2F as a URL path separator:
    #   https://github.com/pallets/flask/issues/900
    #   https://github.com/pallets/werkzeug/issues/477
    #   https://github.com/pallets/werkzeug/issues/797
    # and Apache by default does the same, controlled by AllowEncodedSlashes
    # so that - unless a future release of Flask/Werkzeug changes things -
    # all these URLs never even get routed to the view function
    def test_portfolio_download_bad_access(self):
        def quote(url_path):
            return url_path.replace('/', '%2F')
        # Now I just cannot get mock to wrap the portfolio_download view function,
        # so here is a manual wrapper that counts how many times the view is invoked
        dl_view_name = 'folios.portfolio_download'
        dl_view_fn = self.app.application.view_functions[dl_view_name]
        dl_view_count = AttrObject(n=0)
        def dl_view_wrapper(*args, **kwargs):
            dl_view_count.n += 1
            return dl_view_fn(*args, **kwargs)
        self.app.application.view_functions[dl_view_name] = dl_view_wrapper
        # Get a known working download URL
        db_public_folio = dm.get_portfolio(human_id='public')
        export = self.publish_portfolio(db_public_folio, 'Public export', True)
        api_base_url = '/portfolios/public/downloads/'
        rv = self.app.get(api_base_url + export.filename)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Prove that the view counter works before we rely on it later
        self.assertEqual(dl_view_count.n, 1)
        # Now try to use this URL to pull down an image file instead
        rv = self.app.get(api_base_url + quote('../test_images/cathedral.jpg'))
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        # Try to pull a system file
        rv = self.app.get(api_base_url + quote('~root/../../../etc/passwd'))
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        rv = self.app.get(api_base_url + quote('../../../../../../../../../etc/passwd'))
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        rv = self.app.get(api_base_url + quote('/etc/passwd'))
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        # Also try leading // to see if the code only strips one of them
        rv = self.app.get(api_base_url + quote('//etc/passwd'))
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        # Also try mixed and double-encoding
        rv = self.app.get(api_base_url + '%2F/etc%2Fpasswd')
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        rv = self.app.get(api_base_url + '/%2Fetc%2Fpasswd')
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        rv = self.app.get(api_base_url + '%252Fetc%252Fpasswd')
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        # Check that even if the data has a bad filename that the code
        # still prevents escape from the images repository
        export.filename = '../../../etc/passwd'
        dm.save_object(export)
        dl_view_count.n = 0
        rv = self.app.get(api_base_url + quote(export.filename))
        if dl_view_count.n == 0:
            # Flask routing did not let it through
            self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        else:
            # The view was invoked, our code should block the directory traversal
            self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)

    # Tests that deleting a portfolio deletes the exported files too
    def test_folio_delete_all(self):
        db_folio = dm.get_portfolio(human_id='private')
        export = self.publish_portfolio(db_folio, 'Private portfolio export', True)
        # Export directory should exist
        export_dir = os.path.dirname(get_portfolio_export_file_path(export))
        self.assertTrue(path_exists(export_dir, require_directory=True))
        # Delete the whole portfolio
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        self.login('foliouser', 'foliouser')
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Export directory should be gone
        self.assertFalse(path_exists(export_dir))

    # Tests unpublishing a portfolio
    def test_publish_unpublish(self):
        db_folio = dm.get_portfolio(human_id='private')
        export1 = self.publish_portfolio(db_folio, 'Private portfolio export 1', True)
        export2 = self.publish_portfolio(db_folio, 'Private portfolio export 2', False)
        # Check the published files exist
        self.assertTrue(path_exists(get_portfolio_export_file_path(export1), require_file=True))
        self.assertTrue(path_exists(get_portfolio_export_file_path(export2), require_file=True))
        # Check the API returns the download details
        self.login('foliouser', 'foliouser')
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertEqual(len(obj['data']['downloads']), 2)
        # And again for the .../exports/ endpoint
        api_url = '/api/portfolios/' + str(db_folio.id) + '/exports/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertEqual(len(obj['data']), 2)
        # Unpublish both exports
        api_url = '/api/portfolios/' + str(db_folio.id) + '/exports/' + str(export1.id) + '/'
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/exports/' + str(export2.id) + '/'
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # The audit trail should say unpublished x2
        db_folio = dm.get_portfolio(db_folio.id, load_history=True)
        self.assertEqual(db_folio.history[-1].action, FolioHistory.ACTION_UNPUBLISHED)
        self.assertEqual(db_folio.history[-2].action, FolioHistory.ACTION_UNPUBLISHED)
        # And the export directory should be gone
        export_dir = os.path.dirname(get_portfolio_export_file_path(export1))
        self.assertFalse(path_exists(export_dir))

    # Tests the expiry of exported portfolios
    def test_publish_expiry(self):
        # Publish the public portfolio with a few seconds TTL
        db_folio = dm.get_portfolio(human_id='public')
        export = self.publish_portfolio(
            db_folio, 'Public portfolio export', True,
            expiry_time=datetime.utcnow() + timedelta(seconds=2)
        )
        # Check that the export directory is there
        export_dir = os.path.dirname(get_portfolio_export_file_path(export))
        self.assertTrue(path_exists(export_dir))
        # Check that the download works
        api_url = '/portfolios/public/downloads/' + export.filename
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        # Check that the audit trail says published and downloaded 
        db_folio = dm.get_portfolio(db_folio.id, load_history=True)
        self.assertEqual(db_folio.history[-2].action, FolioHistory.ACTION_PUBLISHED)
        self.assertEqual(db_folio.history[-1].action, FolioHistory.ACTION_DOWNLOADED)
        # Wait for expiry
        time.sleep(2)
        # Force the expiry cleanup background job to run
        task_obj = tm.add_task(
            None,
            'Expire portfolio exports',
            'expire_portfolio_exports',
            priority=Task.PRIORITY_NORMAL,
            log_level='info',
            error_log_level='error'
        )
        self.assertIsNotNone(task_obj)
        tm.wait_for_task(task_obj.id, 10)
        # Check that the download is now a 404
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
        # Check that the export directory is gone
        self.assertFalse(path_exists(export_dir))
        # Check that the audit trail says unpublished
        db_folio = dm.get_portfolio(db_folio.id, load_history=True)
        self.assertEqual(db_folio.history[-1].action, FolioHistory.ACTION_UNPUBLISHED)

    # The "last updated" field is for use with published zips to know when they
    # might be out of date. This isn't too obvious so test it works correctly.
    def test_folio_last_updated(self):
        # Get a starting point
        db_folio = dm.get_portfolio(human_id='public')
        prev_date = db_folio.last_updated
        self.login('foliouser', 'foliouser')
        # Saving the folio header (e.g. a folio rename) should not change last_updated
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        rv = self.app.put(api_url, data={
            'human_id': 'new id',
            'name': 'Renamed portfolio',
            'description': 'Renamed portfolio',
            'internal_access': FolioPermission.ACCESS_VIEW,
            'public_access': FolioPermission.ACCESS_VIEW
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(db_folio.id)
        self.assertEqual(db_folio.last_updated, prev_date)
        # But adding an image should change it
        db_img = auto_sync_existing_file('test_images/thames.jpg', dm, tm)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/'
        rv = self.app.post(api_url, data={'image_id': db_img.id})
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(db_folio.id)
        self.assertGreater(db_folio.last_updated, prev_date)
        prev_date = db_folio.last_updated
        # Changing image params or setting a filename should change it
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/' + str(db_img.id) + '/'
        test_params = [
            {'image_parameters': json.dumps({'width': {'value': 800}})},
            {'filename': 'a river.jpg'},
        ]
        for api_params in test_params:
            rv = self.app.put(api_url, data=api_params)
            self.assertEqual(rv.status_code, API_CODES.SUCCESS)
            db_folio = dm.get_portfolio(db_folio.id)
            self.assertGreater(db_folio.last_updated, prev_date)
            prev_date = db_folio.last_updated
        # Whether changing the order of images should count as an update is
        # debatable. Once extracted from the zip most people are going to see
        # the files listed in alphanumeric order by their o/s, so we're going
        # to say that a re-order should NOT change last_updated.
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/' + str(db_img.id) + '/'
        rv = self.app.put(api_url, data={'index': 0})
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(db_folio.id)
        self.assertEqual(db_folio.last_updated, prev_date)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/' + str(db_img.id) + '/position/'
        rv = self.app.put(api_url, data={'index': 1})
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(db_folio.id)
        self.assertEqual(db_folio.last_updated, prev_date)

    # v4.1 Tests that user/owner objects are not exported, because portfolios
    # can be public and we don't want to leak any user information
    def test_folio_no_user_info(self):
        db_public_folio = dm.get_portfolio(human_id='public')
        api_url = '/api/portfolios/' + str(db_public_folio.id) + '/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        folio = json.loads(rv.data.decode('utf8'))['data']
        # a) Check folio header - owner field
        self.assertNotIn('owner', folio)
        # b) Check folio audit trail - action user
        self.assertIn('history', folio)
        self.assertNotIn('user', folio['history'][0])
        # c) Check that folio permissions don't list group users
        self.assertIn('permissions', folio)
        self.assertNotIn('group', folio['permissions'])
        # Check that the list API does not reveal this same stuff either
        api_url = '/api/portfolios/'
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data.decode('utf8'))
        self.assertEqual(len(obj['data']), 1)
        folio = obj['data'][0]
        # a) Check folio header - owner field
        self.assertNotIn('owner', folio)
        # b) Check folio audit trail - not expected from list API
        self.assertNotIn('history', folio)
        # c) Check that folio permissions don't list group users
        self.assertIn('permissions', folio)
        self.assertNotIn('group', folio['permissions'])

    # v4.1 #10 Deleting a portfolio twice should give 200 then 404
    def test_folio_double_delete(self):
        db_folio = dm.get_portfolio(human_id='private')
        api_url = '/api/portfolios/' + str(db_folio.id) + '/'
        self.login('foliouser', 'foliouser')
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        rv = self.app.delete(api_url)
        self.assertEqual(rv.status_code, API_CODES.NOT_FOUND)
