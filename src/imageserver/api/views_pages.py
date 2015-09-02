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
#

from imageserver.api import blueprint
from imageserver.flask_util import login_required
from imageserver.views_pages import _standard_help_page


# The API help page
@blueprint.route('/help/')
@login_required
def api_help():
    return _standard_help_page('api_help.html')
