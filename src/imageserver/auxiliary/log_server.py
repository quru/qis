#
# Quru Image Server
#
# Document:      log_server.py
# Date started:  03 Aug 2011
# By:            Matt Fozard
# Purpose:       Logging server
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
#

import pickle
import errno
import logging.handlers
import os
import socketserver
import signal
import struct
import sys
from multiprocessing import Process
from threading import Thread
from time import sleep

from flask import current_app as app


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """
    Handler to receive log records sent from a Python logging SocketHandler.

    Loosely based on the network logging example at
    http://docs.python.org/dev/howto/logging-cookbook.html
    """
    def handle(self):
        """
        Handle multiple requests for as long as the connection is open.
        Each request is expected to contain a 4-byte length followed by the
        LogRecord in pickle format. Logs the record according to whatever
        policy is configured locally.
        """
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack('>L', chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = pickle.loads(chunk)
            record = logging.makeLogRecord(obj)
            # Log every record (the client is responsible for filtering by log level)
            self.server.logging_engine.handle(record)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    A TCP server containing a logger.

    One thread is created per logging connection. The client is expected to
    keep its connection open, so that each thread is long-lived.

    Loosely based on the network logging example at
    http://docs.python.org/dev/howto/logging-cookbook.html
    """
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, bind_addr, bind_port, log_file_path, stdout_echo):
        socketserver.ThreadingTCPServer.__init__(
            self,
            (bind_addr, bind_port),
            LogRecordStreamHandler
        )
        # Set up logging destination to file
        logging_engine = logging.getLogger('')
        logging_format = logging.Formatter('%(asctime)s %(name)-10s %(levelname)-8s %(message)s')
        handler_file = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=1048576,
            backupCount=5
        )
        handler_file.setFormatter(logging_format)
        logging_engine.addHandler(handler_file)
        # And a stdout destination if we want one
        if stdout_echo:
            handler_stdout = logging.StreamHandler()
            handler_stdout.setFormatter(logging_format)
            logging_engine.addHandler(handler_stdout)
        # Store a reference to our logger
        self.logging_engine = logging_engine

    def _shutdown(self, signum, frame):
        def _shutdown_socket_server(svr):
            # "must be called while serve_forever() is running in another thread"
            svr.shutdown()

        t = Thread(target=_shutdown_socket_server, args=(self,))
        t.start()


def _run_server(log_filename, stdout_echo):
    """
    Opens a TCP/IP streaming socket and receives log records indefinitely.
    This function does not return until the process is killed.
    """
    try:
        svr = LogRecordSocketReceiver(
            app.config['LOGGING_SERVER'],
            app.config['LOGGING_SERVER_PORT'],
            os.path.join(app.config['LOGGING_BASE_DIR'], log_filename),
            stdout_echo
        )
        signal.signal(signal.SIGTERM, svr._shutdown)
        svr.serve_forever()
        print('Logging server shutdown')

    except IOError as e:
        if e.errno == errno.EADDRINUSE:
            print("A logging server is already running.")
        else:
            print("Logging server exited: " + str(e))
    except BaseException as e:
        if (len(e.args) > 0 and e.args[0] == errno.EINTR) or not str(e):
            print("Logging server exited")
        else:
            print("Logging server exited: " + str(e))
    sys.exit()


def _run_server_process_double_fork(*args):
    p = Process(
        target=_run_server,
        name='log_server',
        args=args
    )
    # Do not kill the log server process when this process exits
    p.daemon = False
    p.start()
    sleep(1)
    # Force our exit, leaving the log server process still running.
    # Our parent process can now exit cleanly without waiting to join() the
    # actual log server process (it can't, since it knows nothing about it).
    os._exit(0)


def run_server_process(log_filename, stdout_echo):
    """
    Starts a logging server as a separate process, to receive logs over TCP/IP.
    The port number and log file path are loaded from the imageserver settings
    module. If the TCP/IP port is already in use or cannot be opened, the
    server process simply exits.
    """
    # Double fork, otherwise we cannot exit until the log server process has completed
    p = Process(
        target=_run_server_process_double_fork,
        args=(log_filename, stdout_echo)
    )
    # Start and wait for the double_fork process to complete (which is quickly)
    p.start()
    p.join()


# Allow the server to be run from the command line
if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Use: log_server <log_file_path> <bind address> <bind port> <stdout_echo>\n")
        print("E.g. export PYTHONPATH=.")
        print("     python imageserver/auxiliary/log_server.py /path/to/my.log 0.0.0.0 9002 true\n")
    else:
        # Create a blank Flask app. We can't use imageserver.flask_app
        # as the first thing it does is spawn this very service!
        from flask import Flask
        init_app = Flask(__name__)
        with init_app.app_context():
            init_app.config['LOGGING_BASE_DIR'] = ''
            init_app.config['LOGGING_SERVER'] = sys.argv[2]
            init_app.config['LOGGING_SERVER_PORT'] = int(sys.argv[3])
            run_server_process(sys.argv[1], (sys.argv[4].lower() == 'true'))
