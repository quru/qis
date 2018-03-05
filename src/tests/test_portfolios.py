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
from imageserver.filesystem_sync import auto_sync_existing_file
from imageserver.models import (
    Group,
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
            'owner_id': db_owner.id
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        self.assertGreater(obj['data']['id'], 0)
        self.assertEqual(obj['data']['human_id'], 'mypf1')
        self.assertEqual(obj['data']['description'], 'This is a test portfolio')
        self.assertEqual(obj['data']['owner_id'], db_owner.id)

    # Test the human ID value when creating portfolios
    def test_folio_human_id(self):
        api_url = '/api/portfolios/'
        db_owner = dm.get_user(username='foliouser')
        self.login('foliouser', 'foliouser')
        # Creation - blank human ID should have one allocated
        rv = self.app.post(api_url, data={
            'human_id': '',
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'owner_id': db_owner.id
        })
        self.assertEqual(rv.status_code, API_CODES.SUCCESS)
        obj = json.loads(rv.data)
        self.assertGreater(len(obj['data']['human_id']), 0)
        # Creation - duplicate human ID should not be allowed
        rv = self.app.post(api_url, data={
            'human_id': 'private',          # see reset_fixtures()
            'name': 'Test portfolio',
            'description': 'This is a test portfolio',
            'owner_id': db_owner.id
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
            'owner_id': db_owner.id
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
            'owner_id': db_owner.id
        })
        self.assertEqual(rv.status_code, API_CODES.ALREADY_EXISTS)


# API test adding images
#     test portfolio view
#     test audit trail
#     test remove images
#     test portfolio view
#     test audit trail

# API test image view permission is required to add image
# API test normal user cannot publish another user's portfolio
# API test portfolio administrator can change, unpublish and delete another user's portfolios

# API list - test public users see only public portfolios
# API list - test internal users see internal + public portfolios
# API list - test internal users see owned + internal + public portfolios

# API get - test private portfolio can only be viewed by owner
# API get - test internal portfolio can only be logged in users
# API get - test public portfolio can be viewed by public
# API get - test private and internal portfolios can't be viewed by public

# API delete - test required permissions
#              test all files removed

# API test image reordering, test required permissions
#     test audit trail

# API test single image changes come out in URLs for portfolio image list

# API test export of originals
#     test audit trail
# API test export with resize
# API test export with resize and single image changes
# API test export with filename changes

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
