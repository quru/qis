#
# Quru Image Server
#
# Document:      util.py
# Date started:  27 Mar 2018
# By:            Matt Fozard
# Purpose:       Auxiliary server utilities
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
# 27Mar2018  Matt  Code moved here from task_server, refactored other servers
#

import os
import time
from multiprocessing import Process

from flask import current_app as app

from imageserver.util import get_computer_hostname


def store_pid(proc_name, pid_val):
    """
    Writes the current process ID to a hidden file in the image server file system.
    Logs any error but does not raise it.
    """
    try:
        pid_dir = os.path.dirname(_get_pidfile_path(proc_name))
        if not os.path.exists(pid_dir):
            os.mkdir(pid_dir)
        with open(_get_pidfile_path(proc_name), 'wt', buffering=0) as f:
            f.write(pid_val)
    except Exception as e:
        app.log.error('Failed to write %s PID file: %s' % (proc_name, str(e)))


def get_pid(proc_name):
    """
    Returns the last value written by _store_pid() as a string,
    or an empty string on failure or if _store_pid() has not been called before.
    """
    try:
        if os.path.exists(_get_pidfile_path(proc_name)):
            with open(_get_pidfile_path(proc_name), 'rt') as f:
                return f.read()
    except Exception as e:
        app.log.error('Failed to read %s PID file: %s' % (proc_name, str(e)))
    return ''


def _get_pidfile_path(proc_name):
    """
    Returns a path for a PID file, incorporating the given process name and this
    computer's host name (for the case when multiple servers are sharing the same
    back-end file system).
    """
    return os.path.join(
        app.config['IMAGES_BASE_DIR'],
        '.meta',
        get_computer_hostname() + '.' + proc_name + '.pid'
    )


def double_fork(process_name, process_function, process_args):
    """
    Forks twice, leaving 'target_function' running as a separate grand-child process.
    This fully detaches the final process from the parent process, avoiding issues
    with the parent having to wait() for the child (or else becoming a zombie process)
    or the parent's controlling terminal (if it has one) being closed. This is better
    explained at: http://www.faqs.org/faqs/unix-faq/programmer/faq/
    """
    def _double_fork():
        p = Process(
            target=process_function,
            name=process_name,
            args=process_args
        )
        # Do not kill the target_function process when this process exits
        p.daemon = False
        # Start target_function as the grand-child process
        p.start()
        time.sleep(1)
        # Force the child exit, leaving the grand-child still running.
        # The parent process can now exit cleanly without waiting to wait() or join()
        # on the grand-child (and it can't, since it knows nothing about it).
        os._exit(0)

    # Start _double_fork as the child process and wait() for it to complete (is quick)
    p = Process(target=_double_fork)
    p.start()
    p.join()
