#
# Quru Image Server
#
# Document:      cache_util.py
# Date started:  07 Sep 2011
# By:            Matt Fozard
# Purpose:       Cache utilities
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
# Usage: su <qis user>
#        (optional) export QIS_SETTINGS=<path to your settings.py>
#        python cache_util.py <command>
#

import site
import sys

RETURN_OK = 0
RETURN_MISSING_PARAMS = 1
RETURN_BAD_PARAMS = 2
RETURN_CACHE_ERROR = 3

silent = False


def delete_image_ids():
    try:
        from imageserver.flask_app import cache_engine, data_engine
        from imageserver import models
        log('Deleting cached image IDs')
        dbs = data_engine.db_get_session()
        try:
            for src in dbs.query(models.Image.src).all():
                cache_key = data_engine._get_id_cache_key(src[0])
                cache_engine.raw_delete(cache_key)
                print('.', end=' ')
        finally:
            dbs.close()
        log('Done')
        return RETURN_OK
    except Exception as e:
        error(str(e))


def log(astr):
    """
    Outputs an informational message if silent mode is disabled.
    """
    if not silent:
        print(astr)


def error(astr):
    """
    Outputs an error message.
    """
    print('ERROR: ' + astr)


def show_usage():
    """
    Outputs usage information.
    """
    print('\nAdministration utilities for managing the image cache.')
    print('\nUsage: su <qis user>')
    print('       python cache_util.py <command>')
    print('Where command can be:')
    print('       del_ids - delete cached image IDs')


if __name__ == '__main__':
    try:
        pver = sys.version_info
        # Pythonpath - escape sub-folder and add custom libs
        site.addsitedir('../..')
        site.addsitedir('../../../lib/python%d.%d/site-packages' % (pver.major, pver.minor))
        # Get params
        cmd = ''
        if len(sys.argv) == 2:
            cmd = sys.argv[1]
        if cmd == 'del_ids':
            rc = delete_image_ids()
            exit(rc)
        else:
            show_usage()
            exit(RETURN_BAD_PARAMS)

    except Exception as e:
        print('Utility exited with error:\n' + str(e))
        print('Ensure you are using the correct user account, ' \
              'and (optionally) set the QIS_SETTINGS environment variable.')
