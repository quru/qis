#
# Quru Image Server
#
# Document:      task_server.py
# Date started:  18 Dec 2012
# By:            Matt Fozard
# Purpose:       Background tasks server
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

import pickle
import errno
import os
import signal
import sys
import time
import threading
import traceback
from datetime import datetime, timedelta
from socket import socket
from threading import Event

from flask import current_app as app

from imageserver.auxiliary import util
from imageserver.models import Task
import imageserver.tasks as tasks


def run_task(thread_id, task, logger, data_engine, debug_mode):
    """
    Performs the given task.
    """
    try:
        # Default task-level logging
        task_log = logger.debug
        task_error_log = logger.error

        # Use task settings for task-level logging
        if hasattr(logger, task.log_level):
            task_log = getattr(logger, task.log_level)
        if hasattr(logger, task.error_log_level):
            task_error_log = getattr(logger, task.error_log_level)

        task_log('Task \'%s\' starting on thread %d' % (task.name, thread_id))

        # Decode function parameters
        params_dict = pickle.loads(task.params) if task.params else None
        if params_dict is None:
            params_dict = dict()
        # Give the function access to its own task record
        params_dict['_task'] = task

        # Get function from tasks.py
        task_fn = getattr(tasks, task.funcname, None)
        if not task_fn:
            logger.error('Task function ' + task.funcname + ' is not defined')
        else:
            # Run task
            task.result = task_fn(**params_dict)
            task_log('Task \'%s\' completed' % task.name)

    except Exception as e:
        # Store the exception as the task result
        task.result = e
        task_error_log(
            'Task ID %d \'%s\' failed with error: %s' % (task.id, task.name, str(e))
        )
        if debug_mode:
            traceback.print_exc()
    finally:
        try:
            # Always mark the task as finished
            task.result = pickle.dumps(task.result, protocol=pickle.HIGHEST_PROTOCOL)
            data_engine.complete_task(task)
        except Exception as e:
            logger.error('Failed to set as complete task %d \'%s\': %s' % (
                task.id, task.name, str(e)
            ))


def _run_server(debug_mode):
    """
    The task serving main function.
    This function does not return until the process is killed.
    """
    BUSY_WAIT = 2       #
    IDLE_WAIT = 5       # All in seconds
    CLEANUP_EVERY = 10  #

    proc_mutex = None
    try:
        num_threads = app.config['TASK_SERVER_THREADS']
        if num_threads < 1:
            raise ValueError('TASK_SERVER_THREADS must have a value of 1 or more')

        # Hold open a port. Without messing around with lock files
        # (and where to put them, and how to lock them), this appears to be the
        # only easy cross platform way of emulating Windows' named global mutex.
        proc_mutex = socket()
        proc_mutex.bind((app.config['TASK_SERVER'], app.config['TASK_SERVER_PORT']))

        # If here, we opened the port so we're the only task server running locally
        shutdown_ev = Event()
        logger = app.log
        data_engine = app.data_engine
        logger.reconnect('tasks_' + str(os.getpid()))
        logger.info('Task server running')

        # Get the previous and the new process ID
        last_proc_id = util.get_pid('tasks')
        proc_id = str(os.getpid())
        util.store_pid('tasks', proc_id)

        # Close nicely
        def _shutdown_hook(signum, frame):
            logger.info('Shutdown signal received')
            shutdown_ev.set()
        signal.signal(signal.SIGTERM, _shutdown_hook)

        # Use a shutdown-friendly sleep function (whole seconds only)
        def _sleep(secs):
            for _ in range(secs):
                if shutdown_ev.is_set():
                    break
                time.sleep(1)

        # In case this is a clean restart, wait a while for the other services
        # (logging, stats, ORM, etc) to start up first.
        _sleep(IDLE_WAIT)

        # Recover any tasks that weren't completed when we last exited
        if not shutdown_ev.is_set() and last_proc_id:
            data_engine.delete_completed_tasks()
            peek_tasks = data_engine.list_objects(Task, order_field=Task.id)
            for t in peek_tasks:
                if (
                    t.lock_id and
                    t.lock_id.startswith(last_proc_id + '_') and
                    t.status == Task.STATUS_ACTIVE
                ):
                    logger.warning('Resetting interrupted task ID %d \'%s\'' % (t.id, t.name))
                    t.status = Task.STATUS_PENDING
                    t.lock_id = None
                    data_engine.save_object(t)

        # Main task dispatching loop
        threads = []
        next_thread_id = 1
        last_cleanup = datetime.utcnow()
        while not shutdown_ev.is_set():
            # Check for completed threads
            threads[:] = [t for t in threads if t.is_alive()]

            # If we have capacity
            if len(threads) < num_threads:
                pending_tasks = data_engine.get_pending_tasks(num_threads - len(threads))
                # Launch each task
                for task in pending_tasks:
                    if shutdown_ev.is_set():
                        break

                    thread_id = next_thread_id
                    lock_id = str(proc_id) + '_' + str(thread_id)
                    # Lock it to our process
                    locked = data_engine.lock_task(task, lock_id)
                    if not locked:
                        logger.warning('Failed to lock task ID %d \'%s\'' % (
                            task.id, task.name)
                        )
                    else:
                        logger.debug('Launching task ID %d \'%s\' as thread %d' % (
                                task.id, task.name, thread_id)
                        )
                        # Go
                        t = threading.Thread(
                            target=run_task,
                            name='task_thread_%d' % thread_id,
                            args=(thread_id, task, logger, data_engine, debug_mode)
                        )
                        t.daemon = False
                        threads.append(t)
                        t.start()

                    # Inc thread counter
                    next_thread_id += 1
                    if next_thread_id > 999999:
                        next_thread_id = 1

            # Wait a while
            _sleep(BUSY_WAIT if len(threads) > 0 else IDLE_WAIT)

            # Periodically run cleanup
            if not shutdown_ev.is_set():
                if datetime.utcnow() - last_cleanup > timedelta(seconds=CLEANUP_EVERY):
                    data_engine.delete_completed_tasks()
                    last_cleanup = datetime.utcnow()

        # Shutdown
        if threads:
            logger.info('Task server shutdown, waiting on %d task(s)' % len(threads))
            for t in threads:
                t.join()
        logger.info('Task server exited')

        print('Task server shutdown')
    except IOError as e:
        if e.errno == errno.EADDRINUSE:
            print("A task server is already running.")
        else:
            print("Task server exited: " + str(e))
    except BaseException as e:
        if (len(e.args) > 0 and e.args[0] == errno.EINTR) or not str(e):
            print("Task server exited")
        else:
            print("Task server exited: " + str(e))
    finally:
        if proc_mutex:
            proc_mutex.close()
    sys.exit()


def run_server_process(debug_mode):
    """
    Starts a task server as a separate process. The database connection and
    other settings are loaded from the imageserver settings module.
    If a task server is already running, the server process simply exits.
    """
    util.double_fork('task_server', _run_server, (debug_mode, ))


# Allow the server to be run from the command line
if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Use: task_server <debug mode>\n")
        print("E.g. export PYTHONPATH=.")
        print("     python imageserver/auxiliary/task_server.py false\n")
    else:
        from imageserver.flask_app import app as init_app
        with init_app.app_context():
            run_server_process(sys.argv[1].lower() == 'true')
