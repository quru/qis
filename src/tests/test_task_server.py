# -*- coding: utf-8 -*-
#
# Quru Image Server
#
# Document:      test_task_server.py
# Date started:  05 Feb 2015
# By:            Matt Fozard
# Purpose:       Tests the background tasks
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

from datetime import datetime, timedelta
import time

import tests.tests as main_tests

from imageserver.flask_app import data_engine as dm
from imageserver.flask_app import task_engine as tm
from imageserver.models import SystemStats, Task


class TaskServerTests(main_tests.FlaskTestCase):
    @classmethod
    def setUpClass(cls):
        super(TaskServerTests, cls).setUpClass()
        main_tests.init_tests()

    def test_task_server(self):
        # Create some stats
        t_now = datetime.utcnow()
        dm.save_object(SystemStats(
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, t_now - timedelta(minutes=5), t_now
        ))
        # We should now have stats
        sys_stats = dm.search_system_stats(t_now - timedelta(minutes=60), t_now)
        self.assertGreater(len(sys_stats), 0)
        # Check current task list entries
        tasks = dm.list_objects(Task, order_field=Task.id)
        task_list_len = len(tasks)
        # Post a background task to purge the stats
        KEEP_SECS = 10
        task_obj = tm.add_task(
            None,
            'Purge system statistics',
            'purge_system_stats',
            {'before_time': t_now},
            Task.PRIORITY_NORMAL,
            'info', 'error',
            KEEP_SECS
        )
        self.assertIsNotNone(task_obj)
        # Check it really got added
        tasks = dm.list_objects(Task, order_field=Task.id)
        self.assertEqual(len(tasks), task_list_len + 1)
        task_list_len = len(tasks)
        # Post it again, make sure there is no dupe added
        dupe_task_obj = tm.add_task(
            None,
            'Purge system statistics',
            'purge_system_stats',
            {'before_time': t_now},
            Task.PRIORITY_NORMAL,
            'info', 'error',
            KEEP_SECS
        )
        self.assertIsNone(dupe_task_obj)
        # Check it really didn't get re-added
        tasks = dm.list_objects(Task, order_field=Task.id)
        self.assertEqual(len(tasks), task_list_len)
        task = tasks[-1]
        self.assertEqual(task.id, task_obj.id)
        # Wait for task completion
        tm.wait_for_task(task_obj.id, 10)
        # We should now have no stats
        t_now = datetime.utcnow()
        sys_stats = dm.search_system_stats(t_now - timedelta(minutes=60), t_now)
        self.assertEqual(len(sys_stats), 0)
        # The completed task should only be removed after the delay we specified
        task = dm.get_object(Task, task_obj.id)
        self.assertIsNotNone(task)
        self.assertEqual(task.status, Task.STATUS_COMPLETE)
        # Wait for keep time + task server's poll time
        time.sleep(KEEP_SECS + 10)
        # Should now be gone
        task = dm.get_object(Task, task_obj.id)
        self.assertIsNone(task)

    # v1.23 Tasks can now store a result - None, object, or Exception
    def test_task_result_none(self):
        # Test no return value
        task_obj = tm.add_task(
            None, 'Test return values', 'test_result_task',
            {'raise_exception': False, 'return_value': None},
            Task.PRIORITY_NORMAL, 'info', 'error', 5
        )
        self.assertIsNotNone(task_obj)
        tm.wait_for_task(task_obj.id, 10)
        task_obj = tm.get_task(task_obj.id, decode_attrs=True)
        self.assertIsNone(task_obj.result)
        dm.delete_object(task_obj)

    # v1.23 Tasks can now store a result - None, object, or Exception
    def test_task_result_object(self):
        # Test normal return value
        task_obj = tm.add_task(
            None, 'Test return values', 'test_result_task',
            {'raise_exception': False, 'return_value': {'my_bool': True}},
            Task.PRIORITY_NORMAL, 'info', 'error', 5
        )
        self.assertIsNotNone(task_obj)
        tm.wait_for_task(task_obj.id, 10)
        task_obj = tm.get_task(task_obj.id, decode_attrs=True)
        self.assertEqual(task_obj.result, {'my_bool': True})
        dm.delete_object(task_obj)

    # v1.23 Tasks can now store a result - None, object, or Exception
    def test_task_result_exception(self):
        # Test exception raised
        task_obj = tm.add_task(
            None, 'Test return values', 'test_result_task',
            {'raise_exception': True, 'return_value': None},
            Task.PRIORITY_NORMAL, 'info', 'error', 5
        )
        self.assertIsNotNone(task_obj)
        tm.wait_for_task(task_obj.id, 10)
        task_obj = tm.get_task(task_obj.id, decode_attrs=True)
        self.assertIsInstance(task_obj.result, ValueError)
        self.assertEqual(repr(task_obj.result), repr(ValueError('An error happened')))
        dm.delete_object(task_obj)

    # Tests that new tasks can be cancelled
    def test_task_cancel(self):
        task_obj = tm.add_task(
            None, 'Test task cancelling', 'test_result_task',
            {'raise_exception': False, 'return_value': None},
            Task.PRIORITY_LOW, 'info', 'error', 0
        )
        self.assertIsNotNone(task_obj)
        self.assertGreater(task_obj.id, 0)
        # Yes, this could be a fragile test if the task server gets to it first
        # It has worked the first 5 times in a row I've tried it, so fingers crossed
        self.assertTrue(tm.cancel_task(task_obj))
        task_obj = tm.get_task(task_obj.id)
        self.assertIsNone(task_obj)
