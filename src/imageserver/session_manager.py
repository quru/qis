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

from .flask_app import cache_engine, data_engine, logger
from .errors import DoesNotExistError, SecurityError
from .models import User


# Caching the user object and its groups for very long feels dangerous
# so we'll use a fairly short timeout of 10 minutes
_USER_CACHE_TIMEOUT_SECS = 600


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
        if 'user' not in flask.g or not flask.g.user:
            # v2.2.1 Loading the user + groups from database is very expensive,
            #        making up 85% of the total request time when serving a cached
            #        image, so we now use the RAM cache to speed this up.
            db_user = _cache_get_session_user(uid)
            if not db_user:
                # We need to go to the database this time
                db_user = data_engine.get_user(uid, load_groups=True, _detach=True)
                if not db_user:
                    raise DoesNotExistError('User no longer exists: ' + str(uid))
                # We don't want the password floating around
                del db_user.password
                # Add to RAM cache ready for subsequent requests
                _cache_set_session_user(db_user)

            # Keep the user object for the length of this request on flask.g.user
            flask.g.user = db_user
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

    _cache_clear_session_user(user.id)
    flask.g.user = None
    flask.session['user_id'] = user.id


def log_out():
    """
    Ends the current Flask session.
    """
    uid = get_session_user_id()
    if uid > 0:
        _cache_clear_session_user(uid)
    flask.g.user = None
    flask.g.http_auth = None
    flask.session.clear()


def reset_user_sessions(users):
    """
    Instructs the session manager that user details have changed
    for either one user or a list of users.
    """
    # Upgrade single user to a list
    if isinstance(users, User):
        users = [users]
    # Reset for all users
    for user in users:
        _cache_clear_session_user(user.id)


def _cache_set_session_user(user):
    """
    Puts a user object into cache for fast retrieval on subsequent requests
    (e.g. measured 0.8ms load from Memcached vs 8ms load from Postgres)
    """
    try:
        cache_engine.raw_put(
            'SESS_USER:%d' % user.id,
            user,
            expiry_secs=_USER_CACHE_TIMEOUT_SECS
        )
    except Exception as e:
        logger.error(
            'Session manager: Failed to cache user details: ' + str(e)
        )


def _cache_get_session_user(user_id):
    """
    Returns the cached user object for a given user ID,
    or None if the user object is not in cache.
    """
    try:
        return cache_engine.raw_get('SESS_USER:%d' % user_id)
    except Exception as e:
        logger.error(
            'Session manager: Failed to retrieve cached user details: ' + str(e)
        )
        return None


def _cache_clear_session_user(user_id):
    """
    Removes the cache entry for the given user ID.
    """
    cache_engine.raw_delete('SESS_USER:%d' % user_id)
