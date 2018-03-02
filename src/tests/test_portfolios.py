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

import tests as main_tests
from tests import (
    BaseTestCase, setup_user_account
)

from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import task_engine as tm
from imageserver.flask_app import permissions_engine as pm

from imageserver.filesystem_sync import auto_sync_existing_file
from imageserver.models import (
    Group,
    Folio, FolioImage, FolioPermission, FolioHistory, FolioExport
)


class PortfoliosAPITests(BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super(PortfoliosAPITests, cls).setUpClass()
        main_tests.init_tests()

    def setUp(self):
        # Restore clean test data before each test
        self.reset_fixtures()

    def reset_fixtures(self):
        # Wipe the old data
        db_session = dm.db_get_session()
        db_session.query(Folio).delete()
        db_session.query(FolioImage).delete()
        db_session.query(FolioPermission).delete()
        db_session.query(FolioHistory).delete()
        db_session.query(FolioExport).delete()
        db_session.commit()
        # Create private, internal and public test portfolios
        db_user = setup_user_account('foliouser')
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

    def test_nothing(self):
        pass

# API test portfolio creation
#     test adding images
#     test portfolio view
#     test audit trail
#     test remove images
#     test portfolio view
#     test audit trail

# API test portfolio create permission is required for creation
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
