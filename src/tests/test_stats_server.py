# -*- coding: utf-8 -*-
#
# Quru Image Server
#
# Document:      test_stats_server.py
# Date started:  23 Aug 2013
# By:            Alex Stapleton
# Purpose:       Tests the stats recording
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

from __future__ import absolute_import

from collections import defaultdict
from cStringIO import StringIO
from datetime import datetime
import time

import mock
import tests.tests as main_tests

from imageserver.auxiliary import stats_server
from imageserver.counter import Counter
from imageserver.filesystem_manager import copy_file, delete_file
from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import stats_engine as sm
from imageserver.stats_manager import StatsManager

from tests import kill_aux_processes


class StringIOConnection(object):
    def __init__(self, value=None):
        self.buf = StringIO(value) if value else StringIO()
        self.buf.seek(0)

    def recv(self, n, flags=None):
        return self.buf.read(n)

    def send(self, data):
        self.buf.write(data)

    def value(self):
        return self.buf.getvalue()

    def makefile(self, *args, **kwargs):
        return self.buf


class StatsHandlerTests(main_tests.FlaskTestCase):
    # Returns a mocked server side "request" object
    def _mock_stats_request(self, data):
        return StringIOConnection(data)

    # Returns a mocked stats_server StatsSocketServer
    def _mock_stats_server(self):
        server = mock.MagicMock()
        server.shutdown_ev.is_set.return_value = False
        server.sys_cache = Counter()
        server.img_cache = defaultdict(Counter)
        return server

    # Uses the stats_server StatsRequestHandler to process a data packet from the client
    def _mock_server_call(self, client_data):
        request = self._mock_stats_request(client_data)
        server = self._mock_stats_server()
        stats_server.StatsRequestHandler(
            request, None, server
        )
        return server

    @mock.patch('imageserver.stats_manager.StatsManager._client_connect')
    def test_make_request(self, mock_connect):
        sc = StatsManager(None, 'Mock', 1)
        sc._sock = StringIOConnection()
        sc.log_request(7, 0.01)
        server = self._mock_server_call(sc._sock.value())
        self.assertEqual(
            server.sys_cache,
            {'requests': 1, 'request_seconds': 0.01, 'max_request_seconds': 0.01}
        )
        self.assertEqual(
            server.img_cache.get(7),
            {'requests': 1, 'request_seconds': 0.01, 'max_request_seconds': 0.01}
        )

    @mock.patch('imageserver.stats_manager.StatsManager._client_connect')
    def test_make_request_nostats(self, mock_connect):
        sc = StatsManager(None, 'Mock', 1)
        sc._sock = StringIOConnection()
        sc.log_request(7, 0.01, False)
        server = self._mock_server_call(sc._sock.value())
        self.assertEqual(
            server.sys_cache,
            {'requests': 1, 'request_seconds': 0.01, 'max_request_seconds': 0.01}
        )
        self.assertEqual(
            server.img_cache.get(7),
            {'requests': 1}
        )

    @mock.patch('imageserver.stats_manager.StatsManager._client_connect')
    def test_make_view(self, mock_connect):
        sc = StatsManager(None, 'Mock', 1)
        sc._sock = StringIOConnection()
        sc.log_view(7, 1024, False, 0.22)
        server = self._mock_server_call(sc._sock.value())
        self.assertEqual(
            server.sys_cache,
            {'requests': 1, 'views': 1, 'cached_views': 0, 'bytes': 1024,
             'request_seconds': 0.22, 'max_request_seconds': 0.22}
        )
        self.assertEqual(
            server.img_cache.get(7),
            {'requests': 1, 'views': 1, 'cached_views': 0, 'bytes': 1024,
             'request_seconds': 0.22, 'max_request_seconds': 0.22}
        )

    @mock.patch('imageserver.stats_manager.StatsManager._client_connect')
    def test_make_view_nostats(self, mock_connect):
        sc = StatsManager(None, 'Mock', 1)
        sc._sock = StringIOConnection()
        sc.log_view(7, 1024, False, 0.22, False)
        server = self._mock_server_call(sc._sock.value())
        self.assertEqual(
            server.sys_cache,
            {'requests': 1, 'views': 1, 'cached_views': 0, 'bytes': 1024,
             'request_seconds': 0.22, 'max_request_seconds': 0.22}
        )
        self.assertEqual(
            server.img_cache.get(7),
            {'requests': 1}
        )

    @mock.patch('imageserver.stats_manager.StatsManager._client_connect')
    def test_make_cached_view(self, mock_connect):
        sc = StatsManager(None, 'Mock', 1)
        sc._sock = StringIOConnection()
        sc.log_view(7, 1024, True, 0.02)
        server = self._mock_server_call(sc._sock.value())
        self.assertEqual(
            server.sys_cache,
            {'requests': 1, 'views': 1, 'cached_views': 1, 'bytes': 1024,
             'request_seconds': 0.02, 'max_request_seconds': 0.02}
        )
        self.assertEqual(
            server.img_cache.get(7),
            {'requests': 1, 'views': 1, 'cached_views': 1, 'bytes': 1024,
             'request_seconds': 0.02, 'max_request_seconds': 0.02}
        )

    @mock.patch('imageserver.stats_manager.StatsManager._client_connect')
    def test_make_download(self, mock_connect):
        sc = StatsManager(None, 'Mock', 1)
        sc._sock = StringIOConnection()
        sc.log_download(7, 1024, 1)
        server = self._mock_server_call(sc._sock.value())
        self.assertEqual(
            server.sys_cache,
            {'requests': 1, 'downloads': 1, 'bytes': 1024,
             'request_seconds': 1, 'max_request_seconds': 1}
        )
        self.assertEqual(
            server.img_cache.get(7),
            {'requests': 1, 'downloads': 1, 'bytes': 1024,
             'request_seconds': 1, 'max_request_seconds': 1}
        )

    @mock.patch('imageserver.stats_manager.StatsManager._client_connect')
    def test_make_download_nostats(self, mock_connect):
        sc = StatsManager(None, 'Mock', 1)
        sc._sock = StringIOConnection()
        sc.log_download(7, 1024, 1, False)
        server = self._mock_server_call(sc._sock.value())
        self.assertEqual(
            server.sys_cache,
            {'requests': 1, 'downloads': 1, 'bytes': 1024,
             'request_seconds': 1, 'max_request_seconds': 1}
        )
        self.assertEqual(
            server.img_cache.get(7),
            {'requests': 1}
        )


class StatsServerTests(main_tests.FlaskTestCase):
    @classmethod
    def setUpClass(cls):
        super(StatsServerTests, cls).setUpClass()
        # Kill stats collection from earlier tests
        kill_aux_processes(nicely=False)
        # Wipe the database, restart stats collection
        main_tests.init_tests()
        # Reset the connection to the stats server
        sm._client_close()
        sm._client_connect()

    def test_stats_engine(self):
        # Test constants
        IMG = 'test_images/cathedral.jpg'
        IMG_COPY = 'test_images/stats_test_image.jpg'
        IMG_LEN = 648496  # knowing length requires 'keep original' values in settings
        IMG_VIEWS = 5
        IMG_VIEWS_NOSTATS = 3
        IMG_VIEWS_304 = 8
        IMG_VIEWS_COPY = 1
        IMG_DOWNLOADS = 1
        try:
            t_then = datetime.utcnow()
            copy_file(IMG, IMG_COPY)
            # View some images
            for _ in range(IMG_VIEWS):
                rv = self.app.get('/image?src='+IMG)
                self.assertEqual(rv.status_code, 200)
                self.assertEqual(len(rv.data), IMG_LEN)
            for _ in range(IMG_DOWNLOADS):
                rv = self.app.get('/original?src='+IMG)
                self.assertEqual(rv.status_code, 200)
                self.assertEqual(len(rv.data), IMG_LEN)
            # View some also without stats.
            # They should still be counted in the system stats but not the image stats.
            for _ in range(IMG_VIEWS_NOSTATS):
                rv = self.app.get('/image?src='+IMG+'&stats=0')
                self.assertEqual(rv.status_code, 200)
                self.assertEqual(len(rv.data), IMG_LEN)
                etag = rv.headers['ETag']
            # View some that only elicit the 304 Not Modified response
            for _ in range(IMG_VIEWS_304):
                rv = self.app.get('/image?src='+IMG, headers={'If-None-Match': etag})
                self.assertEqual(rv.status_code, 304)
            # View an image that we'll delete next
            for _ in range(IMG_VIEWS_COPY):
                rv = self.app.get('/image?src='+IMG_COPY)
                self.assertEqual(len(rv.data), IMG_LEN)
            # Get test image db record
            db_image = dm.get_image(src=IMG)
            self.assertIsNotNone(db_image)
            # Deleting the copied image should mean its views are counted in the system stats
            # but are not included in the image stats (because the image record is gone)
            delete_file(IMG_COPY)
            dm.delete_image(dm.get_image(src=IMG_COPY), purge=True)
            db_image_copy = dm.get_image(src=IMG_COPY)
            self.assertIsNone(db_image_copy)
            # Wait for new stats to flush
            time.sleep(65)
            # See if the system stats line up with the views
            t_now = datetime.utcnow()
            lres = dm.search_system_stats(t_then, t_now)
            self.assertEqual(len(lres), 1)
            res = lres[0]
            self.assertEqual(res.requests, IMG_VIEWS + IMG_VIEWS_COPY + IMG_DOWNLOADS + IMG_VIEWS_NOSTATS + IMG_VIEWS_304)
            self.assertEqual(res.views, IMG_VIEWS + IMG_VIEWS_COPY + IMG_VIEWS_NOSTATS)
            self.assertEqual(res.cached_views, IMG_VIEWS + IMG_VIEWS_NOSTATS - 1)
            self.assertEqual(res.downloads, IMG_DOWNLOADS)
            self.assertEqual(res.total_bytes, (IMG_VIEWS + IMG_VIEWS_COPY + IMG_DOWNLOADS + IMG_VIEWS_NOSTATS) * IMG_LEN)
            self.assertGreater(res.request_seconds, 0)
            self.assertGreater(res.max_request_seconds, 0)
            self.assertLess(res.max_request_seconds, res.request_seconds)
            self.assertGreater(res.cpu_pc, 0)
            self.assertGreater(res.memory_pc, 0)
            # See if the image stats line up with the views
            lres = dm.search_image_stats(t_then, t_now, db_image.id)
            self.assertEqual(len(lres), 1)
            res = lres[0]
            self.assertEqual(res.requests, IMG_VIEWS + IMG_DOWNLOADS + IMG_VIEWS_NOSTATS + IMG_VIEWS_304)
            self.assertEqual(res.views, IMG_VIEWS)
            self.assertEqual(res.cached_views, IMG_VIEWS - 1)
            self.assertEqual(res.downloads, IMG_DOWNLOADS)
            self.assertEqual(res.total_bytes, (IMG_VIEWS + IMG_DOWNLOADS) * IMG_LEN)
            self.assertGreater(res.request_seconds, 0)
            self.assertGreater(res.max_request_seconds, 0)
            self.assertLess(res.max_request_seconds, res.request_seconds)
            # And the summary (reporting) data too
            lsummary = dm.summarise_image_stats(t_then, t_now)
            # lsummary [(image_id, sum_requests, sum_views, sum_cached_views,
            #           sum_downloads, sum_bytes_served, sum_seconds, max_seconds)]
            self.assertEqual(len(lsummary), 1)
            res = lsummary[0]
            self.assertEqual(res[0], db_image.id)
            self.assertEqual(res[1], IMG_VIEWS + IMG_DOWNLOADS + IMG_VIEWS_NOSTATS + IMG_VIEWS_304)
            self.assertEqual(res[2], IMG_VIEWS)
            self.assertEqual(res[3], IMG_VIEWS - 1)
            self.assertEqual(res[4], IMG_DOWNLOADS)
            self.assertEqual(res[5], (IMG_VIEWS + IMG_DOWNLOADS) * IMG_LEN)
            self.assertGreater(res[6], 0)
            self.assertGreater(res[7], 0)
            self.assertLess(res[7], res[6])
            ssummary = dm.summarise_system_stats(t_then, t_now)
            # ssummary (sum_requests, sum_views, sum_cached_views,
            #          sum_downloads, sum_bytes_served, sum_seconds, max_seconds)
            res = ssummary
            self.assertEqual(res[0], IMG_VIEWS + IMG_VIEWS_COPY + IMG_DOWNLOADS + IMG_VIEWS_NOSTATS + IMG_VIEWS_304)
            self.assertEqual(res[1], IMG_VIEWS + IMG_VIEWS_COPY + IMG_VIEWS_NOSTATS)
            self.assertEqual(res[2], IMG_VIEWS + IMG_VIEWS_NOSTATS - 1)
            self.assertEqual(res[3], IMG_DOWNLOADS)
            self.assertEqual(res[4], (IMG_VIEWS + IMG_VIEWS_COPY + IMG_DOWNLOADS + IMG_VIEWS_NOSTATS) * IMG_LEN)
            self.assertGreater(res[5], 0)
            self.assertGreater(res[6], 0)
            self.assertLess(res[6], res[5])
        finally:
            delete_file(IMG_COPY)
