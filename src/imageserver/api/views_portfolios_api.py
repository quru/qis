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
from datetime import datetime
import json
import sys

from flask import request
from flask.views import MethodView

from . import api_add_url_rules, url_version_prefix
from .helpers import _prep_folio_object, _prep_folioexport_object, _prep_folioimage_object
from imageserver.api_util import (
    api_permission_required, add_api_error_handler,
    add_parameter_error_handler, make_api_success_response
)
from imageserver.errors import DoesNotExistError, ParameterError
from imageserver.filesystem_manager import delete_dir, get_portfolio_directory
from imageserver.filesystem_sync import auto_sync_file
from imageserver.flask_app import data_engine, permissions_engine, task_engine
from imageserver.models import (
    Image, FolderPermission, Group, SystemPermissions, Task,
    Folio, FolioExport, FolioImage, FolioPermission, FolioHistory
)
from imageserver.portfolios.util import delete_portfolio_export
from imageserver.session_manager import get_session_user
from imageserver.template_attrs import TemplateAttrs
from imageserver.util import (
    object_to_dict, object_to_dict_list,
    parse_boolean, parse_int, parse_iso_date, parse_iso_datetime,
    validate_number, validate_string,
    secure_filename, secure_url_fragment, AttrObject
)

# These APIs allow public access, but the user object contains
# information that only admins should see, so filter them out.
_omit_fields = [
    'user', 'owner'
]


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
            return make_api_success_response(
                object_to_dict_list(folio_list, _omit_fields)
            )
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
            return make_api_success_response(
                object_to_dict(folio, _omit_fields)
            )

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
            return make_api_success_response(
                object_to_dict(folio, _omit_fields)
            )
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
            return make_api_success_response(
                object_to_dict(folio, _omit_fields)
            )
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
            if params['human_id'] != secure_url_fragment(params['human_id'], True):
                raise ValueError('human_id is not allowed to contain characters: %<>&.?:/')

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
            return make_api_success_response(
                object_to_dict_list(image_list, _omit_fields)
            )
        else:
            # Get a single portfolio-image
            db_session = data_engine.db_get_session()
            try:
                folio_image = data_engine.get_portfolio_image(
                    AttrObject(id=folio_id), AttrObject(id=image_id),
                    _db_session=db_session
                )
                if folio_image is None:
                    raise DoesNotExistError(str(folio_id) + '/' + str(image_id))
                # Check permissions
                permissions_engine.ensure_portfolio_permitted(
                    folio_image.portfolio, FolioPermission.ACCESS_VIEW, get_session_user()
                )
                return make_api_success_response(object_to_dict(
                    _prep_folioimage_object(folio_image), _omit_fields + ['portfolio']
                ))
            finally:
                db_session.close()

    @add_api_error_handler
    def post(self, folio_id):
        db_session = data_engine.db_get_session()
        try:
            # Get the portfolio
            folio = data_engine.get_portfolio(folio_id, _db_session=db_session)
            if folio is None:
                raise DoesNotExistError(str(folio_id))
            # Check portfolio permissions
            permissions_engine.ensure_portfolio_permitted(
                folio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Get the image by either ID or src
            params = self._get_validated_object_parameters(request.form, True)
            if 'image_id' in params:
                image = data_engine.get_image(params['image_id'], _db_session=db_session)
                if image is None:
                    raise DoesNotExistError(str(params['image_id']))
            else:
                image = auto_sync_file(
                    params['image_src'],
                    data_engine, task_engine,
                    anon_history=True, burst_pdf=False,
                    _db_session=db_session
                )
                if image is None or image.status == Image.STATUS_DELETED:
                    raise DoesNotExistError(params['image_src'])
            # Check image permissions
            permissions_engine.ensure_folder_permitted(
                image.folder,
                FolderPermission.ACCESS_VIEW,
                get_session_user(),
                False
            )
            # Add history first so that we only commit once at the end
            data_engine.add_portfolio_history(
                folio,
                get_session_user(),
                FolioHistory.ACTION_IMAGE_CHANGE,
                '%s added' % image.src,
                _db_session=db_session,
                _commit=False
            )
            # Flag that exported zips are now out of date
            folio.last_updated = datetime.utcnow()
            # Add the image and commit changes
            db_folio_image = data_engine.save_object(FolioImage(
                    folio, image,
                    params['image_parameters'],
                    params['filename'],
                    params['index']
                ),
                refresh=True,
                _db_session=db_session,
                _commit=True
            )
            return make_api_success_response(object_to_dict(
                _prep_folioimage_object(db_folio_image), _omit_fields + ['portfolio']
            ))
        finally:
            db_session.close()

    @add_api_error_handler
    def put(self, folio_id, image_id):
        db_session = data_engine.db_get_session()
        try:
            folio_image = data_engine.get_portfolio_image(
                AttrObject(id=folio_id), AttrObject(id=image_id),
                _db_session=db_session
            )
            if folio_image is None:
                raise DoesNotExistError(str(folio_id) + '/' + str(image_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio_image.portfolio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Update the object with any/all parameters that were passed in
            params = self._get_validated_object_parameters(request.form, False)
            changes = []
            affects_zips = False
            if (
                params['image_parameters'] is not None and
                params['image_parameters'] != folio_image.parameters
            ):
                folio_image.parameters = params['image_parameters']
                changes.append('image attributes changed')
                affects_zips = True
            if (
                params['filename'] is not None and
                params['filename'] != folio_image.filename
            ):
                folio_image.filename = params['filename']
                changes.append('filename changed')
                affects_zips = True
            if (
                params['index'] is not None and
                params['index'] != folio_image.order_num
            ):
                folio_image.order_num = params['index']
                changes.append('set as position %d' % (params['index'] + 1))
            if changes:
                # Flag if exported zips will be out of date
                if affects_zips:
                    folio_image.portfolio.last_updated = datetime.utcnow()
                # Add history and commit changes
                data_engine.add_portfolio_history(
                    folio_image.portfolio,
                    get_session_user(),
                    FolioHistory.ACTION_IMAGE_CHANGE,
                    '%s updated: %s' % (folio_image.image.src, ', '.join(changes)),
                    _db_session=db_session,
                    _commit=True
                )
            return make_api_success_response(object_to_dict(
                _prep_folioimage_object(folio_image), _omit_fields + ['portfolio']
            ))
        finally:
            db_session.close()

    @add_api_error_handler
    def delete(self, folio_id, image_id):
        db_session = data_engine.db_get_session()
        try:
            folio_image = data_engine.get_portfolio_image(
                AttrObject(id=folio_id), AttrObject(id=image_id),
                _db_session=db_session
            )
            if folio_image is None:
                raise DoesNotExistError(str(folio_id) + '/' + str(image_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio_image.portfolio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Add history first so that we only commit once at the end
            folio = folio_image.portfolio
            data_engine.add_portfolio_history(
                folio,
                get_session_user(),
                FolioHistory.ACTION_IMAGE_CHANGE,
                '%s removed' % folio_image.image.src,
                _db_session=db_session,
                _commit=False
            )
            # Flag that exported zips will be out of date
            folio.last_updated = datetime.utcnow()
            # Delete the image from the portfolio and commit changes
            data_engine.delete_object(
                folio_image,
                _db_session=db_session,
                _commit=True
            )
            return make_api_success_response()
        finally:
            db_session.close()

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict, adding):
        params = {
            'filename': data_dict.get('filename'),
            'index': data_dict.get('index'),
            'image_parameters': data_dict.get('image_parameters')
        }
        if adding:
            # Require either image_id or image_src
            if data_dict.get('image_id') and data_dict.get('image_src'):
                raise ValueError('specify only one of either image_id or image_src')
            elif data_dict.get('image_id'):
                params['image_id'] = parse_int(data_dict['image_id'])
                validate_number(params['image_id'], 1, sys.maxsize)
            elif data_dict.get('image_src'):
                params['image_src'] = data_dict['image_src'].strip()
                validate_string(params['image_src'], 5, 1024)
            else:
                raise KeyError('image_id or image_src')
            # Get or default all the others
            params['filename'] = params['filename'] or ''
            params['index'] = parse_int(params['index']) if params['index'] else 0
            params['image_parameters'] = params['image_parameters'] or '{}'
        else:
            # All parameters optional, if not supplied we leave the values unchanged
            if params['index']:
                params['index'] = parse_int(params['index'])

        if params['filename'] is not None:
            validate_string(params['filename'], 0, 255)
            if params['filename']:
                # Zips only support ASCII filenames, block directory traversal attempts
                sec_filename = secure_filename(params['filename'])
                if sec_filename != params['filename']:
                    # We could continue with the secured filename, but the caller won't
                    # expect the filename to change, so be consistent and just fail it
                    raise ValueError('filename not allowed, try: ' + sec_filename)
        if params['index'] is not None:
            validate_number(params['index'], -999999, 999999)
        if params['image_parameters'] is not None:
            validate_string(params['image_parameters'], 2, 100 * 1024)
            params['image_parameters'] = _image_params_to_template_dict(
                params['image_parameters']
            )
        return params


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
            # Get data
            folio_image = data_engine.get_portfolio_image(
                AttrObject(id=folio_id), AttrObject(id=image_id),
                _db_session=db_session
            )
            if folio_image is None:
                raise DoesNotExistError(str(folio_id) + '/' + str(image_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio_image.portfolio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Update the portfolio
            params = self._get_validated_object_parameters(request.form)
            chd_folio_image = data_engine.reorder_portfolio(folio_image, params['index'])
            data_engine.add_portfolio_history(
                folio_image.portfolio,
                get_session_user(),
                FolioHistory.ACTION_IMAGE_CHANGE,
                '%s moved to position %d' % (folio_image.image.src, chd_folio_image.order_num + 1),
                _db_session=db_session,
                _commit=True
            )
            # Return the updated image list
            folio = data_engine.get_portfolio(folio_id, load_images=True, _db_session=db_session)
            image_list = [_prep_folioimage_object(fi) for fi in folio.images]
            return make_api_success_response(
                object_to_dict_list(image_list, _omit_fields + ['portfolio'])
            )
        finally:
            db_session.close()

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'index': parse_int(data_dict['index'])
        }
        validate_number(params['index'], -999999, 999999)
        return params


class PortfolioExportAPI(MethodView):
    """
    Provides the REST API to publish and unpublish the images in a portfolio.

    Required access:
    - Ownership or View access to the portfolio for GET
    - Ownership of the portfolio for POST and DELETE
    - Or alternatively admin_folios system permission

    Note that portfolios can be made viewable for public users, so
    unlike most of the "admin" type APIs these URLs have require_login=False.
    """
    @add_api_error_handler
    def get(self, folio_id, export_id=None):
        # Get the portfolio
        folio = data_engine.get_portfolio(folio_id)
        if folio is None:
            raise DoesNotExistError(str(folio_id))
        # Check permissions
        permissions_engine.ensure_portfolio_permitted(
            folio, FolioPermission.ACCESS_VIEW, get_session_user()
        )
        if export_id is None:
            # List portfolio exports
            exports_list = [_prep_folioexport_object(folio, fe) for fe in folio.downloads]
            return make_api_success_response(
                object_to_dict_list(exports_list, _omit_fields)
            )
        else:
            # Get a single portfolio-export
            folio_export = data_engine.get_object(FolioExport, export_id)
            if folio_export is None:
                raise DoesNotExistError(str(export_id))
            if folio_export.folio_id != folio_id:
                raise ParameterError(
                    'export ID %d does not belong to portfolio ID %d' % (export_id, folio_id)
                )
            return make_api_success_response(object_to_dict(
                _prep_folioexport_object(folio, folio_export), _omit_fields
            ))

    @add_api_error_handler
    def post(self, folio_id):
        db_session = data_engine.db_get_session()
        try:
            # Get the portfolio
            folio = data_engine.get_portfolio(folio_id, _db_session=db_session)
            if folio is None:
                raise DoesNotExistError(str(folio_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Block the export now if it would create an empty zip file
            if len(folio.images) == 0:
                raise ParameterError('this portfolio is empty and cannot be published')
            # Create a folio-export record and start the export as a background task
            params = self._get_validated_object_parameters(request.form)
            folio_export = FolioExport(
                folio,
                params['description'],
                params['originals'],
                params['image_parameters'],
                params['expiry_time']
            )
            data_engine.add_portfolio_history(
                folio,
                get_session_user(),
                FolioHistory.ACTION_PUBLISHED,
                folio_export.describe(True),
                _db_session=db_session,
                _commit=False
            )
            folio_export = data_engine.save_object(
                folio_export,
                refresh=True,
                _db_session=db_session,
                _commit=True
            )
            export_task = task_engine.add_task(
                get_session_user(),
                'Export portfolio %d / export %d' % (folio.id, folio_export.id),
                'export_portfolio', {
                    'export_id': folio_export.id,
                    'ignore_errors': False
                },
                Task.PRIORITY_NORMAL,
                'info', 'error', 60
            )
            # Update and return the folio-export record with the task ID
            folio_export.task_id = export_task.id
            data_engine.save_object(folio_export, _db_session=db_session, _commit=True)
            return make_api_success_response(object_to_dict(
                _prep_folioexport_object(folio, folio_export), _omit_fields + ['portfolio']
            ), task_accepted=True)
        finally:
            db_session.close()

    @add_api_error_handler
    def delete(self, folio_id, export_id):
        db_session = data_engine.db_get_session()
        try:
            # Get the portfolio
            folio = data_engine.get_portfolio(folio_id, _db_session=db_session)
            if folio is None:
                raise DoesNotExistError(str(folio_id))
            # Check permissions
            permissions_engine.ensure_portfolio_permitted(
                folio, FolioPermission.ACCESS_EDIT, get_session_user()
            )
            # Get the single portfolio-export
            folio_export = data_engine.get_object(FolioExport, export_id, _db_session=db_session)
            if folio_export is None:
                raise DoesNotExistError(str(export_id))
            if folio_export.folio_id != folio_id:
                raise ParameterError(
                    'export ID %d does not belong to portfolio ID %d' % (export_id, folio_id)
                )
            # Delete it and the export files
            delete_portfolio_export(
                folio_export,
                get_session_user(),
                'Deleted: ' + folio_export.describe(True),
                _db_session=db_session
            )
            return make_api_success_response()
        finally:
            db_session.close()

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'description': data_dict['description'],
            'originals': parse_boolean(data_dict['originals']),
            'image_parameters': data_dict.get('image_parameters', '{}'),
            'expiry_time': parse_iso_date(data_dict['expiry_time'])
        }
        if len(data_dict['expiry_time']) >= 19:
            # It looks like expiry_time has a time part
            params['expiry_time'] = parse_iso_datetime(data_dict['expiry_time'])

        validate_string(params['description'], 0, 5 * 1024)
        validate_string(params['image_parameters'], 2, 100 * 1024)
        params['image_parameters'] = _image_params_to_template_dict(
            params['image_parameters']
        )
        if params['expiry_time'] < datetime.utcnow():
            raise ValueError('expiry time (UTC) has already passed')
        return params


def _image_params_to_template_dict(json_str):
    """
    Parses and validates image parameters JSON, which is expected to be in the
    same format as defined for image templates, returning the validated values
    as an image template dictionary.

    Raises a ValueError if the supplied string is not valid JSON, if the JSON
    does not conform to image template format, or if any of the image parameters
    have invalid values.
    """
    try:
        image_template_dict = json.loads(json_str)
    except ValueError as e:
        raise ValueError('image parameters: ' + str(e))
    # Validate the JSON data as conforming to image template syntax
    _ = TemplateAttrs('Portfolio', image_template_dict)
    # If that worked, the dict is valid
    return image_template_dict


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

# Define portfolio content API views
_papi_portfoliocontent_views = api_permission_required(
    PortfolioContentAPI.as_view('portfolio-content'),
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
    PortfolioReorderAPI.as_view('portfolio-reorder'),
    require_login=False  # Could be True but would be the only URL returning HTTP 401
)
api_add_url_rules([
        url_version_prefix + '/portfolios/<int:folio_id>/images/<int:image_id>/position/',
        '/portfolios/<int:folio_id>/images/<int:image_id>/position/'
    ],
    view_func=_papi_portfolioreorder_views,
    methods=['PUT']
)

# Define portfolio export API views
_papi_portfolioexport_views = api_permission_required(
    PortfolioExportAPI.as_view('portfolio-export'),
    require_login=False
)
api_add_url_rules([
        url_version_prefix + '/portfolios/<int:folio_id>/exports/',
        '/portfolios/<int:folio_id>/exports/'
    ],
    view_func=_papi_portfolioexport_views,
    methods=['GET', 'POST']
)
api_add_url_rules([
        url_version_prefix + '/portfolios/<int:folio_id>/exports/<int:export_id>/',
        '/portfolios/<int:folio_id>/exports/<int:export_id>/'
    ],
    view_func=_papi_portfolioexport_views,
    methods=['GET', 'DELETE']
)
