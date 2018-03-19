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
from imageserver.flask_util import api_permission_required, external_url_for
from imageserver.models import (
    Group, SystemPermissions,
    Folio, FolioExport, FolioImage, FolioPermission, FolioHistory
)
from imageserver.portfolios.util import get_portfolio_image_attrs
from imageserver.session_manager import get_session_user, get_session_user_id
from imageserver.util import (
    object_to_dict, object_to_dict_list,
    parse_boolean, parse_int, validate_number, validate_string
)
from imageserver.views_util import url_for_image_attrs


class PortfolioAPI(MethodView):
    """
    Provides the REST API to get, create or update portfolios.

    Required access:
    - folios system permission for POST
    - Ownership or View access to the portfolio for GET
    - Ownership of the portfolio for PUT and DELETE
    - Or alternatively admin_folios system permission

    Note that portfolios can be made viewable for public users, so
    unlike most of the "admin" type APIs these URLs have require_login=False.
    """
    @add_api_error_handler
    def get(self, folio_id=None):
        if folio_id is None:
            # List portfolios that the user can view
            folio_list = data_engine.list_portfolios(
                get_session_user(),
                FolioPermission.ACCESS_VIEW
            )
            folio_list = [_prep_folio_object(f) for f in folio_list]
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
            folio = _prep_folio_object(folio)
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
            # Return a clean object the same as for get(id)
            folio = data_engine.get_portfolio(folio.id, load_images=True, load_history=True)
            folio = _prep_folio_object(folio)
            return make_api_success_response(object_to_dict(folio))
        finally:
            db_session.close()

    @add_api_error_handler
    def put(self, folio_id):
        db_session = data_engine.db_get_session()
        try:
            # Get portfolio
            folio = data_engine.get_portfolio(folio_id, _db_session=db_session)
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
            data_engine.add_portfolio_history(
                folio,
                get_session_user(),
                FolioHistory.ACTION_EDITED,
                ', '.join(changes).capitalize(),
                _db_session=db_session,
                _commit=False
            )
            data_engine.save_object(
                folio,
                _db_session=db_session,
                _commit=True  # fail here if human_id not unique
            )
            if permissions_changed:
                permissions_engine.reset_portfolio_permissions()
            # Return a clean object the same as for get(id)
            folio = data_engine.get_portfolio(folio.id, load_images=True, load_history=True)
            folio = _prep_folio_object(folio)
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


class PortfolioContentAPI(MethodView):
    """
    Provides the REST API to add, remove, and change (e.g. crop) images in a
    portfolio.

    Required access:
    - Ownership or View access to the portfolio for GET
    - Ownership of the portfolio for POST, PUT and DELETE
    - Or alternatively admin_folios system permission

    Note that portfolios can be made viewable for public users, so
    unlike most of the "admin" type APIs these URLs have require_login=False.
    """
    @add_api_error_handler
    def get(self, folio_id, image_id=None):
        if image_id is None:
            # List images in the portfolio
            folio = data_engine.get_portfolio(folio_id, load_images=True)
            if folio is None:
                raise DoesNotExistError(str(folio_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio, FolioPermission.ACCESS_VIEW, get_session_user()
            )
            image_list = [_prep_folioimage_object(fi) for fi in folio.images]
            return make_api_success_response(object_to_dict_list(image_list))
        else:
            # Get a single portfolio-image
            db_session = data_engine.db_get_session()
            try:
                folio = data_engine.get_portfolio(folio_id, _db_session=db_session)
                if folio is None:
                    raise DoesNotExistError(str(folio_id))
                image = data_engine.get_image(image_id, _db_session=db_session)
                if image is None:
                    raise DoesNotExistError(str(image_id))
                folio_image = data_engine.get_portfolio_image(folio, image, _db_session=db_session)
                if folio_image is None:
                    raise DoesNotExistError(str(folio_id) + '/' + str(image_id))
                # Check permissions
                permissions_engine.ensure_portfolio_permitted(
                    folio, FolioPermission.ACCESS_VIEW, get_session_user()
                )
                return make_api_success_response(object_to_dict(
                    _prep_folioimage_object(folio_image)
                ))
            finally:
                db_session.close()


class PortfolioReorderAPI(MethodView):
    """
    Provides the REST API to reorder the images in a portfolio.

    Required access:
    - Ownership of the portfolio
    - Or alternatively admin_folios system permission
    """
    @add_api_error_handler
    def put(self, folio_id, image_id):
        db_session = data_engine.db_get_session()
        try:
            # Get data objects
            folio = data_engine.get_portfolio(folio_id, _db_session=db_session)
            if folio is None:
                raise DoesNotExistError(str(folio_id))
            image = data_engine.get_image(image_id, _db_session=db_session)
            if image is None:
                raise DoesNotExistError(str(image_id))
            folio_image = data_engine.get_portfolio_image(folio, image, _db_session=db_session)
            if folio_image is None:
                raise DoesNotExistError(str(folio_id) + '/' + str(image_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Update the portfolio
            params = self._get_validated_object_parameters(request.form)
            updated_folio_image = data_engine.reorder_portfolio(folio_image, params['index'])
            data_engine.add_portfolio_history(
                folio,
                get_session_user(),
                FolioHistory.ACTION_IMAGE_CHANGE,
                '%s moved to position %d' % (image.src, updated_folio_image.order_num + 1),
                _db_session=db_session,
                _commit=True
            )
            # Return the updated image list
            folio = data_engine.get_portfolio(folio_id, load_images=True, _db_session=db_session)
            image_list = [_prep_folioimage_object(fi) for fi in folio.images]
            return make_api_success_response(object_to_dict_list(image_list))
        finally:
            db_session.close()

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'index': parse_int(data_dict['index'])
        }
        validate_number(params['index'], -999999, 999999)
        return params


# API - portfolio export
# /api/v1/portfolios/[portfolio id]/exports/
# /api/v1/portfolios/[portfolio id]/exports/[export id]/

# TODO update last_updated for image changes


def _prep_folio_object(folio):
    """
    Modifies a Folio object to add calculated fields.
    """
    # Add attribute for public viewing URL
    folio.url = external_url_for('folios.portfolio_view', human_id=folio.human_id)
    # Add extra fields to the images
    if data_engine.attr_is_loaded(folio, 'images'):
        folio.images = [
            _prep_folioimage_object(fi) for fi in folio.images
        ]
    # Add extra fields to the downloads
    if data_engine.attr_is_loaded(folio, 'downloads'):
        folio.downloads = [
            _prep_folioexport_object(folio, fe) for fe in folio.downloads
        ]
    return folio


def _prep_folioimage_object(folioimage):
    """
    Modifies a FolioImage object to add calculated fields.
    """
    # Add attribute for the image viewing URL
    folioimage.url = url_for_image_attrs(
        get_portfolio_image_attrs(folioimage, validate=False),
        external=True
    )
    return folioimage


def _prep_folioexport_object(folio, folioexport):
    """
    Modifies a FolioExport object to add calculated fields.
    """
    # Add attribute for the download URL
    if folioexport.filename:
        folioexport.url = external_url_for(
            'folios.portfolio_download',
            human_id=folio.human_id,
            filename=folioexport.filename
        )
    else:
        folioexport.url = ''
    return folioexport


# Define portfolio header API views
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

# Define portfolio header API views
_papi_portfoliocontent_views = api_permission_required(
    PortfolioContentAPI.as_view('portfolio.content'),
    require_login=False
)
api_add_url_rules([
        url_version_prefix + '/portfolios/<int:folio_id>/images/',
        '/portfolios/<int:folio_id>/images/'
    ],
    view_func=_papi_portfoliocontent_views,
    methods=['GET', 'POST']
)
api_add_url_rules([
        url_version_prefix + '/portfolios/<int:folio_id>/images/<int:image_id>/',
        '/portfolios/<int:folio_id>/images/<int:image_id>/'
    ],
    view_func=_papi_portfoliocontent_views,
    methods=['GET', 'PUT', 'DELETE']
)

# Define portfolio reordering API views
_papi_portfolioreorder_views = api_permission_required(
    PortfolioReorderAPI.as_view('portfolio.reorder'),
    require_login=False  # Could be True but would be the only portfolio URL returning HTTP 401
)
api_add_url_rules([
        url_version_prefix + '/portfolios/<int:folio_id>/images/<int:image_id>/position/',
        '/portfolios/<int:folio_id>/images/<int:image_id>/position/'
    ],
    view_func=_papi_portfolioreorder_views,
    methods=['PUT']
)
