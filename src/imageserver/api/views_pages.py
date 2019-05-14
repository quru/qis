#
# Quru Image Server
#
# Document:      views_pages.py
# Date started:  06 Dec 2011
# By:            Matt Fozard
# Purpose:       API web page URLs and views
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
# 13May2019  Matt  Added token_login - web session login from API token
#

from flask import redirect, request, render_template

import imageserver.flask_ext as flask_ext
import imageserver.session_manager as session_manager
from imageserver.api import blueprint, url_version_prefix
from imageserver.flask_app import app, logger
from imageserver.views_pages import _standard_help_page
from imageserver.views_util import login_point, login_required, log_security_error, safe_error_str


# The API help page
@blueprint.route('/help/')
@login_required
def api_help():
    return _standard_help_page('api_help.html')


# API token to web session converter page
@blueprint.route('/tokenlogin/', methods=['GET'])
@blueprint.route(url_version_prefix + '/tokenlogin/', methods=['GET'])
@login_point(from_web=True)
def token_login():
    err_msg = ''
    token = request.args.get('token', '')
    next_url = request.args.get('next', '')
    try:
        if token:
            token_auth_class = app.config['API_AUTHENTICATION_CLASS']
            auth_cls = getattr(flask_ext, token_auth_class, None)
            if not auth_cls:
                raise ValueError('Class flask_ext.%s was not found' % token_auth_class)
            auth_module = auth_cls(app)
            auth_object = auth_module.decode_auth_token(token)
            if auth_object:
                # The token is valid - set as logged in on the API
                auth_module.set_authenticated(auth_object)
                # Now set as logged in on the web session too
                auth_user = session_manager.get_session_user()
                if not auth_user:
                    raise ValueError(
                        'Internal error - no session user returned - has BaseHttpAuthentication '
                        'or session_manager been changed?'
                    )
                session_manager.log_in(auth_user)
            else:
                err_msg = 'Invalid or expired token'
        else:
            err_msg = 'No token value supplied'

    except Exception as e:
        if not log_security_error(e, request):
            logger.error('Error performing API token to web login: ' + str(e))
        if app.config['DEBUG']:
            raise
        err_msg = 'Sorry, an error occurred. Please try again later.'
        session_manager.log_out()

    if next_url and not err_msg:
        return redirect(next_url)
    else:
        return render_template(
            'token_login.html',
            err_msg=safe_error_str(err_msg)
        )
