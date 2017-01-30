# -*- coding: utf-8 -*-
#
# Quru Image Server
#
# Document:      test_web_pages.py
# Date started:  25 Aug 2016
# By:            Matt Fozard
# Purpose:       Tests the web interface
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
# 25Aug2016  Matt  Moved web page tests out from tests.py
#

import os
import shutil

import tests as main_tests
from tests import BaseTestCase, setup_user_account

from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import cache_engine as cm
from imageserver.filesystem_manager import (
    get_abs_path, delete_file, delete_dir, make_dirs
)


class ImageServerTestsWebPages(BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super(ImageServerTestsWebPages, cls).setUpClass()
        main_tests.setup()
        # Create a plain user for testing pages that require login
        setup_user_account('webuser', 'none')

    # Utility to call a page requiring login, with and without login,
    # returns the response of the requested URL after logging in.
    def call_page_requiring_login(self, url, admin_login=False,
                                  required_text=None, required_status=200):
        # Check that anonymous user gets redirected to login
        rv = self.app.get(url)
        self.assertEqual(rv.status_code, 302)
        # Login
        if admin_login:
            self.login('admin', 'admin')
        else:
            self.login('webuser', 'webuser')
        # Call the requested page
        rv = self.app.get(url)
        self.assertEqual(rv.status_code, required_status)
        if required_text:
            self.assertIn(required_text, rv.data)
        return rv

    # Login page
    def test_login_page(self):
        rv = self.app.get('/login/')
        self.assertEqual(rv.status_code, 200)

    # Login action
    def test_login(self):
        self.login('admin', 'admin')

    # Logout action
    def test_logout(self):
        self.logout()

    # Home page
    def test_index_page(self):
        from imageserver import __about__
        rv = self.app.get('/')
        self.assertEqual(rv.status_code, 200)
        self.assertIn(
            __about__.__title__ + ' v' + __about__.__version__,
            rv.data
        )

    # Help page
    def test_help_page(self):
        self.call_page_requiring_login(
            '/help/',
            False,
            'This guide is aimed at web site editors'
        )

    # File upload page
    def test_file_upload_page(self):
        self.call_page_requiring_login('/upload/', False)

    # File upload complete page, populated
    def test_file_upload_complete_page(self):
        self.login('admin', 'admin')
        # Copy a test file to upload
        src_file = get_abs_path('test_images/cathedral.jpg')
        dst_file = '/tmp/qis_uploadfile.jpg'
        shutil.copy(src_file, dst_file)
        try:
            # Upload
            rv = self.file_upload(self.app, dst_file, 'test_images')
            self.assertEqual(rv.status_code, 200)
            # Test upload complete page
            rv = self.app.get('/uploadcomplete/')
            self.assertEqual(rv.status_code, 200)
            self.assertIn('1 image was uploaded successfully.', rv.data)
            # #2575 The thumbnail needs to set "&format=jpg" otherwise it breaks for
            #       browser-unsupported types e.g. TIF, PDF files
            self.assertIn('src=test_images/tmp_qis_uploadfile.jpg&amp;format=jpg', rv.data)
        finally:
            # Remove the test files and data
            os.remove(dst_file)
            delete_file('test_images/tmp_qis_uploadfile.jpg')
            db_img = dm.get_image(src='test_images/tmp_qis_uploadfile.jpg')
            if db_img:
                dm.delete_image(db_img, True)

    # File upload complete page, no uploads
    def test_file_upload_complete_page_blank(self):
        cm.clear()
        self.call_page_requiring_login(
            '/uploadcomplete/',
            False,
            'You don\'t seem to have uploaded any images recently.'
        )

    # Browse index page
    def test_browse_index_page(self):
        self.call_page_requiring_login(
            '/list/',
            False,
            'Listing of /'
        )

    # Browse folder page
    def test_browse_folder_page(self):
        self.call_page_requiring_login(
            '/list/?path=/test_images',
            False,
            'blue bells.jpg'
        )

    # Browse folder page, non-existent should still be OK
    def test_browse_folder_page_non_exist(self):
        self.call_page_requiring_login(
            '/list/?path=/test_images/qwerty',
            False,
            'Sorry, this folder does not exist.'
        )

    # #2475 Browse folder page, error reading directory should still be OK
    #       (OK as in returning a nice error rather than the HTTP 500 it used to)
    def test_browse_folder_page_bad_folder(self):
        self.call_page_requiring_login(
            '/list/?path=/test_images\x00uh oh',
            False,
            'must be encoded string without NULL bytes'
        )

    # Image detail page
    def test_image_detail_page(self):
        self.call_page_requiring_login(
            '/details/?src=/test_images/blue bells.jpg',
            False,
            '/test_images/blue bells.jpg'
        )

    # Image detail page, non-existent should still be OK
    def test_image_detail_page_non_exist(self):
        self.call_page_requiring_login(
            '/details/?src=/test_images/qwerty.jpg',
            False,
            'This file does not exist.'
        )

    # Image detail page - go backwards
    def test_image_detail_navigate_back(self):
        rv = self.call_page_requiring_login(
            '/list/navigate/?src=/test_images/blue bells.jpg&dir=back',
            required_status=302
        )
        self.assertIn('bear.jpg', rv.data)

    # Image detail page - go forwards
    def test_image_detail_navigate_forward(self):
        rv = self.call_page_requiring_login(
            '/list/navigate/?src=/test_images/blue bells.jpg&dir=fwd',
            required_status=302
        )
        self.assertIn('book-ecirgb.jpg', rv.data)

    # Image detail page - go backwards from first image
    def test_image_detail_navigate_back_first(self):
        self.call_page_requiring_login(
            '/list/navigate/?src=/test_images/bear.jpg&dir=back',
            required_status=204
        )

    # Image detail page - navigate from non-existent file path
    def test_image_detail_navigate_missing(self):
        self.call_page_requiring_login(
            '/list/navigate/?src=/test_images/MISSING FILE&dir=back',
            required_status=204
        )

    # Image detail page - ensure navigation ignores folders
    def test_image_detail_navigate_ignore_folders(self):
        test_folder = '/test_images/blue images'
        try:
            # Create a dir that (alphabetically) follows the test image name
            make_dirs(test_folder)
            rv = self.call_page_requiring_login(
                '/list/navigate/?src=/test_images/blue bells.jpg&dir=fwd',
                required_status=302
            )
            # We should get a redirect to the next file not the folder
            self.assertIn('book-ecirgb.jpg', rv.data)
        finally:
            delete_dir(test_folder)

    # Image publish page
    def test_image_publish_page(self):
        self.call_page_requiring_login(
            '/publish/?src=/test_images/blue bells.jpg',
            False
        )

    # Test page accesses requiring system permissions
    def test_system_permission_pages(self):
        def test_pages(expect_code):
            rv = self.app.get('/reports/top10/')
            self.assertEqual(rv.status_code, expect_code)
            rv = self.app.get('/reports/systemstats/')
            self.assertEqual(rv.status_code, expect_code)
            rv = self.app.get('/admin/users/')
            self.assertEqual(rv.status_code, expect_code)
            rv = self.app.get('/admin/users/1/')
            self.assertEqual(rv.status_code, expect_code)
            rv = self.app.get('/admin/groups/')
            self.assertEqual(rv.status_code, expect_code)
            rv = self.app.get('/admin/groups/1/')
            self.assertEqual(rv.status_code, expect_code)
            rv = self.app.get('/admin/templates/')
            self.assertEqual(rv.status_code, expect_code)
            rv = self.app.get('/admin/templates/1/')
            self.assertEqual(rv.status_code, expect_code)
        # Not logged in
        test_pages(302)
        rv = self.app.get('/account/')
        self.assertEqual(rv.status_code, 302)
        # Logged in, no access
        self.login('webuser', 'webuser')
        test_pages(403)
        # But allow access to edit own account
        rv = self.app.get('/account/')
        self.assertEqual(rv.status_code, 200)
        # Logged in, with access
        self.login('admin', 'admin')
        test_pages(200)
        rv = self.app.get('/account/')
        self.assertEqual(rv.status_code, 200)

    # Test the template admin pages
    def test_template_admin_page(self):
        # test_system_permission_pages() already tests that the pages work
        # so here we test that non-super users cannot edit templates
        setup_user_account('lister', 'admin_files')
        self.login('lister', 'lister')
        rv = self.app.get('/admin/templates/')
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn('delete', rv.data)
        rv = self.app.get('/admin/templates/1/')
        self.assertEqual(rv.status_code, 200)
        self.assertIn('''id="submit" disabled="disabled"''', rv.data)
        self.login('admin', 'admin')
        rv = self.app.get('/admin/templates/')
        self.assertEqual(rv.status_code, 200)
        self.assertIn('delete', rv.data)
        rv = self.app.get('/admin/templates/1/')
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn('''id="submit" disabled="disabled"''', rv.data)

    # Test that the markdown rendering is working
    def test_markdown_support(self):
        self.call_page_requiring_login(
            '/api/help/',
            False,
            'JSON is language independent'
        )

    # Test that the markdown substitutions are working
    def test_markdown_subs(self):
        # API help - it's "url: 'http://images.example.com/api/v1/list'" in the Markdown
        self.call_page_requiring_login(
            '/api/help/',
            False,
            "url: 'http://localhost/api/v1/list'"
        )
        # Image help
        self.login('webuser', 'webuser')
        rv = self.app.get('/help/')
        self.assertEqual(rv.status_code, 200)
        # Image help - subs //images.example.com/
        self.assertNotIn('//images.example.com/', rv.data)
        self.assertIn('//localhost/', rv.data)
        # Image help - subs buildings
        self.assertNotIn('buildings', rv.data)
        self.assertIn('test_images', rv.data)
        # Image help - subs quru.png
        self.assertNotIn('quru.png', rv.data)
        self.assertIn('quru110.png', rv.data)
        # Image help - subs quru-padded.png
        self.assertNotIn('quru-padded.png', rv.data)
        self.assertIn('quru470.png', rv.data)
        # Image help - subs logos
        self.assertNotIn('logos', rv.data)
        self.assertIn('test_images', rv.data)
        # Image help - subs the server-specific settings placeholder text
        self.assertNotIn('View this page from within QIS to see the default '
                         'image settings for your server.', rv.data)
        self.assertIn('The following settings are active on your server.', rv.data)

    # The simple viewer help + demo
    def test_simple_viewer_page(self):
        self.call_page_requiring_login('/simpleview/')

    def test_simple_viewer_page_help(self):
        self.call_page_requiring_login('/simpleview/help/', required_text='A demo page is')

    # The canvas viewer help + demo
    def test_canvas_viewer_page(self):
        self.call_page_requiring_login('/canvasview/')

    def test_canvas_viewer_page_help(self):
        self.call_page_requiring_login('/canvasview/help/', required_text='A demo page is')

    # The gallery viewer help + demo
    def test_gallery_viewer_page(self):
        self.call_page_requiring_login('/gallery/')

    def test_gallery_viewer_page_help(self):
        self.call_page_requiring_login('/gallery/help/', required_text='A demo page is')

    # The slideshow viewer help + demo
    def test_slideshow_viewer_page(self):
        self.call_page_requiring_login('/slideshow/')

    def test_slideshow_viewer_page_help(self):
        self.call_page_requiring_login('/slideshow/help/', required_text='A demo page is')
