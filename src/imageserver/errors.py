#
# Quru Image Server
#
# Document:      errors.py
# Date started:  31 Mar 2011
# By:            Matt Fozard
# Purpose:       Internal errors and exceptions
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


class ImageError(ValueError):
    """
    An error resulting from an invalid or unsupported imaging operation.
    """
    pass


class AlreadyExistsError(ValueError):
    """
    An error resulting from a duplicate value or an attempt to create an
    object that already exists.
    """
    pass


class DoesNotExistError(ValueError):
    """
    An error resulting from an attempt to use an object that does not exist.
    """
    pass


class SecurityError(Exception):
    """
    An error resulting from some unauthorised action.
    """
    pass


class StartupError(Exception):
    """
    An error that should prevent server startup.
    """
    pass


class AuthenticationError(Exception):
    """
    An error resulting from a failure to authenticate.
    """
    pass


class DBError(Exception):
    """
    An error resulting from a database operation.
    Adds an optional extra 'sql' attribute.
    """
    def __init__(self, message, sql=None):
        Exception.__init__(self, message)
        self.sql = sql if sql is not None else ''


class DBDataError(DBError):
    """
    An error resulting from incorrect database data.
    """
    pass


class ParameterError(ValueError):
    """
    An error resulting from an invalid parameter value.
    """
    pass


class TimeoutError(RuntimeError):
    """
    An error resulting from an operation timeout.
    """
    pass


class ServerTooBusyError(RuntimeError):
    """
    Raised when the server is too busy to service a request.
    """
    pass
