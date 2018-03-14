#
# Quru Image Server
#
# Document:      views_portfolios_api.py
# Date started:  7 Mar 2018
# By:            Matt Fozard
# Purpose:       API for managing and handling portfolios
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

from flask import request
from flask.views import MethodView

from imageserver.api import api_add_url_rules, url_version_prefix
from imageserver.api_util import add_api_error_handler, add_parameter_error_handler
from imageserver.api_util import make_api_success_response
from imageserver.errors import DoesNotExistError
from imageserver.filesystem_manager import (
    delete_dir, get_portfolio_directory, get_portfolio_export_file_path
)
from imageserver.flask_app import data_engine, permissions_engine
from imageserver.flask_util import api_permission_required
from imageserver.models import (
    Group, SystemPermissions,
    Folio, FolioExport, FolioImage, FolioPermission, FolioHistory
)
from imageserver.session_manager import get_session_user, get_session_user_id
from imageserver.util import object_to_dict, object_to_dict_list
from imageserver.util import parse_boolean, parse_int
from imageserver.util import validate_number, validate_string


class PortfolioAPI(MethodView):
    """
    Provides the REST API to get, create or update portfolios.

    Required access:
    - folios system permission for POST
    - Ownership or View access to the portfolio for GET
    - Ownership of the portfolio for PUT and DELETE
    - Or alternatively admin_folios system permission

    Note that portfolios can be made viewable for public users, so unlike most
    of the "admin" type APIs, several of these URLs have require_login=False.
    """
    @add_api_error_handler
    def get(self, folio_id=None):
        if folio_id is None:
            # List portfolios that the user can view
            folio_list = data_engine.list_portfolios(
                get_session_user(),
                FolioPermission.ACCESS_VIEW
            )
            folio_list = [self._prep_folio_object(f) for f in folio_list]
            return make_api_success_response(object_to_dict_list(folio_list))
        else:
            # Get single portfolio
            folio = data_engine.get_portfolio(folio_id, load_images=True, load_history=True)
            if folio is None:
                raise DoesNotExistError(str(folio_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio, FolioPermission.ACCESS_VIEW, get_session_user()
            )
            folio = self._prep_folio_object(folio)
            return make_api_success_response(object_to_dict(folio))

    @add_api_error_handler
    def post(self):
        # Require folios or admin_folios permission to create a portfolio
        permissions_engine.ensure_permitted(
            SystemPermissions.PERMIT_FOLIOS, get_session_user()
        )
        db_session = data_engine.db_get_session()
        try:
            params = self._get_validated_object_parameters(request.form)
            folio = Folio(
                params['human_id'] or Folio.create_human_id(),
                params['name'],
                params['description'],
                get_session_user()
            )
            self._set_permissions(folio, params, db_session)
            data_engine.create_portfolio(
                folio,
                get_session_user(),
                _db_session=db_session,
                _commit=True  # fail here if human_id not unique
            )
            folio = self._prep_folio_object(folio, db_session)
            return make_api_success_response(object_to_dict(folio))
        finally:
            db_session.close()

    @add_api_error_handler
    def put(self, folio_id):
        db_session = data_engine.db_get_session()
        try:
            # Get portfolio
            folio = data_engine.get_portfolio(
                folio_id, load_images=True, load_history=True, _db_session=db_session
            )
            if folio is None:
                raise DoesNotExistError(str(folio_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Update the object
            params = self._get_validated_object_parameters(request.form)
            permissions_changed = self._set_permissions(folio, params, db_session)
            changes = []
            if params['human_id'] != folio.human_id:
                changes.append('short URL changed')
            if params['name'] != folio.name:
                changes.append('name changed')
            if params['description'] != folio.description:
                changes.append('description changed')
            if permissions_changed:
                changes.append('permissions changed')
            folio.human_id = params['human_id'] or Folio.create_human_id()
            folio.name = params['name']
            folio.description = params['description']
            # Note: folio.last_updated is only for image changes
            #       (to know when to invalidate the exported zips)
            folio.history.append(data_engine.add_portfolio_history(
                folio,
                get_session_user(),
                FolioHistory.ACTION_EDITED,
                ', '.join(changes).capitalize(),
                _db_session=db_session,
                _commit=False
            ))
            data_engine.save_object(
                folio,
                _db_session=db_session,
                _commit=True  # fail here if human_id not unique
            )
            if permissions_changed:
                permissions_engine.reset_portfolio_permissions()
            folio = self._prep_folio_object(folio, db_session)
            return make_api_success_response(object_to_dict(folio))
        finally:
            db_session.close()

    @add_api_error_handler
    def delete(self, folio_id):
        # Get portfolio
        folio = data_engine.get_portfolio(folio_id)
        if folio is None:
            raise DoesNotExistError(str(folio_id))
        # Check permissions
        permissions_engine.ensure_portfolio_permitted(
            folio, FolioPermission.ACCESS_DELETE, get_session_user()
        )
        # Double check the downloads were eager-loaded before we try to use them below
        if not data_engine.attr_is_loaded(folio, 'downloads'):
            raise ValueError('bug: folio.downloads should be present')
        # Delete - cascades to folio images, permissions, history, and exports
        data_engine.delete_object(folio)
        # If we got this far the database delete worked and we now need to
        # delete the exported zip files (if any)
        delete_dir(get_portfolio_directory(folio), recursive=True)
        return make_api_success_response()

    def _prep_folio_object(self, folio, db_session=None):
        """
        Modifies a Folio object to add calculated fields, remove private fields,
        and prevent recursion when serializing the object. If the object is loaded
        into a database session, provide the session so that the object can be
        detached from it, to prevent the object changes from being persisted.
        """
        if db_session:
            db_session.expunge(folio)
        # TODO need one of these for each affected model? make staticmethod or move
        # TODO add url attributes
        # TODO wipe out user passwords
        # TODO prevent recursion
        return folio

    def _set_permissions(self, folio, params, db_session):
        """
        Sets portfolio permissions from the params and returns whether the
        previous permissions were changed.
        """
        changed = False
        param_names = {
            Group.ID_PUBLIC: 'public_access',
            Group.ID_EVERYONE: 'internal_access'
        }
        for group_id in param_names:
            access_level = params[param_names[group_id]]
            current_perm = [fp for fp in folio.permissions if fp.group_id == group_id]
            if not current_perm:
                # Add missing folder permission for group
                db_group = data_engine.get_group(group_id, _db_session=db_session)
                if db_group is None:
                    raise DoesNotExistError(param_names[group_id] + ' group')
                changed = True
                folio.permissions.append(FolioPermission(folio, db_group, access_level))
            else:
                # Update the existing folder permission for group
                fp = current_perm[0]
                changed = changed or (fp.access != access_level)
                fp.access = access_level
        return changed

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'human_id': data_dict.get('human_id', '').strip(),
            'name': data_dict['name'],
            'description': data_dict['description'],
            'internal_access': parse_int(data_dict['internal_access']),
            'public_access': parse_int(data_dict['public_access'])
        }
        if params['human_id']:
            validate_string(params['human_id'], 1, 64)
        validate_string(params['name'], 0, 255)
        validate_string(params['description'], 0, 5 * 1024)
        # For the first release of portfolios we're limiting access to <= DOWNLOAD
        validate_number(params['internal_access'],
                        FolioPermission.ACCESS_NONE, FolioPermission.ACCESS_DOWNLOAD)
        validate_number(params['public_access'],
                        FolioPermission.ACCESS_NONE, FolioPermission.ACCESS_DOWNLOAD)
        return params

# API - portfolio headers
# /api/v1/portfolios/
# /api/v1/portfolios/[portfolio id]/

# API - portfolio content management
# /api/v1/portfolios/[portfolio id]/images/
# /api/v1/portfolios/[portfolio id]/images/[image id]/
# /api/v1/portfolios/[portfolio id]/images/[image id]/position/

# API - portfolio export
# /api/v1/portfolios/[portfolio id]/exports/
# /api/v1/portfolios/[portfolio id]/exports/[export id]/

# TODO update last_updated for image changes
#      add unit tests

# TODO add tests to ensure password not in user fields

# TODO require login for add/remove/reorder URLs x2
#      unless this is too inconsistent

_papi_portfolio_views = api_permission_required(
    PortfolioAPI.as_view('portfolio'),
    require_login=False
)

api_add_url_rules([
        url_version_prefix + '/portfolios/',
        '/portfolios/'
    ],
    view_func=_papi_portfolio_views,
    methods=['GET', 'POST']
)
api_add_url_rules([
        url_version_prefix + '/portfolios/<int:folio_id>/',
        '/portfolios/<int:folio_id>/'
    ],
    view_func=_papi_portfolio_views,
    methods=['GET', 'PUT', 'DELETE']
)
