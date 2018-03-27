#
# Quru Image Server
#
# Document:      flask_util.py
# Date started:  10 Aug 2011
# By:            Matt Fozard
# Purpose:       Flask-related utilities and helper functions
# Requires:      Flask
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
# 10Aug2011  Matt  Created from the functions in views.py and views_pages.py
# 17Aug2011  Matt  Added SSL support
# 16Nov2012  Matt  Implemented system permissions checking

from functools import wraps

from flask import jsonify, make_response, redirect, request, session, url_for
from flask import render_template as f_render_template
from werkzeug.urls import url_encode

from . import __about__
from .api_util import make_api_error_response
from .flask_app import app, permissions_engine
from .errors import AuthenticationError, SecurityError
from .session_manager import get_session_user, logged_in
from .util import parse_int


def login_point(from_web):
    """
    Defines a decorator specifically for the login page that enforces the
    INTERNAL_BROWSING_PORT and INTERNAL_BROWSING_SSL settings, but does not
    require the user to yet be logged in.
    """
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            res = _check_internal_request(request, session, from_web, False)
            return res if res else f(*args, **kwargs)
        return decorated_function
    return wrapper


def login_required(f):
    """
    Defines a decorator that can be applied to a view function to require
    that the user must be logged in. The user is redirected to the login page
    if they are not logged in.

    This decorator enforces INTERNAL_BROWSING_PORT and INTERNAL_BROWSING_SSL,
    if they are set.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        res = _check_internal_request(request, session, True, True)
        return res if res else f(*args, **kwargs)
    return decorated_function


def ssl_required(f):
    """
    Defines a decorator that can be applied to a view function to require that
    HTTPS is in force. The user is redirected to the same URL path on HTTPS if
    the connection is standard HTTP.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        res = _check_ssl_request(request, True)
        return res if res else f(*args, **kwargs)
    return decorated_function


def api_permission_required(f, require_login=True, required_flag=None):
    """
    Defines a decorator that can be applied to a view function to optionally
    require that the user be logged in (true by default) and optionally require
    the specified system permissions flag.

    An API JSON response is returned if the user is not logged in or does not
    have the required permission flag.

    This decorator also enforces INTERNAL_BROWSING_PORT and INTERNAL_BROWSING_SSL,
    if they are set.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        res = _check_internal_request(request, session, False, require_login, required_flag)
        return res if res else f(*args, **kwargs)
    return decorated_function


def _check_internal_request(request, session, from_web, require_login,
                            required_permission_flag=None):
    """
    A low-level component implementing request scheme, port, session and
    optional system permission checking for an "internal" web request.
    Incorporates _check_port and _check_ssl_request.
    Returns a Flask redirect or response if there is a problem, otherwise None.
    """
    # Check the port first
    if app.config['INTERNAL_BROWSING_PORT']:
        port_response = _check_port(request, app.config['INTERNAL_BROWSING_PORT'], from_web)
        if port_response:
            return port_response
    # Check SSL second, so that if we need to redirect to HTTPS
    # we know we're already on the correct port number
    if app.config['INTERNAL_BROWSING_SSL']:
        ssl_response = _check_ssl_request(request, from_web)
        if ssl_response:
            return ssl_response
    # Check the session is logged in
    if require_login:
        if not logged_in():
            if from_web:
                from_path = request.path
                if len(request.args) > 0:
                    from_path += '?' + url_encode(request.args)
                # Go to login page, redirecting to original destination on success
                return redirect(internal_url_for('login', next=from_path))
            else:
                # Return an error
                return make_api_error_response(AuthenticationError(
                    'You must be logged in to access this function'
                ))
        # Check admin permission
        if required_permission_flag:
            try:
                permissions_engine.ensure_permitted(
                    required_permission_flag, get_session_user()
                )
            except SecurityError as e:
                # Return an error
                if from_web:
                    return make_response(str(e), 403)
                else:
                    return make_api_error_response(e)
    # OK
    return None


def _check_port(request, required_port, from_web):
    """
    A low-level component implementing a request checker that tests the port
    number in use and returns a Flask redirect if required
    (or a JSON error response if not from_web), but otherwise returns None.
    """
    if get_port(request) != required_port:
        msg = 'This URL is not available on port %d' % get_port(request)
        if from_web:
            return make_response(msg, 401)
        else:
            return make_api_error_response(AuthenticationError(msg))
    return None


def _check_ssl_request(request, from_web):
    """
    A low-level component implementing a request checker that tests for HTTPS
    and returns a Flask redirect if required (or a JSON error response if not
    from_web), but otherwise returns None.
    """
    if not request.is_secure:
        if from_web:
            to_url = request.url.replace('http:', 'https:', 1)
            return redirect(to_url)
        else:
            return make_api_error_response(AuthenticationError(
                'HTTPS must be used to access this function'
            ))
    return None


def render_template(template_path, **kwargs):
    """
    Extended version of Flask's render_template function that adds in
    standard/common application parameters.
    """
    return f_render_template(
        template_path,
        about=__about__,
        settings=app.config,
        **kwargs
    )


def make_json_response(status_code, *args, **kwargs):
    """
    Extended version of Flask's jsonify function that allows the
    caller to specify the HTTP status code for the response.
    """
    r = jsonify(*args, **kwargs)
    r.status_code = status_code
    return r


def external_url_for(endpoint, **kwargs):
    """
    Extended version of Flask's url_for function.
    Returns the external URL for the requested end point,
    applying the setting PUBLIC_HOST_NAME if it is defined.

    Note that as at Flask 0.10.1, Flask's SERVER_NAME setting should remain
    set to None to avoid changing the routing behaviour:
    https://github.com/mitsuhiko/flask/issues/998
    """
    scheme = app.config['PREFERRED_URL_SCHEME'] or 'http'
    if app.config['PUBLIC_HOST_NAME']:
        host = app.config['PUBLIC_HOST_NAME']
        approot = app.config['APPLICATION_ROOT'] or '/'
        url = scheme + '://' + host + approot
        if url.endswith('/'):
            url = url[0:-1]
        # Return custom front end URL with Flask back end
        return unescape_url_path_seps(
            url + url_for(endpoint, **kwargs)
        )
    else:
        # Let Flask do it all
        return unescape_url_path_seps(
            url_for(endpoint, _external=True, _scheme=scheme, **kwargs)
        )


def internal_url_for(endpoint, **kwargs):
    """
    Extended version of Flask's url_for function.
    Returns the internal URL for the requested end point,
    applying the setting INTERNAL_BROWSING_PORT if it is defined.
    """
    internal_port = app.config['INTERNAL_BROWSING_PORT']
    if not internal_port or (request and (get_port(request) == internal_port)):
        return unescape_url_path_seps(url_for(endpoint, **kwargs))
    else:
        full_url = url_for(endpoint, _external=True, **kwargs)
        return unescape_url_path_seps(change_url_port(full_url, internal_port))


def change_url_port(full_url, port):
    """
    Takes a complete URL and sets or changes the port number, returning a new URL.
    E.g. Port 8000 applied to URL "http://www.myco.com/mypath" would return
         "http://www.myco.com:8000/mypath"
    """
    scheme_end_idx = full_url.find('//')
    server_end_idx = full_url.find('/', scheme_end_idx + 2)
    if scheme_end_idx != -1 and server_end_idx != -1:
        curr_port_idx = full_url.find(':', scheme_end_idx + 2, server_end_idx)
        curr_port_str = '' if curr_port_idx == -1 else full_url[curr_port_idx:server_end_idx]
        upload_port_str = ':' + str(port)
        if not curr_port_str or curr_port_str != upload_port_str:
            if curr_port_str:
                full_url = full_url.replace(curr_port_str, upload_port_str, 1)
            else:
                full_url = full_url[0:server_end_idx] + upload_port_str + full_url[server_end_idx:]
    return full_url


def unescape_url_path_seps(url):
    """
    The Flask url_for function escapes path separators in the URL query string
    to %2F and %5C. Normally this would be reasonable, except that this appears
    to not be handled correctly by some older browsers.

    It also potentially runs into trouble with Apache's default setting for
    AllowEncodedSlashes (Off) which rejects %2F and %5C in URLs.

    According to http://en.wikipedia.org/wiki/Percent-encoding/
    it is legal to have these characters un-escaped so long as they are after
    the URL path, i.e. part of the query string.

    This function returns the given URL with any escaped path separators
    restored to "/" or "\" in the query string part of the URL.
    """
    q_idx = url.find('?')
    if q_idx != -1:
        url_query = url[q_idx:]
        url_query = url_query.replace("%2F", "/")
        url_query = url_query.replace("%5C", "\\")
        url = url[0:q_idx] + url_query
    return url


def get_port(request):
    """
    Returns the port number in use on a Flask/Werkzeug request object.
    """
    sep_idx = request.host.find(':')
    if sep_idx == -1:
        return 443 if request.is_secure else 80
    else:
        return parse_int(request.host[sep_idx + 1:])
