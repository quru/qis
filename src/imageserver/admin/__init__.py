#
# Quru Image Server
#
# Document:      __init__.py
# Date started:  11 Aug 2011
# By:            Matt Fozard
# Purpose:       Image server admin blueprint initialiser
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
#

from flask.blueprints import Blueprint
from flask import request, session

from imageserver import views_util

# Define the admin blueprint
blueprint = Blueprint('admin', __name__, static_folder='static', template_folder='templates')


# Require all admin requests to be logged in with admin permission
# and (if the configuration says so) also be on HTTPS
@blueprint.before_request
def admin_login_required():
    return views_util._check_internal_request(
        request, session, True, True, 'admin_any'
    )

# Import admin views
from . import views_pages
