#
# Quru Image Server
#
# Document:      __init__.py
# Date started:  6 Dec 2011
# By:            Matt Fozard
# Purpose:       Image server API blueprint initialiser
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

# Define the API blueprint
blueprint = Blueprint('api', __name__, static_folder='static', template_folder='templates')

# Current API version (for URL routing)
url_version_prefix = '/v1'


# Support definition of multiple URL rules per view (for API versioning)
def api_add_url_rules(rules, endpoint=None, view_func=None, **options):
    if isinstance(rules, basestring):
        rules = [rules]
    for rule in rules:
        blueprint.add_url_rule(rule, endpoint, view_func, **options)


# Import API views
import views_data_api
import views_files_api
import views_tasks_api
import views_api
import views_pages
