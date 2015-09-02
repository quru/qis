#
# Quru Image Server
#
# Document:      session_manager.py
# Date started:  15 Nov 2012
# By:            Matt Fozard
# Purpose:       Manages a web or API session
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
# NOTE Flask sessions are cookie based - whatever goes in the session gets
#      sent to the client on every response! For this reason we only add a
#      user ID to the session and no more.
#

import flask

from flask_app import data_engine
from errors import SecurityError
from models import User


def logged_in():
    """
    Returns whether a user is logged in, either with HTTP authentication
    (for the API) or on the current Flask session (for the web pages).
    """
    return (get_session_user_id() > 0)


def get_session_user():
    """
    Returns a detached copy of the currently logged in user object,
    including the user's groups, or None if no one is logged in.
    """
    uid = get_session_user_id()
    if uid > 0:
        # Cache the user object on flask.g.user
        if 'user' not in flask.g or not flask.g.user:
            flask.g.user = data_engine.get_user(uid, load_groups=True)
            del flask.g.user.password  # We don't want this floating around
        return flask.g.user
    return None


def get_session_user_id():
    """
    Returns the currently logged in user ID (either with HTTP authentication
    or on the Flask session), or -1 if no one is logged in.
    """
    # Check the HTTP auth first, as this is more specific than the Flask
    # session cookie (that could have been hanging around in the browser).
    http_auth_obj = flask.g.get('http_auth')
    if http_auth_obj is not None:
        return http_auth_obj['user_id']
    else:
        session_uid = flask.session.get('user_id', -1)
        return session_uid if session_uid > 0 else -1


def log_in(user):
    """
    Sets the supplied user as logged in on the current Flask session.
    """
    if user.status != User.STATUS_ACTIVE:
        raise SecurityError('User account %s is disabled/deleted' % user.username)

    flask.g.user = None
    flask.session['user_id'] = user.id


def log_out():
    """
    Ends the current Flask session.
    """
    flask.g.user = None
    flask.session.clear()
