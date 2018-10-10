#
# Quru Image Server
#
# Document:      api_util.py
# Date started:  06 Dec 2011
# By:            Matt Fozard
# Purpose:       Developer API public interface definitions and utilities
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

from functools import wraps
import traceback

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from . import errors
from .util import unicode_to_utf8


# Define JSON API return codes and default messages
class API_CODES():
    SUCCESS = 200
    SUCCESS_TASK_ACCEPTED = 202
    INVALID_PARAM = 400
    REQUIRES_AUTH = 401
    UNAUTHORISED = 403
    NOT_FOUND = 404
    METHOD_UNSUPPORTED = 405
    ALREADY_EXISTS = 409
    IMAGE_ERROR = 415
    INTERNAL_ERROR = 500
    TOO_BUSY = 503


API_MESSAGES = {
    200: 'OK',
    202: 'OK task accepted',
    400: 'Invalid parameter',
    401: 'Not authenticated',
    403: 'Unauthorised request',
    404: 'The requested item was not found',
    405: 'Unsupported method',
    409: 'The specified item already exists',
    415: 'Invalid or unsupported image file',
    500: 'Internal error',
    503: 'The server is too busy'
}


def add_api_error_handler(f):
    """
    Defines a decorator that can be applied to a view function to wrap it in
    a try/catch block, and return a standard API JSON response for any
    exceptions raised by the view. Callers may add an 'api_data' attribute to
    the exception to have it returned in the API response's 'data' field.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            from .flask_app import logger
            return make_api_error_response(e, logger)
    return decorated_function


def add_parameter_error_handler(f):
    """
    Defines a decorator that, when applied to a parameter parsing function,
    raises a ParameterError for common exceptions.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            raise errors.ParameterError('Invalid value: ' + str(e))
        except KeyError as e:
            # Try to extract the key info from the Werkzeug exception wrapper
            info = getattr(e, 'message', None) or str(e)
            raise errors.ParameterError('Missing parameter: ' + info)
    return decorated_function


def add_jsonp_support(f):
    """
    Defines a decorator that can be applied to a view function returning JSON
    data to add JSONP support. If the current request object contains a 'jsonp'
    parameter, the JSON response will be wrapped with this value as the JSONP
    callback function and the data type modified to "application/javascript".

    Note that JSONP support is only required for views that are called
    cross-domain, and that CORS is preferred over JSONP. Also when using
    JSONP only the GET verb is supported.

    This decorator should be applied before add_api_error_handler.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_response = f(*args, **kwargs)
        jsonp_fn = request.args.get('jsonp', '')
        if jsonp_fn:
            api_response.mimetype = 'application/javascript'
            api_response.data = jsonp_fn + '(' + api_response.data + ')'
        return api_response
    return decorated_function


def create_api_dict(status_code, status_message, data=None):
    """
    Returns an API standard response dict with the given code, message and data fields.
    """
    return dict(status=status_code, message=status_message, data=data)


def create_api_error_dict(exc, logger=None):
    """
    Returns an API standard response dict for the given exception.
    If the exception has an 'api_data' attribute, this will be returned in
    the response's data value, otherwise the data value will be None.
    If a logger is provided, security errors, bad parameters and unexpected
    errors are also logged.
    """
    err_no = API_CODES.INTERNAL_ERROR
    exc_name = ''
    exc_val = '(none)' if exc is None else unicode_to_utf8(str(exc))

    # Try first for our own exceptions
    if isinstance(exc, errors.ParameterError):
        err_no = API_CODES.INVALID_PARAM
    elif isinstance(exc, errors.AlreadyExistsError):
        err_no = API_CODES.ALREADY_EXISTS
    elif isinstance(exc, errors.DoesNotExistError):
        err_no = API_CODES.NOT_FOUND
    elif isinstance(exc, errors.AuthenticationError):
        err_no = API_CODES.REQUIRES_AUTH
    elif isinstance(exc, errors.ImageError):
        err_no = API_CODES.IMAGE_ERROR
    elif isinstance(exc, errors.SecurityError):
        err_no = API_CODES.UNAUTHORISED
    elif isinstance(exc, errors.ServerTooBusyError):
        err_no = API_CODES.TOO_BUSY
    elif isinstance(exc, HTTPException):
        # It's a Flask/Werkzeug HTTP exception
        err_no = exc.code
        exc_name = exc.name
        exc_val = exc.description

    # Log interesting errors
    if logger is not None:
        if err_no == API_CODES.INVALID_PARAM:
            logger.error('API Parameter error (' + exc_val + ')')
        elif err_no == API_CODES.UNAUTHORISED:
            logger.error('API Security error (' + exc_val + ')')
        elif err_no == API_CODES.INTERNAL_ERROR:
            logger.error('API ' + traceback.format_exc())

    if not exc_name:
        exc_name = API_MESSAGES.get(err_no, 'Unknown Error')

    return create_api_dict(
        err_no,
        exc_name + ' (' + exc_val + ')',
        getattr(exc, 'api_data', None)
    )


def make_api_success_response(data=None, task_accepted=False):
    """
    A shortcut that calls create_api_dict() with data and the success status
    code (HTTP 200 or 202) and creates a JSON response of the result.
    """
    status = API_CODES.SUCCESS_TASK_ACCEPTED if task_accepted else API_CODES.SUCCESS
    return _to_json_response(
        status,
        create_api_dict(
            status,
            API_MESSAGES[status],
            data
        )
    )


def make_api_error_response(exc, logger=None):
    """
    A shortcut that calls create_api_error_dict() and creates a JSON response
    of the result.
    """
    rd = create_api_error_dict(exc, logger)
    return _to_json_response(rd['status'], rd)


def _to_json_response(status_code, response_dict):
    """
    Creates a view response as JSON data.
    """
    jr = jsonify(response_dict)
    jr.status_code = status_code
    # Don't let IE ignore the content type or you might get XSS for HTML text inside the JSON
    jr.headers['X-Content-Type-Options'] = 'nosniff'
    # Legacy browsers - if the API post targets a hidden iframe instead of XHR
    # (bug: request.form.get breaks on 413 errors so skip it for those)
    if status_code != 413 and request.form.get('api_json_as_text', '') == 'true':
        if not request.args.get('jsonp'):
            jr.mimetype = 'text/plain'
            # Force a 200 for IE to render the text instead of an error page
            jr.status_code = 200
    return jr
