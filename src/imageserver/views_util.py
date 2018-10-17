#
# Quru Image Server
#
# Document:      views_util.py
# Date started:  10 Aug 2011
# By:            Matt Fozard
# Purpose:       Custom template tags, filters, and decorators
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
# 10Aug2011  Matt  Created from the filters in views_pages.py
# 01Apr2015  Matt  Added markdown filter
# 17Oct2018  Matt  Moved view decorators in here from flask_util
#

import time
from calendar import timegm
from collections import OrderedDict
from datetime import datetime
from functools import wraps

import markdown
from flask import make_response, redirect, request, session
from jinja2 import Markup
from werkzeug.urls import url_encode, url_quote_plus

from . import __about__
from . import imaging
from .api_util import make_api_error_response
from .errors import AuthenticationError, SecurityError
from .flask_app import app, logger, permissions_engine
from .flask_util import get_port, internal_url_for, external_url_for
from .models import FolderPermission, SystemPermissions
from .session_manager import get_session_user, logged_in
from .util import get_file_extension, filepath_filename, unicode_to_utf8


@app.template_filter('datetimeformat')
def datetimeformat_filter(utc_val, to_local_time=False, date_format='ymd', show_time=True):
    """
    A template filter to convert either a UTC datetime instance or a time
    supplied as UTC seconds. Returns a formatted string of the UTC date and
    time, or the date and time in the local timezone (if to_local_time is True).
    The date format can be: 'ymd', 'dmy', or 'mdy'.
    """
    secs = timegm(utc_val.timetuple()) if isinstance(utc_val, datetime) else utc_val
    tval = time.localtime(secs) if to_local_time else time.gmtime(secs)
    if date_format == 'ymd':
        fmt = '%Y-%m-%d' + (' %H:%M' if show_time else '')
    elif date_format == 'dmy':
        fmt = '%d/%m/%Y' + (' %H:%M' if show_time else '')
    elif date_format == 'mdy':
        fmt = '%m/%d/%Y' + (' %I:%M%p' if show_time else '')
    else:
        raise ValueError('Invalid date format parameter value')
    return time.strftime(fmt, tval)


@app.template_filter('dateformat')
def dateformat_filter(utc_val, to_local_time=False, date_format='ymd'):
    """
    A shortcut to call the datetimeformat filter with show_time as False.
    """
    return datetimeformat_filter(utc_val, to_local_time, date_format, False)


@app.template_filter('urlencode')
def urlencode_filter(strval):
    """
    A template filter to return a URL-encoded string.
    """
    return url_quote_plus(strval)


@app.template_filter('fileextension')
def file_extension_filter(filename):
    """
    A template filter to return the lower case file extension of a file name.
    """
    return get_file_extension(filename)


@app.template_filter('filename')
def filename_filter(filepath):
    """
    A template filter to return the last part of a file path.
    """
    return filepath_filename(filepath)


@app.template_filter('decamelcase')
def de_camelcase_filter(cc):
    """
    A template filter to add spaces to a CamelCase word, so that e.g.
    "MyXYZWord" becomes "My XYZ Word" and "ArticleBy-line" becomes "Article Byline"
    """
    ret = ''
    len_cc = len(cc)
    for i in range(0, len_cc):
        if cc[i].isupper() and (i > 0) and (i < len_cc-1) and (
            not cc[i-1].isupper() or not cc[i+1].isupper()
        ):
            ret += ' '
        ret += cc[i]
    return ret.replace('-', '')


@app.template_filter('newlines')
def newlines_filter(text):
    """
    A template filter to convert newline characters in a string to HTML <br>.
    """
    if text is None:
        return text
    else:
        return Markup(text.replace('\r', '').replace('\n', '<br/>'))


@app.template_filter('pluralize')
def pluralize_filter(num, singular='', plural='s'):
    """
    A filter to output one string (default nothing) or another (default 's')
    depending on whether the provided number is 1 or not.
    """
    return singular if num == 1 else plural


@app.template_filter('markdown')
def markdown_filter(md_text):
    """
    A filter to return a unicode html string from a unicode markdown string.
    Only unicode strings are supported!
    """
    return Markup(markdown.markdown(md_text, output_format='html5'))


@app.context_processor
def inject_template_vars():
    """
    Sets the custom variables that are available inside templates.
    """
    return {
        'about': __about__,
        'settings': app.config,
        'logged_in': logged_in(),
        'user': get_session_user(),
        'FolderPermission': FolderPermission,
        'SystemPermission': SystemPermissions
    }


def register_template_funcs():
    """
    Sets the custom functions to make available inside templates.
    """
    app.add_template_global(app_edition, 'app_edition')
    app.add_template_global(wrap_is_permitted, 'is_permitted')
    app.add_template_global(wrap_is_folder_permitted, 'is_folder_permitted')
    app.add_template_global(internal_url_for, 'url_for')
    app.add_template_global(external_url_for, 'external_url_for')
    app.add_template_global(url_for_thumbnail, 'url_for_thumbnail')


def app_edition():
    """
    Returns whether the application is running in "Standard" or "Premium" mode.
    """
    return "Premium" if imaging.get_backend() == "imagemagick" else "Standard"


def wrap_is_permitted(flag):
    """
    Provides a template function to return whether the current user has been
    granted a particular system permission.
    """
    return permissions_engine.is_permitted(
        flag, get_session_user()
    )


def wrap_is_folder_permitted(folder, folder_access):
    """
    Provides a template function to return whether the current user has a
    particular access level to a folder.
    """
    return permissions_engine.is_folder_permitted(
        folder, folder_access, get_session_user()
    )


def url_for_thumbnail(src, external=False, stats=True):
    """
    Returns the URL for a thumbnail image of an image src. Use this function to
    generate standard-sized and standard-formatted thumbnail images in the UI
    so that they are re-used from cache when possible.
    Note that the order of the parameters in the returned URL cannot be relied
    upon in Python versions below 3.6.
    """
    url_args = OrderedDict()  # Order of **url_args is only preserved in Python 3.6+
    url_args['src'] = src
    url_args['width'] = '200'             # Also update the getPreviewImageURL()
    url_args['height'] = '200'            # function in preview_popup.js
    url_args['format'] = 'jpg'            # if you change any if these...
    url_args['colorspace'] = 'srgb'
    url_args['strip'] = '1'
    if not stats:
        url_args['stats'] = '0'  # stats does not affect caching

    url_fn = external_url_for if external else internal_url_for
    return url_fn('image', **url_args)


def url_for_image_attrs(image_attrs, external=False, stats=True):
    """
    Returns the image URL for the image represented by image_attrs.
    """
    image_attrs.normalise_values()
    url_args = image_attrs.to_web_dict()
    if not stats:
        url_args['stats'] = '0'

    url_fn = external_url_for if external else internal_url_for
    return url_fn('image', **url_args)


def log_security_error(error, request):
    """
    Creates an error log entry and returns true if 'error' is a SecurityError,
    otherwise performs no action and returns false.
    """
    if error and isinstance(error, SecurityError):
        ip = request.remote_addr if request.remote_addr else '<unknown>'
        user = get_session_user()
        logger.error(
            'Security error for %s URL %s for user %s from IP %s : %s' % (
                request.method.upper(),
                request.url,
                user.username if user else '<anonymous>',
                ip,
                unicode_to_utf8(str(error))
            )
        )
        return True
    else:
        return False


def safe_error_str(error):
    """
    Converts an exception or a string to a utf8 string that has any known
    sensitive text (such as secrets from the app config) redacted.
    """
    if not isinstance(error, str):
        error = str(error)
    error = unicode_to_utf8(error)
    # TODO implement me
    return str(error)


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


def _check_internal_request(request, session, from_web, require_login,
                            required_permission_flag=None):
    """
    A low-level component implementing request scheme, port, session and
    optional system permission checking for an "internal" web request.
    Incorporates _check_port and _check_ssl_request.
    Returns a Flask redirect or response if there is a problem, or None on success.
    Responses are returned as HTML when from_web is True, or as JSON when False.
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
                ), logger)
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
                    return make_api_error_response(e, logger)
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
            return make_api_error_response(AuthenticationError(msg), logger)
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
            ), logger)
    return None
