#
# Quru Image Server
#
# Document:      task_manager.py
# Date started:  13 Dec 2012
# By:            Matt Fozard
# Purpose:       Provides background task management
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
# 04Jan2013  Matt  Move run_server to a static method, do not call from client constructor
# 27Feb2013  Matt  Add background housekeeping thread to perform routine tasks
#

import pickle
import time
from datetime import datetime, timedelta
from threading import Thread

import imageserver.auxiliary.task_server as task_server
from .errors import AlreadyExistsError, DBError, TimeoutError
from .models import Task
from .util import this_is_computer


class TaskManager(object):
    """
    Manages background task processing for the application.

    Provides the ability to launch a task-running server process,
    and a set of client functions that can be called to run tasks.
    """
    def __init__(self, data_manager, logger):
        """
        Initialises a background task posting client.

        data_manager - a database manager instance
        logger       - a logger for client messages
        """
        self._logger = logger
        self._data = data_manager
        self._hk_thread = None
        self._hk_running = False

    def add_task(self, user, name, function, params_dict=None,
                 priority=Task.PRIORITY_NORMAL,
                 log_level=None, error_log_level=None, keep_secs=0):
        """
        Posts a new task to be processed in the background.
        The combination of function name + parameters is unique in the task queue,
        whether the task is pending, in progress, or (for keep_secs seconds) complete.

        user - An optional owner of the task, or None for system tasks.
        name - A description of the task.
        function - The name of the Python function to run, which must exist in tasks.py
        params_dict - A dictionary of parameters for the function
        priority - A Task.PRIORITY value
        log_level - A value to use for logging the start and end of the task.
                    One from: 'debug', 'info', 'warn', 'error', or None for no logging.
        error_log_level - As for log_level, the value to use for logging any
                          exceptions raised by the task.
        keep_secs - The number of seconds to keep the task record after completion,
                    in order to prevent an identical task running again.

        Returns the new Task object on success,
        or None if the same task already exists in the task queue.
        """
        db_session = self._data.db_get_session()
        try:
            if params_dict is None:
                params_dict = {}
            params_data = pickle.dumps(params_dict, protocol=pickle.HIGHEST_PROTOCOL)

            log_str = log_level if log_level else ''
            err_log_str = error_log_level if error_log_level else ''

            # Enforce task name limit
            if len(name) > 100:
                name = name[:97] + '...'

            # Need a "clean" user object
            db_user = self._data.get_user(user.id, _db_session=db_session) if user else None

            task = Task(
                db_user, name, function, params_data, priority,
                log_str, err_log_str, keep_secs
            )
            task = self._data.save_object(
                task, refresh=True, _db_session=db_session, _commit=True
            )
            return task
        except DBError as e:
            self._logger.error('Error adding task %s to queue: %s' % (name, str(e)))
            db_session.rollback()
            return None
        except AlreadyExistsError:
            db_session.rollback()
            return None
        finally:
            db_session.close()

    def get_task(self, task_id, decode_attrs=False, _db_session=None):
        """
        Returns the Task object matching the requested ID, or None if
        the task record no longer exists (meaning the task has completed
        and been removed, if the ID was previously valid).

        The 'params' and 'result' attributes are encoded by default.
        If you request these to be decoded, do not re-attach the object
        to a database session (without re-encoding them first).
        """
        t = self._data.get_object(Task, task_id, _db_session=_db_session)
        if t:
            if decode_attrs:
                if _db_session is not None:
                    # Don't re-save the task object when db session is closed
                    _db_session.expunge(t)
                t.params = pickle.loads(t.params)
                if t.result is not None:
                    t.result = pickle.loads(t.result)
        return t

    def get_task_status(self, task_id, _db_session=None):
        """
        Returns the current Task.STATUS value for a task,
        assumed to be complete if the task no longer exists.
        """
        t = self.get_task(task_id, False, _db_session)
        return t.status if t else Task.STATUS_COMPLETE

    def wait_for_task(self, task_id, timeout_seconds=0, _db_session=None):
        """
        Waits for a task to complete or until a timeout occurs.
        Returns the completed task object (with decoded 'params' and 'result'
        attributes) or raises a TimeoutError. Returns None if the requested
        task is no longer present in the database.
        """
        db_session = _db_session or self._data.db_get_session()
        try:
            timeout_time = time.time() + timeout_seconds
            t = self.get_task(task_id, False, _db_session=db_session)
            while t and t.status != Task.STATUS_COMPLETE:
                if time.time() >= timeout_time:
                    raise TimeoutError()
                try:
                    time.sleep(1)
                    db_session.refresh(t, ('status', 'result'))
                except:
                    t = None
            if t is not None:
                # Return the task with result decoded
                return self.get_task(task_id, True, _db_session=db_session)
            return None
        finally:
            if not _db_session:
                db_session.close()

    def init_housekeeping_tasks(self):
        """
        Creates a background thread to run housekeeping tasks.
        Note the implications of this in a mod_wsgi / web server environment:

        * Multiple web workers may each spawn a housekeeping thread.
          Task creation should be careful not to allow duplicate/overlapping tasks.
        * The web workers may be recycled at any time.
          Sudden shutdown of the housekeeping thread must not cause problems.
        """
        if self._hk_thread is None:
            self._hk_running = True
            self._hk_thread = Thread(target=self._housekeeping, name='Housekeeping')
            self._hk_thread.daemon = True
            self._hk_thread.start()

    def stop_housekeeping_tasks(self):
        """
        Stops the background housekeeping tasks.
        """
        self._hk_running = False

    def _housekeeping(self):
        """
        Launches periodic background housekeeping tasks as required.
        """
        self._logger.info('Housekeeping task scheduler started')

        tasks = [{
            'name': 'Delete old temporary files',
            'function': 'delete_old_temp_files',
            'priority': Task.PRIORITY_NORMAL,
            'interval_hours': 24,
            'last_run': None,
            'logging': ('info', 'error')
        }]
        while (self._hk_running):
            time.sleep(60)
            if self._hk_running:
                for task in tasks:
                    min_ran_time = datetime.utcnow() - timedelta(hours=task['interval_hours'])
                    if task['last_run'] is None or task['last_run'] < min_ran_time:
                        self.add_task(
                            None,
                            task['name'],
                            task['function'],
                            None,
                            task['priority'],
                            task['logging'][0],
                            task['logging'][1],
                            # Keep for interval - 10 mins
                            max((task['interval_hours'] * 60 * 60) - 600, 0)
                        )
                        task['last_run'] = datetime.utcnow()

        self._logger.info('Housekeeping task scheduler stopped')

    @staticmethod
    def run_server(server_host, server_port, debug_mode):
        """
        Launches a task server if the server_host (as a host name or IP
        address) evaluates to this server. Returns without action if the
        server_host appears to refer to a different server, or if a server
        process is already running.

        server_host - the name or IP address of the task server
        server_port - the port number that the task server will listen on
        debug_mode  - whether to run the task server in debug mode
        """
        if server_host and (server_port > 0) and this_is_computer(server_host):
            task_server.run_server_process(debug_mode)
