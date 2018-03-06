# -*- coding: utf-8 -*-
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

import json

import tests as main_tests

from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import task_engine as tm
from imageserver.flask_app import permissions_engine as pm

from imageserver.api_util import API_CODES
from imageserver.filesystem_manager import (
    copy_file, delete_dir, make_dirs
)
from imageserver.filesystem_sync import auto_sync_existing_file, auto_sync_folder
from imageserver.models import (
    FolderPermission, Group,
    Folio, FolioImage, FolioPermission, FolioHistory, FolioExport
)


class PortfoliosAPITests(main_tests.BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super(PortfoliosAPITests, cls).setUpClass()
        main_tests.init_tests()

    def setUp(self):
        super(PortfoliosAPITests, self).setUp()
        # Restore clean test data before each test
        self.reset_fixtures()

    def reset_fixtures(self):
        # Wipe the old data
        db_session = dm.db_get_session()
        db_session.query(FolioImage).delete()
        db_session.query(FolioPermission).delete()
        db_session.query(FolioHistory).delete()
        db_session.query(FolioExport).delete()
        db_session.query(Folio).delete()
        db_session.commit()
        # Create private, internal and public test portfolios
        db_user = main_tests.setup_user_account('foliouser')
        db_group = db_user.groups[-1]
        db_group.permissions.folios = True
        dm.save_object(db_group)
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

    # Tests portfolio creation and permissions
    def test_folio_create(self):
        api_url = '/api/portfolios/'
        # Must be logged in to create
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.REQUIRES_AUTH)
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
        obj = json.loads(rv.data)
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
        obj = json.loads(rv.data)
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
            'id': db_folio.id,
            'human_id': '',
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        self.assertGreater(len(obj['data']['human_id']), 0)
        self.assertNotEqual(obj['data']['human_id'], 'public')
        # Updates - duplicate human ID should not be allowed
        rv = self.app.put(api_url, data={
            'id': db_folio.id,
            'human_id': 'private',          # see reset_fixtures()
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)
        # A human ID of all whitespace should be treated the same as a blank
        rv = self.app.post(api_url, data={
            'human_id': '  ',
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'internal_access': FolioPermission.ACCESS_NONE,
            'public_access': FolioPermission.ACCESS_NONE
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        self.assertGreater(len(obj['data']['human_id']), 0)
        self.assertNotEqual(obj['data']['human_id'].strip(), '')

    # Tests adding and removing images from a portfolio
    def test_folio_add_remove_image(self):
        db_folio = dm.get_portfolio(human_id='private')
        db_img = auto_sync_existing_file('test_images/thames.jpg', dm, tm)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/'
        self.login('foliouser', 'foliouser')
        # Get the initial image list
        rv = self.app.get(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
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

    # Tests handling of bad permissions when adding and removing images
    def test_folio_add_remove_image_permissions(self):
        db_folio = dm.get_portfolio(human_id='private')
        db_img = auto_sync_existing_file('test_images/thames.jpg', dm, tm)
        api_url = '/api/portfolios/' + str(db_folio.id) + '/images/'
        # Must be logged in
        rv = self.app.post(api_url, data={
            'image_id': db_img.id
        })
        self.assertEqual(rv.status_code, API_CODES.REQUIRES_AUTH)
        # Cannot change another user's portfolio
        db_user = main_tests.setup_user_account('anotherfoliouser')
        db_group = db_user.groups[-1]
        db_group.permissions.folios = True
        dm.save_object(db_group)
        self.login('anotherfoliouser', 'anotherfoliouser')
        rv = self.app.post(api_url, data={
            'image_id': db_img.id
        })
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # The portfolio owner must have view permission for the image being added
        self.login('foliouser', 'foliouser')
        db_owner = dm.get_user(username='foliouser', load_groups=True)
        self.assertEqual(len(db_owner.groups), 1)  # Ensure no other group permissions need changing
        db_group = db_owner.groups[-1]
        unauth_image_dir = '/secret_images'
        unauth_image_path = unauth_image_dir + '/cathedral.jpg'
        try:
            # Put an image into a folder that is not viewable by foliouser
            make_dirs(unauth_image_dir)
            copy_file('test_images/cathedral.jpg', unauth_image_path)
            db_folder = auto_sync_folder(unauth_image_dir, dm, tm, False)
            fp = FolderPermission(db_folder, db_group, FolderPermission.ACCESS_NONE)
            dm.save_object(fp)
            pm.reset_folder_permissions()
            # Now try to add that image
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
        rv = self.app.post(api_url, data={
            'index': 0
        })
        self.assertEqual(rv.status_code, API_CODES.UNAUTHORISED)
        # OK log in as the owner
        self.login('foliouser', 'foliouser')
        # Setting index before list start should use index 0
        rv = self.app.post(api_url, data={
            'index': -10
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(human_id='public', load_images=True, load_history=True)
        self.assertEqual(db_folio.images[0].image.src, 'test_images/tiger.svg')
        self.assertEqual(db_folio.images[1].image.src, 'test_images/blue bells.jpg')
        self.assertEqual(db_folio.images[2].image.src, 'test_images/cathedral.jpg')
        # Setting index to the middle should do as asked
        rv = self.app.post(api_url, data={
            'index': 1
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(human_id='public', load_images=True, load_history=True)
        self.assertEqual(db_folio.images[0].image.src, 'test_images/blue bells.jpg')
        self.assertEqual(db_folio.images[1].image.src, 'test_images/tiger.svg')
        self.assertEqual(db_folio.images[2].image.src, 'test_images/cathedral.jpg')
        # Setting index after list end should use index len(list)-1
        rv = self.app.post(api_url, data={
            'index': 999
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        db_folio = dm.get_portfolio(human_id='public', load_images=True, load_history=True)
        self.assertEqual(db_folio.images[0].image.src, 'test_images/blue bells.jpg')
        self.assertEqual(db_folio.images[1].image.src, 'test_images/cathedral.jpg')
        self.assertEqual(db_folio.images[2].image.src, 'test_images/tiger.svg')
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
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        hids = [folio.human_id for folio in obj['data']]
        self.assertEqual(len(hids), 1)
        self.assertEqual(hids[0], 'public')
        # Internal users should see internal + public portfolios
        main_tests.setup_user_account('janeaustin')
        self.login('janeaustin', 'janeaustin')
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        hids = [folio.human_id for folio in obj['data']]
        self.assertEqual(len(hids), 2)
        self.assertIn('public', hids)
        self.assertIn('internal', hids)
        # Portfolio owners should see their own + internal + public portfolios
        self.login('foliouser', 'foliouser')
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        hids = [folio.human_id for folio in obj['data']]
        self.assertEqual(len(hids), 3)
        self.assertIn('public', hids)
        self.assertIn('internal', hids)
        self.assertIn('private', hids)

    # Tests that the portfolio list API does not return the image lists and audit
    # trail too. This is only a performance concern, not a functional one.
    def test_folio_listing_fields(self):
        api_url = '/api/portfolios/'
        rv = self.app.post(api_url)
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        self.assertGreater(len(obj['data']), 0)
        folio = obj['data'][0]
        self.assertFalse(hasattr(folio, 'images'))
        self.assertFalse(hasattr(folio, 'history'))

# API get - test private portfolio can only be viewed by owner
# API get - test internal portfolio can only be logged in users
# API get - test public portfolio can be viewed by public
# API get - test private and internal portfolios can't be viewed by public
#           test change of group permissions
# and the same for view page

# API delete - test required permissions
#              test all files removed

# API test single image changes come out in URLs for portfolio image list

# API test export of originals
#     test audit trail
# API test export with resize
# API test export with resize and single image changes
# API test export with filename changes
# API test normal user cannot export another user's portfolio

# URLs test download of zip, check zip content
#      test format changes change file extension
# URLs test download of zip requires download permission
# URLs test download of zip with public download permission
#      test audit trail
# URLs test basic view page requires view permission
# URLs test basic view page with public view permission

# API test unpublish
#     test files removed
#     test audit trail

# API test export expiry
#     test files removed
#     test audit trail

# API test files folder removed when empty

# API test portfolio administrator can change, unpublish and delete another user's portfolios
