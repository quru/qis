#
# Quru Image Server
#
# Document:      user_edit.py
# Date started:  10 May 2012
# By:            Matt Fozard
# Purpose:       Local user account utility
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
#        python user_edit.py <command>
#

import site
import sys

RETURN_OK = 0
RETURN_MISSING_PARAMS = 1
RETURN_BAD_PARAMS = 2
RETURN_DB_ERROR = 3

silent = False


class Parameters():
    MODE_UPDATE = 0
    MODE_ADD = 1
    MODE_DELETE = 2

    def __init__(self):
        self.mode = Parameters.MODE_UPDATE
        self.err_msg = ''
        self.username = ''
        self.password = ''
        self.firstname = ''
        self.lastname = ''
        self.email = ''

    def set_from_args(self, args):
        """
        Populates this object from the provided string array.
        On failure, the err_msg value will be set to an error message,
        and is_error() will return True.
        """
        self.err_msg = ''
        max_idx = len(args) - 1
        cur_idx = 0
        # Parse parameters
        try:
            while cur_idx <= max_idx:
                arg = args[cur_idx]
                if arg == '-a':
                    self.mode = Parameters.MODE_ADD
                elif arg == '-d':
                    self.mode = Parameters.MODE_DELETE
                elif arg == '-u':
                    cur_idx += 1
                    if (cur_idx > max_idx) or args[cur_idx].startswith('-'):
                        raise ValueError('Missing username value')
                    self.username = args[cur_idx]
                elif arg == '-p':
                    cur_idx += 1
                    if (cur_idx > max_idx) or args[cur_idx].startswith('-'):
                        raise ValueError('Missing password value')
                    self.password = args[cur_idx]
                elif arg == '-e':
                    cur_idx += 1
                    if (cur_idx > max_idx) or args[cur_idx].startswith('-'):
                        raise ValueError('Missing email value')
                    self.email = args[cur_idx]
                elif arg == '-fn':
                    cur_idx += 1
                    if (cur_idx > max_idx) or args[cur_idx].startswith('-'):
                        raise ValueError('Missing first name value')
                    self.firstname = args[cur_idx]
                elif arg == '-ln':
                    cur_idx += 1
                    if (cur_idx > max_idx) or args[cur_idx].startswith('-'):
                        raise ValueError('Missing last name value')
                    self.lastname = args[cur_idx]
                else:
                    raise ValueError('Unrecognised parameter: ' + arg)
                cur_idx += 1
            # Check parameter combinations
            if not self.username:
                raise ValueError('The username to add/update/delete must be provided')
            if self.mode == Parameters.MODE_ADD:
                if not self.password:
                    raise ValueError('A password must be provided')
        except ValueError as e:
            self.err_msg = str(e)

    def is_error(self):
        return len(self.err_msg) > 0


def apply_user(params):
    from imageserver.flask_app import data_engine
    from imageserver.models import User
    from imageserver.errors import DBError
    try:
        existing_user = data_engine.get_user(username=params.username)

        if params.mode == Parameters.MODE_ADD:
            if existing_user:
                if existing_user.status == User.STATUS_DELETED:
                    raise ValueError('A deleted user record for this username already exists')
                else:
                    raise ValueError('This username already exists')
            else:
                data_engine.create_user(User(
                    params.firstname,
                    params.lastname,
                    params.email,
                    params.username,
                    params.password,
                    User.AUTH_TYPE_PASSWORD,
                    False,
                    User.STATUS_ACTIVE
                ))
                log('User created')
        elif params.mode == Parameters.MODE_UPDATE:
            if not existing_user:
                raise ValueError('The username was not found')
            if existing_user.status == User.STATUS_DELETED:
                raise ValueError('This user record is deleted')
            existing_user.first_name = params.firstname
            existing_user.last_name = params.lastname
            existing_user.email = params.email
            existing_user.set_password(params.password)
            data_engine.save_object(existing_user)
            log('User updated')
        else:
            if not existing_user:
                raise ValueError('The username was not found')
            data_engine.delete_user(existing_user)
            log('User deleted')

        return RETURN_OK
    except ValueError as e:
        error(str(e))
        return RETURN_BAD_PARAMS
    except DBError as e:
        error(str(e))
        return RETURN_DB_ERROR


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
    print('\nAdministration utility for managing local image server user accounts.')
    print('\nUsage: su <qis user>')
    print('       python user_edit.py [-a] [-d] -u <username> -p <password> ')
    print('                           -e <email> -fn <firstname> -ln <lastname>')
    print('\nWhere:')
    print('         -a specifies user details to add (provide all details)')
    print('         -d specifies a user to delete (only username required)')
    print('         If neither -a or -d is specified, user details are updated')


if __name__ == '__main__':
    try:
        pver = sys.version_info
        # Pythonpath - escape sub-folder and add custom libs
        site.addsitedir('../..')
        site.addsitedir('../../../lib/python%d.%d/site-packages' % (pver.major, pver.minor))
        # Get params
        if len(sys.argv) > 2:
            params = Parameters()
            params.set_from_args(sys.argv[1:])
            if not params.is_error():
                rc = apply_user(params)
                exit(rc)
            else:
                print(params.err_msg)
                exit(RETURN_BAD_PARAMS)
        show_usage()
        exit(RETURN_BAD_PARAMS)

    except Exception as e:
        print('Utility exited with error:\n' + str(e))
        print('Ensure you are using the correct user account, ' \
              'and (optionally) set the QIS_SETTINGS environment variable.')
