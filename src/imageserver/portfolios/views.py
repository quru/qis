#
# Quru Image Server
#
# Document:      views.py
# Date started:  09 Mar 2018
# By:            Matt Fozard
# Purpose:       Portfolio access views
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

from flask import request, send_file
import werkzeug.exceptions as httpexc

from imageserver.errors import DoesNotExistError, SecurityError
from imageserver.filesystem_manager import (
    ensure_path_exists, get_abs_path, get_portfolio_export_file_path
)
from imageserver.flask_app import app, logger
from imageserver.flask_app import data_engine, permissions_engine
from imageserver.models import FolioHistory, FolioPermission
from imageserver.portfolios import blueprint
from imageserver.session_manager import get_session_user
from imageserver.views_util import log_security_error


# Portfolio download as a zip file
@blueprint.route('/<string:human_id>/downloads/<string:filename>', methods=['GET'])
def portfolio_download(human_id, filename):
    logger.debug('GET ' + request.url)
    try:
        # Find the portfolio
        folio = data_engine.get_portfolio(human_id=human_id)
        if not folio:
            raise DoesNotExistError('Portfolio \'%s\' does not exist' % human_id)

        # Ensure that the user has permission to download the portfolio
        user = get_session_user()
        permissions_engine.ensure_portfolio_permitted(
            folio,
            FolioPermission.ACCESS_DOWNLOAD,
            user
        )

        # Check that the filename is valid (note: assumes folio.downloads is eager loaded)
        if not filename:
            raise DoesNotExistError('No filename specified')
        folio_exports = [
            dl for dl in folio.downloads if dl.filename == filename
        ]
        if not folio_exports:
            raise DoesNotExistError('Download \'%s\' is not available' % filename)
        folio_export = folio_exports[0]
        # The physical file should always exist when the data+filename exists
        # This also checks that the file path lies inside IMAGES_BASE_DIR
        zip_path = get_portfolio_export_file_path(folio_export)
        ensure_path_exists(zip_path, require_file=True)

        # Prepare to serve the file
        response = send_file(
            get_abs_path(zip_path),
            mimetype='application/zip',
            as_attachment=True,
            conditional=True,
            cache_timeout=31536000  # zips never change once created
        )

        # Lastly write an audit record
        data_engine.add_portfolio_history(
            folio,
            user,
            FolioHistory.ACTION_DOWNLOADED,
            folio_export.filename
        )
        return response

    except httpexc.HTTPException:
        # Pass through HTTP 4xx and 5xx
        raise
    except SecurityError as e:
        if app.config['DEBUG']:
            raise
        log_security_error(e, request)
        raise httpexc.Forbidden()
    except DoesNotExistError as e:
        logger.warn('404 Not found: ' + str(e))
        raise httpexc.NotFound(str(e))
    except Exception as e:
        if app.config['DEBUG']:
            raise
        logger.error('500 Error for ' + request.url + '\n' + str(e))
        raise httpexc.InternalServerError(str(e))
