#
# Quru Image Server
#
# Document:      stats_server.py
# Date started:  31 Aug 2011
# By:            Matt Fozard
# Purpose:       Stats recording server
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
# 09Jan2012  Matt  Read settings from new settings module instead of passing in
# 03Jun2013  Matt  Add flush monitoring thread to prevent false spikes in the
#                  data when the flush process is stalled or very slow
# 09Jan2015  Matt  Add CPU and RAM recording
#


from collections import defaultdict
import errno
import json
import os
import SocketServer
import signal
import sys
from datetime import date, datetime, timedelta
from multiprocessing import Process
from threading import Event, Lock, Thread
from time import sleep

from flask import current_app as app
from sqlalchemy.exc import IntegrityError

from imageserver.counter import Counter
from imageserver.models import ImageStats, SystemStats, Task

try:
    import psutil
    _have_psutil = True
except:
    _have_psutil = False


class StatsRequestHandler(SocketServer.StreamRequestHandler):
    """
    Handler to receive stats parcels sent from the image server stats client.
    """
    def handle(self):
        """
        Handle multiple requests for as long as the connection is open.
        Each request is expected to contain the stats object in JSON format,
        terminated by a newline character.
        """
        self.server.logger.debug('Entering client stats stream handler')
        while not self.server.shutdown_ev.is_set():
            try:
                self._handle_one()
            except StopIteration:
                break
        self.server.logger.debug('Exited client stats stream handler')

    def _handle_one(self):
        data = self.rfile.readline()
        if not data:
            raise StopIteration()

        stats_dict = json.loads(data)
        for image_key, stats_obj in stats_dict.iteritems():
            image_id = int(image_key)
            self._sys_cache(stats_obj)
            if image_id:
                self._img_cache(image_id, stats_obj)

    def _sys_cache(self, stats_obj):
        with self.server.sys_cache_lock:
            sys_cache = self.server.sys_cache
            sys_cache.update(stats_obj)
            # Add/update calculated field max_request_seconds
            if 'request_seconds' in stats_obj:
                sys_cache['max_request_seconds'] = max(
                    sys_cache['max_request_seconds'],
                    stats_obj['request_seconds']
                )

    def _img_cache(self, image_key, stats_obj):
        with self.server.img_cache_lock:
            img_cache = self.server.img_cache
            istats = img_cache.get(image_key)
            if istats is None:
                istats = Counter()
                img_cache[image_key] = istats
            istats.update(stats_obj)
            # Add/update calculated field max_request_seconds
            if 'request_seconds' in stats_obj:
                istats['max_request_seconds'] = max(
                    istats['max_request_seconds'],
                    stats_obj['request_seconds']
                )


class StatsSocketServer(SocketServer.ThreadingTCPServer):
    """
    A multi-threaded TCP server for receiving and processing stats messages.

    One thread is created per client connection. The client is expected to
    keep its connection open, so that each thread is long-lived.

    Loosely based on the network logging example at
    http://docs.python.org/dev/howto/logging-cookbook.html
    """
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, debug_mode):
        SocketServer.ThreadingTCPServer.__init__(
            self,
            (app.config['STATS_SERVER'], app.config['STATS_SERVER_PORT']),
            StatsRequestHandler
        )

        self.logger = app.log
        self.logger.set_name('stats_' + str(os.getpid()))
        self.database = app.data_engine
        self.tasks = app.task_engine
        self.data_cache = app.cache_engine

        self.frequency = app.config['STATS_FREQUENCY']
        if self.frequency < 1:
            raise ValueError('STATS_FREQUENCY must have a value of 1 or more')

        self.shutdown_ev = Event()
        self.init_engine()

    def init_engine(self):
        # Initialise hardware stats and psutil
        self._reset_hardware_caches()
        self._poll_hardware()  # See psutil.cpu_percent(interval=None) docs
        self._reset_hardware_caches()
        # Create system and image stats caches
        self._reset_caches()
        # Protect caches from simultaneous access problems
        self.sys_cache_lock = Lock()
        self.img_cache_lock = Lock()
        self.flush_lock = Lock()
        # Create thread for flushing caches to database
        self.flush_thread = Thread(
            target=self.cache_flush_thread,
            name='stats_flush_thread'
        )
        self.flush_thread.daemon = False
        self.flush_thread.start()
        # Create thread to monitor the flushes
        self.flush_monitor_thread = Thread(
            target=self.flush_monitor_thread,
            name='flush_monitor_thread'
        )
        self.flush_monitor_thread.daemon = False
        self.flush_monitor_thread.start()
        # Create thread for cleaning up old stats
        self.tidy_thread = Thread(
            target=self.stats_tidyup_thread,
            name='stats_tidyup_thread',
            kwargs={
                'keep_days': app.config['STATS_KEEP_DAYS']
            }
        )
        self.tidy_thread.daemon = False
        self.tidy_thread.start()

    def cache_flush_thread(self):
        """
        A thread that regularly writes the stats caches to the database.
        """
        self.logger.info('Stats server running')
        while not self.shutdown_ev.is_set():
            sleep(60)
            self._flush()
        self.logger.info('Stats server exited')

    def stats_tidyup_thread(self, keep_days=0):
        """
        A thread responsible for periodically uploading anonymous
        usage statistics and deleting old statistics records.
        """
        # Set first run as 1 hour after startup
        self.tidy_last = datetime.utcnow() - timedelta(hours=23)

        while not self.shutdown_ev.is_set():
            sleep(60)
            # Run tasks once per day
            if (datetime.utcnow() - self.tidy_last) > timedelta(hours=24):
                if keep_days < 1:
                    self.logger.info('Automatic stats deletion is disabled')
                else:
                    # Purge old statistics (as a background task)
                    purge_date = date.today() - timedelta(days=keep_days)
                    purge_time = datetime(
                        purge_date.year,
                        purge_date.month,
                        purge_date.day
                    )
                    self.tasks.add_task(
                        None,
                        'Auto-delete historic system statistics',
                        'purge_system_stats',
                        {'before_time': purge_time},
                        Task.PRIORITY_NORMAL,
                        'info', 'error',
                        60 * 60 * 23       # Don't repeat for 23+ hours
                    )
                    self.tasks.add_task(
                        None,
                        'Auto-delete historic image statistics',
                        'purge_image_stats',
                        {'before_time': purge_time},
                        Task.PRIORITY_NORMAL,
                        'info', 'error',
                        60 * 60 * 23
                    )
                # Upload usage stats (as a background task)
                self.tasks.add_task(
                    None,
                    'Upload usage statistics',
                    'upload_usage_stats',
                    {},
                    Task.PRIORITY_NORMAL,
                    'info', 'warning',
                    60 * 60 * 23
                )
                self.tidy_last = datetime.utcnow()

    def flush_monitor_thread(self):
        """
        A thread to detect and handle problems with the flush process.
        """
        while not self.shutdown_ev.is_set():
            sleep(60)
            # Get time since last flush
            with self.sys_cache_lock:
                dt_last_flush = self.caches_started
            # If age is much more than a minute, the flush is either slow or
            # failing.  But if the caches reach STATS_FREQUENCY age, we have to
            # discard them to prevent the next successful flush from including
            # stats that span more than 1 time period. This otherwise causes a
            # false spike in the data.
            caches_age = datetime.utcnow() - dt_last_flush
            if caches_age >= timedelta(minutes=self.frequency):
                self.logger.error((
                    'Stats have not been flushed for %s minutes. '
                    'Discarding old data to begin a new stats period.'
                ) % self.frequency)
                with self.sys_cache_lock:
                    with self.img_cache_lock:
                        self._reset_caches()

    def _reset_caches(self):
        """
        Clears the current image and system stats caches.
        Normally this happens every minute as part of the flush process.
        NOTE: both cache locks must already be locked!
        """
        # System stats
        self.sys_cache = Counter()
        # Image stats
        self.img_cache = defaultdict(Counter)
        # Note the last reset time
        self.caches_started = datetime.utcnow()

    def _reset_hardware_caches(self):
        """
        Clears the current hardware (CPU, RAM) stats caches.
        This should happen whenever the system stats record is rolled over.
        Only the flush thread uses the hardware stats so no locks are required.
        """
        self.hw_cache = {
            'cpu': [],
            'ram': [],
            'cache': []
        }

    def _flush_sys_stats_bucket(self, db_session, dt_period_start, dt_now, stats):
            db_sys_stats = self.database.get_latest_system_stats(
                since_time=dt_period_start,
                _db_session=db_session
            )
            if db_sys_stats is None:
                db_sys_stats = SystemStats(
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    self.caches_started, dt_now
                )
                db_session.add(db_sys_stats)
                self._reset_hardware_caches()

            st_cpu, st_ram, st_dcache = self._poll_hardware()

            db_sys_stats.requests += stats['requests']
            db_sys_stats.views += stats['views']
            db_sys_stats.cached_views += stats['cached_views']
            db_sys_stats.downloads += stats['downloads']
            db_sys_stats.total_bytes += stats['bytes']
            db_sys_stats.request_seconds += stats['request_seconds']
            db_sys_stats.max_request_seconds = stats['max_request_seconds']
            db_sys_stats.cpu_pc = st_cpu
            db_sys_stats.memory_pc = st_ram
            db_sys_stats.cache_pc = st_dcache
            db_sys_stats.to_time = dt_now

    def _flush_img_stats_bucket(self, db_session, dt_period_start, dt_now, stats):
        inserts = []
        model = ImageStats
        table = self.database._db_metadata.tables[ImageStats.__table_name__]
        for image_id, istats in stats.iteritems():
            rcount = istats['requests']
            vcount = istats['views']
            cvcount = istats['cached_views']
            dcount = istats['downloads']
            bytesum = istats['bytes']
            rsecs = istats['request_seconds']
            maxsecs = istats['max_request_seconds']

            update_num = db_session.query(model).filter(
                model.image_id == image_id
            ).filter(
                model.from_time > dt_period_start
            ).update({
                model.requests: model.requests + rcount,
                model.views: model.views + vcount,
                model.cached_views: model.cached_views + cvcount,
                model.downloads: model.downloads + dcount,
                model.total_bytes: model.total_bytes + bytesum,
                model.request_seconds: model.request_seconds + rsecs,
                model.max_request_seconds: maxsecs,
                model.to_time: dt_now
            }, synchronize_session=False)

            if not update_num:
                inserts.append({
                    'image_id': image_id,
                    'requests': rcount,
                    'views': vcount,
                    'cached_views': cvcount,
                    'downloads': dcount,
                    'total_bytes': bytesum,
                    'request_seconds': rsecs,
                    'max_request_seconds': maxsecs,
                    'from_time': self.caches_started,
                    'to_time': dt_now
                })
        db_session.commit()

        if inserts:
            try:
                db_session.execute(table.insert(), inserts)
            except IntegrityError:
                db_session.rollback()
                inserts = self._fix_insert_list(inserts, db_session)
                if inserts:
                    db_session.execute(table.insert(), inserts)

    def _flush(self):
        """
        Flushes the current cache state to the database and resets the caches.
        """
        if not self.flush_lock.acquire(0):
            self.logger.warn(
                'A stats flush is already in progress, '
                'abandoning this run.'
            )
            return

        start_time = datetime.utcnow()
        try:
            self.logger.debug('Statistics flush starting')

            # Get and test the database connection first.
            # If it's down we'll want to roll the stats over and carry on.
            db_session = self.database.db_get_session(autoflush=False)

            try:
                # Take copies of the caches then reset them so the
                # request handler can keep going
                with self.sys_cache_lock:
                    with self.img_cache_lock:
                        local_sys_cache = self.sys_cache
                        local_img_cache = self.img_cache
                        self._reset_caches()
                        self.logger.debug('Stats caches copied and reset')

                dt_now = datetime.utcnow()
                dt_period_start = dt_now - timedelta(minutes=self.frequency)

                # System stats
                self._flush_sys_stats_bucket(
                    db_session, dt_period_start, dt_now, local_sys_cache
                )
                db_session.commit()
                self.logger.debug('System stats updated')

                # Image stats
                self._flush_img_stats_bucket(
                    db_session, dt_period_start, dt_now, local_img_cache
                )
                db_session.commit()
                self.logger.info('Statistics updated for %d image(s)' % len(local_img_cache))
            finally:
                db_session.close()

        except Exception as e:
            self.logger.error('Error flushing stats to database: ' + str(e))
        finally:
            self.flush_lock.release()

        # Warn if that all took longer than we expect
        end_time = datetime.utcnow()
        flush_delta = (end_time - start_time)
        if flush_delta.seconds > 10:
            self.logger.warn(
                'Statistics flush took ' + str(flush_delta.seconds) +
                ' seconds, check server load and database'
            )
        else:
            self.logger.debug(
                'Statistics flush took ' + str(
                    (flush_delta.seconds * 1000) +
                    (flush_delta.microseconds / 1000)
                ) + ' milliseconds'
            )

    def _fix_insert_list(self, insert_list, db_session):
        """
        When an image is deleted (and the image data purged), it is possible
        for recent image views, or views of cached versions, to still be
        recorded here. Attempting to insert a stats record for the deleted
        image then causes a foreign key integrity error.

        This function checks all image IDs in the provided data list for
        existence, removes list entries for image IDs that no longer exist, and
        returns the list.
        """
        self.logger.warn(
            'Stats data includes deleted images, attempting to fix and retry'
        )
        ret_list = []
        for stat_dict in insert_list:
            image_id = stat_dict['image_id']
            if (
                self.database.get_image(
                    image_id,
                    _db_session=db_session) is None
            ):
                self.logger.warn(
                    'Removing deleted image ID %d from stats' % image_id
                )
                # Remove left-over images from cache too
                self.tasks.add_task(
                    None,
                    'Uncache deleted image',
                    'uncache_image',
                    {'image_id': image_id},
                    Task.PRIORITY_NORMAL,
                    None, 'error'
                )
            else:
                ret_list.append(stat_dict)
        self.logger.debug('Now retrying image stats write')
        return ret_list

    def _poll_hardware(self):
        """
        Returns a tuple of
        (average CPU usage, average RAM usage, current cache usage)
        for the server running the stats process (this!). The CPU and RAM
        values will be returned as 0 if the psutils package is not installed.
        """
        current_cpu = psutil.cpu_percent(interval=None) if _have_psutil else 0
        current_ram = psutil.virtual_memory().percent if _have_psutil else 0
        current_cache = max(self.data_cache.size_percent(), 0)

        self.logger.debug('Server usage: CPU %.1f%%, RAM %.1f%%, cache %d%%' % (
            current_cpu, current_ram, current_cache
        ))

        self.hw_cache['cpu'].append(current_cpu)
        self.hw_cache['ram'].append(current_ram)
        self.hw_cache['cache'].append(current_cache)

        avg_cpu = sum(self.hw_cache['cpu']) / len(self.hw_cache['cpu'])
        avg_ram = sum(self.hw_cache['ram']) / len(self.hw_cache['ram'])
        latest_cache = self.hw_cache['cache'][-1]
        return (avg_cpu, avg_ram, latest_cache)

    def _shutdown(self, signum, frame):
        def _shutdown_socket_server(svr):
            # "must be called while serve_forever() is running in another thread"
            svr.shutdown()

        self.shutdown_ev.set()
        t = Thread(target=_shutdown_socket_server, args=(self,))
        t.start()


def _run_server(debug_mode):
    """
    Opens a TCP/IP streaming socket and receives stats records indefinitely.
    This function does not return until the process is killed.
    """
    try:
        svr = StatsSocketServer(debug_mode)
        signal.signal(signal.SIGTERM, svr._shutdown)
        svr.serve_forever()
        print 'Stats server shutdown'

    except IOError as e:
        if e.errno == errno.EADDRINUSE:
            print "A stats server is already running."
        else:
            print "Stats server exited: " + str(e)
    except BaseException as e:
        if (len(e.args) > 0 and e.args[0] == errno.EINTR) or not str(e):
            print "Stats server exited"
        else:
            print "Stats server exited: " + str(e)
    sys.exit()


def _run_server_process_double_fork(*args):
    p = Process(
        target=_run_server,
        name='stats_server',
        args=args
    )
    # Do not kill the stats server process when this process exits
    p.daemon = False
    p.start()
    sleep(1)
    # Force our exit, leaving the stats server process still running.
    # Our parent process can now exit cleanly without waiting to join() the
    # actual stats server process (it can't, since it knows nothing about it).
    os._exit(0)


def run_server_process(debug_mode):
    """
    Starts a stats server as a separate process, to receive stats messages over
    TCP/IP. The port number and other settings are loaded from the imageserver
    settings module. If the TCP/IP port is already in use or cannot be opened,
    the server process simply exits.
    """
    # Double fork, otherwise we cannot exit until the server process has
    # completed
    p = Process(
        target=_run_server_process_double_fork,
        args=(debug_mode, )
    )
    # Start and wait for the double_fork process to complete (which is quickly)
    p.start()
    p.join()


# Allow the server to be run from the command line
if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "Use: stats_server <debug mode>\n"
        print "E.g. export PYTHONPATH=."
        print "     python imageserver/auxiliary/stats_server.py false\n"
    else:
        from imageserver.flask_app import app as init_app
        with init_app.app_context():
            run_server_process(sys.argv[1].lower() == 'true')
