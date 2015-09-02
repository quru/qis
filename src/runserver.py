#
# Quru Image Server
#
# Document:      runserver.py
# Date started:  04 Apr 2011
# By:            Matt Fozard
# Purpose:       Runs the development Python web server
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
#
# Notes:
#
# Script to run the image server using the built-in development HTTP server.
# For a production deployment, use Apache with mod_wsgi and runserver.wsgi
#
# Usage: su username
#        python runserver.py [host [port]]
#
# Looks for conf/local_settings.py by default, or you can set the QIS_SETTINGS
# environment variable with the full path to your development settings file.
#

import os
import signal
import sys

if __name__ == '__main__':
    normal_exit = True
    try:
        from imageserver.flask_app import app

        host = '127.0.0.1' if app.config['DEBUG'] else '0.0.0.0'
        if len(sys.argv) > 1:
            host = sys.argv[1]
        port = 5000
        if len(sys.argv) > 2:
            port = int(sys.argv[2])

        # If you're on Mac OS X and the app is crashing in qismagick.so,
        # either rebuild ImageMagick with --disable-openmp
        # or try adding use_reloader=False to app.run below.

        # The reloader unhooks debugger breakpoints, so disable it when debugging
        use_reloader = app.config['DEBUG'] and (sys.gettrace() is None)

        if not os.environ.get('QIS_SETTINGS'):
            print '''
                Warning! The QIS_SETTINGS environment variable is not set
                and no conf/local_settings.py file was found.
                Continuing with default settings...
            '''

        app.run(host=host, port=port, debug=app.config['DEBUG'], use_reloader=use_reloader)

    except Exception as e:
        normal_exit = False
        print '\nServer exited with error:\n' + str(e)
        print 'If the image engine failed to start, ' \
              'check your settings file and environment variables.\n'
        raise
    finally:
        if not normal_exit:
            # Stop the background aux processes too
            signal.signal(signal.SIGTERM, lambda a, b: None)
            os.killpg(os.getpgid(0), signal.SIGTERM)
