#
# Quru Image Server
#
# Document:      log_manager.py
# Date started:  28 Mar 2011
# By:            Matt Fozard
# Purpose:       Provides multi-process logging services
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
# 03Aug2011  Matt  Changed to instantiate a logging server and log using a
#                  SocketHandler (making the logging multi-process safe)
# 31Aug2011  Matt  Renamed from logger.py to log_manager.py, converted into a
#                  class containing logging state to match stats_manager.py
# 04Jan2013  Matt  Move run_server to a static method, do not call from client constructor

import logging.handlers
import time

from imageserver.auxiliary import log_server
from imageserver.util import this_is_computer


class LogManager(object):
    """
    Manages client-server logging for the application.

    Provides the ability to launch a logging server process,
    and a set of client functions that can be called by areas requiring logging.
    """
    def __init__(self, logger_name, debug_mode, server_host, server_port):
        """
        Initialises a logging client.

        logger_name - a name for the logging client
        debug_mode - a boolean for whether to log additional information
        server_host - the name or IP address of the logging server
        server_port - the port number of the logging server

        The log functions connect to the logging server automatically.
        Logging can be disabled by providing an empty string for server_host
        and/or 0 for the port number.
        """
        self.logging_handler = None
        self.logging_engine = None
        self._host = server_host
        self._port = server_port
        self._client_connect(logger_name)
        self.set_debug_mode(debug_mode)
        # Do not log if we have no host name or port
        self.set_enabled(server_host and (server_port > 0))

    def _client_connect(self, logger_name):
        """
        (Re-)establishes the connection to the server and sets the logging
        client name.
        """
        is_disabled = False
        is_debug = False
        if self.logging_engine:
            is_disabled = self.logging_engine.disabled
            is_debug = self.get_level() == logging.DEBUG
            for handler in self.logging_engine.handlers:
                handler.close()
                self.logging_engine.removeHandler(handler)
        self.logging_engine = logging.getLogger(logger_name)
        self.logging_handler = logging.handlers.SocketHandler(
            self._host, self._port
        )
        self.logging_engine.addHandler(self.logging_handler)
        self.set_debug_mode(is_debug)
        self.set_enabled(not is_disabled)

    def _client_close(self):
        """
        Disconnects from the server. The connection will try to re-establish
        automatically if a log function is subsequently called.
        """
        if self.logging_handler and self.logging_handler.sock:
            try:
                self.logging_handler.sock.close()
            except (IOError, OSError):
                pass
            finally:
                self.logging_handler.sock = None

    def reconnect(self, logger_name):
        """
        Resets the connection to the server with a new logging client name.
        """
        self._client_connect(logger_name)

    def set_enabled(self, enabled):
        self.logging_engine.disabled = not enabled

    def set_debug_mode(self, debug_mode):
        self.logging_engine.setLevel(logging.DEBUG if debug_mode else logging.INFO)

    def get_level(self):
        return self.logging_engine.getEffectiveLevel()

    def debug(self, msg):
        self.logging_engine.debug(msg)

    def info(self, msg):
        self.logging_engine.info(msg)

    def warning(self, msg):
        self.logging_engine.warning(msg)

    def error(self, msg):
        self.logging_engine.error(msg)

    def critical(self, msg):
        self.logging_engine.critical(msg)

    @staticmethod
    def run_server(server_host, server_port, log_filename, debug_mode):
        """
        Launches a logging server if the server_host (as a host name or IP
        address) evaluates to this server. Returns without action if the
        server_host appears to refer to a different server, or if a logging
        server process is already running.

        server_host - the name or IP address of the logging server
        server_port - the port number that the logging server will listen on
        log_filename - the log filename that the logging server will create
        debug_mode - a boolean for whether to log additional information

        Logging can be disabled by providing an empty string for server_host
        and/or 0 for the port number.
        """
        if server_host and (server_port > 0) and this_is_computer(server_host):
            log_server.run_server_process(log_filename, debug_mode)
            time.sleep(1)  # Yuck, but we don't want to lose the first logs
