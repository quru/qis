#
# Quru Image Server
#
# Document:      stats_manager.py
# Date started:  31 Aug 2011
# By:            Matt Fozard
# Purpose:       Provides multi-process statistics recording services
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
#

import json
import socket
import time
from threading import Lock

import imageserver.auxiliary.stats_server as stats_server
from imageserver.util import this_is_computer

RECONNECT_WAIT_SECS = 30


class StatsManager(object):
    """
    Manages client-server statistics logging for the application.

    Provides the ability to launch a stats recording server process,
    and a set of client functions that can be called to record image accesses.
    """
    def __init__(self, logger, server_host, server_port):
        """
        Initialises a stats logging client.

        logger       - a logger for client messages
        server_host  - the name or IP address of the stats server
        server_port  - the port number of the stats server

        Statistics can be disabled by providing an empty string for server_host
        and/or 0 for the port number.
        """
        self._logger = logger
        self._server_host = server_host
        self._server_port = server_port
        self._sock = None
        self._sock_lock = Lock()
        self._sock_last_connect = 0
        # Do not send stats if we have no host name or port
        self.set_enabled(server_host and (server_port > 0))

    def _client_connect(self):
        """
        Re-connects the connection to the server, if it is not connected
        and RECONNECT_WAIT_SECS seconds have passed since the last attempt.
        """
        now_secs = long(time.time())
        if (now_secs - self._sock_last_connect >= RECONNECT_WAIT_SECS):
            self._sock_last_connect = now_secs
            try:
                self._logger.debug('Connecting to stats server')
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.connect((self._server_host, self._server_port))
                self._logger.info('Connected OK to stats server')
            except Exception as e:
                self._logger.error('Failed to connect to stats server: ' + str(e))
                self._client_close()
                # Kick the stats server (but don't try this too often)
                # self._init_server(...)

    def _client_close(self):
        """
        Disconnects from the the server.
        """
        if self._sock is not None:
            try:
                self._sock.close()
            except:
                pass
        self._sock = None

    def _send(self, data):
        """
        Internal function that sends an object to the stats server.
        Returns a boolean indicating success.
        """
        if not self._enabled:
            return False

        try:
            if not self._sock:
                self._client_connect()
                if not self._sock:
                    return False

            with self._sock_lock:
                self._sock.send(json.dumps(data) + "\r\n")
            return True

        except Exception as e:
            self._logger.error('Connection to stats server failed: ' + str(e))
            self._client_close()
            return False

    def set_enabled(self, enabled):
        """
        Enables or disables the logging of statistics.
        """
        self._enabled = enabled

    def log_request(self, image_id, duration_secs, write_image_stats=True):
        """
        Logs an image request that did not return image data.
        Specify the image ID as 0 to update only the system statistics, or set
        write_image_stats False to update only the request count for an image.
        """
        if image_id and not write_image_stats:
            self._send({
                # Bump requests in both system stats and image stats
                image_id: {"requests": 1},
                # Then update system stats only
                0: {
                    "request_seconds": duration_secs
                }
            })
        else:
            # The normal case, update both system stats and image stats
            self._send({
                image_id: {
                    "requests": 1,
                    "request_seconds": duration_secs
                }
            })

    def log_view(self, image_id, size, from_cache, duration_secs, write_image_stats=True):
        """
        Logs an image request that returned image data.
        Specify the image ID as 0 to update only the system statistics, or set
        write_image_stats False to update only the request count for an image.
        """
        if image_id and not write_image_stats:
            self._send({
                # Bump requests in both system stats and image stats
                image_id: {"requests": 1},
                # Then update system stats only
                0: {
                    "views": 1,
                    "cached_views": 1 * from_cache,
                    "bytes": size,
                    "request_seconds": duration_secs
                }
            })
        else:
            # The normal case, update both system stats and image stats
            self._send({
                image_id: {
                    "requests": 1,
                    "views": 1,
                    "cached_views": 1 * from_cache,
                    "bytes": size,
                    "request_seconds": duration_secs
                }
            })

    def log_download(self, image_id, size, duration_secs, write_image_stats=True):
        """
        Logs the download of an original image file.
        Specify the image ID as 0 to update only the system statistics, or set
        write_image_stats False to update only the request count for an image.
        """
        if image_id and not write_image_stats:
            self._send({
                # Bump requests in both system stats and image stats
                image_id: {"requests": 1},
                # Then update system stats only
                0: {
                    "downloads": 1,
                    "bytes": size,
                    "request_seconds": duration_secs
                }
            })
        else:
            # The normal case, update both system stats and image stats
            self._send({
                image_id: {
                    "requests": 1,
                    "downloads": 1,
                    "bytes": size,
                    "request_seconds": duration_secs
                }
            })

    @staticmethod
    def run_server(server_host, server_port, debug_mode):
        """
        Launches a statistics server if the server_host (as a host name or IP
        address) evaluates to this server. Returns without action if the
        server_host appears to refer to a different server, or if a server
        process is already running.

        server_host - the name or IP address of the stats server
        server_port - the port number that the stats server will listen on
        debug_mode  - whether to run the stats server in debug mode

        Statistics can be disabled by providing an empty string for server_host
        and/or 0 for the port number.
        """
        if server_host and (server_port > 0) and this_is_computer(server_host):
            stats_server.run_server_process(debug_mode)
