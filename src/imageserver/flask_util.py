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
# 17Oct2018  Matt  Moved view decorators into views_util

from flask import current_app, jsonify, request, url_for

from .util import parse_int


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
    scheme = current_app.config['PREFERRED_URL_SCHEME'] or 'http'
    if current_app.config['PUBLIC_HOST_NAME']:
        host = current_app.config['PUBLIC_HOST_NAME']
        approot = current_app.config['APPLICATION_ROOT'] or '/'
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
    internal_port = current_app.config['INTERNAL_BROWSING_PORT']
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
