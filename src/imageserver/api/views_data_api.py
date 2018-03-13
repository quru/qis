#
# Quru Image Server
#
# Document:      views_data_api.py
# Date started:  08 Feb 2012
# By:            Matt Fozard
# Purpose:       Developer / Admin API for managing database records
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

import copy
from functools import wraps
import json
import sys

from flask import request, session
from flask.views import MethodView

from imageserver.api import api_add_url_rules, url_version_prefix
from imageserver.api_util import add_api_error_handler, add_parameter_error_handler
from imageserver.api_util import make_api_success_response
from imageserver.errors import DoesNotExistError, ParameterError, SecurityError
from imageserver.flask_app import data_engine, image_engine, permissions_engine
from imageserver.flask_util import api_permission_required, _check_internal_request
from imageserver.models import Group, ImageHistory, ImageTemplate, User
from imageserver.models import FolderPermission, Property, SystemPermissions
from imageserver.session_manager import get_session_user, get_session_user_id
from imageserver.session_manager import log_out, reset_user_sessions
from imageserver.template_attrs import TemplateAttrs
from imageserver.util import get_string_changes, generate_password
from imageserver.util import object_to_dict, object_to_dict_list
from imageserver.util import parse_boolean, parse_int
from imageserver.util import validate_number, validate_string


class ImageAPI(MethodView):
    """
    Provides the REST admin API to get or update image database records.

    Required access:
    - View access to the image's folder for GET
    - Edit access to the image's folder for PUT
    - Or alternatively admin_files
    """
    @add_api_error_handler
    def get(self, image_id):
        db_img = data_engine.get_image(image_id=image_id)
        if not db_img:
            raise DoesNotExistError(str(image_id))
        else:
            # Require view permission or file admin
            permissions_engine.ensure_folder_permitted(
                db_img.folder,
                FolderPermission.ACCESS_VIEW,
                get_session_user()
            )
            return make_api_success_response(object_to_dict(db_img))

    @add_api_error_handler
    def put(self, image_id):
        params = self._get_validated_object_parameters(request.form)

        # Get image and update it
        db_img = data_engine.get_image(image_id=image_id)
        if not db_img:
            raise DoesNotExistError(str(image_id))

        # Require edit permission or file admin
        permissions_engine.ensure_folder_permitted(
            db_img.folder,
            FolderPermission.ACCESS_EDIT,
            get_session_user()
        )

        old_title = db_img.title
        old_description = db_img.description
        db_img.title = params['title']
        db_img.description = params['description']
        data_engine.save_object(db_img)

        # Get text changes. Max info length =
        # 100 + 200 + len('()' + '()' + 'Title: ' + ' / ' + 'Description: ') ==> 327
        title_diff = get_string_changes(old_title, params['title'], char_limit=100).strip()
        if not title_diff:
            # Try for deletions from title
            title_diff = get_string_changes(params['title'], old_title, char_limit=100).strip()
            if title_diff:
                title_diff = '(' + title_diff + ')'
        desc_diff = get_string_changes(
            old_description, params['description'], char_limit=200
        ).strip()
        if not desc_diff:
            # Try for deletions from description
            desc_diff = get_string_changes(
                params['description'], old_description, char_limit=200
            ).strip()
            if desc_diff:
                desc_diff = '(' + desc_diff + ')'
        info = ''
        if title_diff:
            info += 'Title: ' + title_diff
        if info and desc_diff:
            info += ' / '
        if desc_diff:
            info += 'Description: ' + desc_diff
        # Add change history
        data_engine.add_image_history(
            db_img,
            get_session_user(),
            ImageHistory.ACTION_EDITED,
            info
        )
        return make_api_success_response(object_to_dict(db_img))

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'title': data_dict['title'].strip(),
            'description': data_dict['description'].strip()
        }
        validate_string(params['title'], 0, 255)
        validate_string(params['description'], 0, 10000)
        return params


class TemplateAPI(MethodView):
    """
    Provides the REST admin API to list, create, get, update or delete
    image templates.

    Required access:
    - None to get or list the templates (caller must only be logged in)
    - Otherwise requires super user
    """
    # ImageAttrs fields we don't want to store or return in the JSON
    HIDE_FIELDS = ['filename', 'template']

    @add_api_error_handler
    def get(self, template_id=None):
        if template_id is None:
            # List templates
            tlist = data_engine.list_objects(ImageTemplate, ImageTemplate.name)
            tdictlist = object_to_dict_list(tlist)
            for tdict in tdictlist:
                self._del_keys(tdict['template'], TemplateAPI.HIDE_FIELDS)
            return make_api_success_response(tdictlist)
        else:
            # Get single template
            template_info = data_engine.get_image_template(template_id)
            if template_info is None:
                raise DoesNotExistError(str(template_id))
            tdict = object_to_dict(template_info)
            self._del_keys(tdict['template'], TemplateAPI.HIDE_FIELDS)
            return make_api_success_response(tdict)

    @add_api_error_handler
    def post(self):
        permissions_engine.ensure_permitted(
            SystemPermissions.PERMIT_SUPER_USER, get_session_user()
        )
        params = self._get_validated_object_parameters(request.form)
        template = ImageTemplate(
            params['name'],
            params['description'],
            params['template']
        )
        template = data_engine.save_object(template, refresh=True)
        image_engine.reset_templates()
        return self.get(template.id)

    @add_api_error_handler
    def put(self, template_id):
        permissions_engine.ensure_permitted(
            SystemPermissions.PERMIT_SUPER_USER, get_session_user()
        )
        params = self._get_validated_object_parameters(request.form)
        template = data_engine.get_image_template(template_id)
        if template is None:
            raise DoesNotExistError(str(template_id))
        template.name = params['name']
        template.description = params['description']
        template.template = params['template']
        data_engine.save_object(template)
        image_engine.reset_templates()
        return self.get(template.id)

    @add_api_error_handler
    def delete(self, template_id):
        permissions_engine.ensure_permitted(
            SystemPermissions.PERMIT_SUPER_USER, get_session_user()
        )
        template_info = data_engine.get_image_template(template_id)
        if template_info is None:
            raise DoesNotExistError(str(template_id))
        db_default_template = data_engine.get_object(Property, Property.DEFAULT_TEMPLATE)
        if template_info.name.lower() == db_default_template.value.lower():
            raise ParameterError('The system default template cannot be deleted')
        data_engine.delete_object(template_info)
        image_engine.reset_templates()
        return make_api_success_response()

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'name': data_dict['name'].strip(),
            'description': data_dict['description'],
            'template': data_dict['template']
        }
        validate_string(params['name'], 1, 120)
        validate_string(params['description'], 0, 5 * 1024)
        validate_string(params['template'], 2, 100 * 1024)
        # Validate the JSON syntax
        try:
            template_dict = json.loads(params['template'])
        except ValueError as e:
            raise ValueError(u'template: ' + unicode(e))
        # Validate the JSON data values
        self._del_keys(template_dict, TemplateAPI.HIDE_FIELDS)
        template_attrs = TemplateAttrs(params['name'], template_dict)
        # Return the template as a validated dict
        params['template'] = template_attrs.get_raw_dict()
        return params

    def _del_keys(self, dct, keys_list):
        """
        Deletes the keys in keys_list from dictionary dct.
        """
        for k in keys_list:
            try:
                del dct[k]
            except KeyError:
                pass


class UserAPI(MethodView):
    """
    Provides the REST admin API to list, create, get, update or delete
    user database records.

    Required access:
    - None to get or update a user's own record
    - Otherwise requires admin_users
    """
    @add_api_error_handler
    def get(self, user_id=None):
        if user_id is None:
            # List users
            ulist = data_engine.list_users(order_field=User.username)
            # Do not give out anything password related
            udictlist = object_to_dict_list(ulist)
            for user in udictlist:
                del user['password']
            return make_api_success_response(udictlist)
        else:
            # Get single user
            user = data_engine.get_user(user_id)
            if user is None:
                raise DoesNotExistError(str(user_id))
            # Do not give out anything password related
            udict = object_to_dict(user)
            del udict['password']
            return make_api_success_response(udict)

    @add_api_error_handler
    def post(self):
        params = self._get_validated_object_parameters(request.form, True)
        # Do not use the password if this is an LDAP user
        if params['auth_type'] == User.AUTH_TYPE_LDAP:
            params['password'] = generate_password()
        # Create the new user
        user = User(
            params['first_name'], params['last_name'],
            params['email'],
            params['username'], params['password'],
            params['auth_type'],
            params['allow_api'],
            User.STATUS_ACTIVE
        )
        data_engine.create_user(user)
        # Do not give out anything password related
        udict = object_to_dict(user)
        del udict['password']
        return make_api_success_response(udict)

    @add_api_error_handler
    def put(self, user_id):
        params = self._get_validated_object_parameters(request.form, False)
        user = data_engine.get_user(user_id=user_id)
        if user is None:
            raise DoesNotExistError(str(user_id))
        user.first_name = params['first_name']
        user.last_name = params['last_name']
        user.email = params['email']
        user.auth_type = params['auth_type']
        user.allow_api = params['allow_api']
        # Don't update the status field with this method
        # Update username only if non-LDAP
        if user.auth_type != User.AUTH_TYPE_LDAP:
            user.username = params['username']
        # Update password only if non-LDAP and a new one was passed in
        if user.auth_type != User.AUTH_TYPE_LDAP and params['password']:
            user.set_password(params['password'])
        data_engine.save_object(user)
        # Reset session caches
        reset_user_sessions(user)
        # Do not give out anything password related
        udict = object_to_dict(user)
        del udict['password']
        return make_api_success_response(udict)

    @add_api_error_handler
    def delete(self, user_id):
        user = data_engine.get_user(user_id=user_id)
        if user is None:
            raise DoesNotExistError(str(user_id))
        if user.id == 1:
            raise ParameterError('The \'admin\' user cannot be deleted')
        data_engine.delete_user(user)
        # If this is the current user, log out
        if get_session_user_id() == user_id:
            log_out()
        # Reset session caches
        reset_user_sessions(user)
        # Do not give out anything password related
        udict = object_to_dict(user)
        del udict['password']
        return make_api_success_response(udict)

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict, require_password):
        params = {
            'first_name': data_dict['first_name'],
            'last_name': data_dict['last_name'],
            'email': data_dict['email'],
            'username': data_dict['username'].strip(),
            'password': data_dict.get('password', ''),
            'auth_type': parse_int(data_dict['auth_type']),
            'allow_api': parse_boolean(data_dict.get('allow_api', ''))
        }
        validate_string(params['first_name'], 0, 120)
        validate_string(params['last_name'], 0, 120)
        validate_string(params['email'], 0, 120)
        validate_number(params['auth_type'], User.AUTH_TYPE_PASSWORD, User.AUTH_TYPE_LDAP)
        if params['auth_type'] != User.AUTH_TYPE_LDAP:
            validate_string(params['username'], 1, 120)
        if params['password'] or require_password:
            validate_string(params['password'], 6, 120)
        return params


class GroupAPI(MethodView):
    """
    Provides the REST admin API to list, create, get, update or delete
    group database records.

    Required access:
    - Minimum admin_users
    - Also requires admin_permissions to create or delete, or to update group permissions
    """
    @add_api_error_handler
    def get(self, group_id=None):
        if group_id is None:
            # List groups
            return make_api_success_response(
                object_to_dict_list(data_engine.list_objects(Group, Group.name))
            )
        else:
            # Get single group
            group = data_engine.get_group(group_id=group_id, load_users=True)
            if group is None:
                raise DoesNotExistError(str(group_id))
            # Do not give out anything password related
            gdict = object_to_dict(group)
            for udict in gdict['users']:
                del udict['password']
            return make_api_success_response(gdict)

    @add_api_error_handler
    def post(self):
        # Check permissions! The current user must have permissions admin to create groups.
        permissions_engine.ensure_permitted(
            SystemPermissions.PERMIT_ADMIN_PERMISSIONS, get_session_user()
        )
        params = self._get_validated_object_parameters(request.form)
        if params['group_type'] == Group.GROUP_TYPE_SYSTEM:
            raise ParameterError('System groups cannot be created')
        group = Group(
            params['name'],
            params['description'],
            params['group_type']
        )
        group.users = []
        self._set_permissions(group, params)
        data_engine.create_group(group)
        return make_api_success_response(object_to_dict(group))

    @add_api_error_handler
    def put(self, group_id):
        params = self._get_validated_object_parameters(request.form)
        group = data_engine.get_group(group_id=group_id, load_users=True)
        if group is None:
            raise DoesNotExistError(str(group_id))
        # Back up the object in case we need to restore it
        backup_group = copy.deepcopy(group)
        # Update group
        group.description = params['description']
        if group.group_type != Group.GROUP_TYPE_SYSTEM:
            group.group_type = params['group_type']
        if group.group_type == Group.GROUP_TYPE_LOCAL:
            group.name = params['name']
        permissions_changed = self._set_permissions(group, params)
        data_engine.save_object(group)
        # Reset permissions and session caches
        if permissions_changed:
            reset_user_sessions(group.users)
            permissions_engine.reset()
            _check_for_user_lockout(backup_group)
        # Do not give out anything password related
        gdict = object_to_dict(group)
        for udict in gdict['users']:
            del udict['password']
        return make_api_success_response(gdict)

    @add_api_error_handler
    def delete(self, group_id):
        # Check permissions! The current user must have permissions admin to delete groups.
        permissions_engine.ensure_permitted(
            SystemPermissions.PERMIT_ADMIN_PERMISSIONS, get_session_user()
        )
        group = data_engine.get_group(group_id=group_id, load_users=True)
        if group is None:
            raise DoesNotExistError(str(group_id))
        try:
            data_engine.delete_group(group)
        except ValueError as e:
            raise ParameterError(str(e))
        # Reset permissions and session caches
        reset_user_sessions(group.users)
        permissions_engine.reset()
        return make_api_success_response()

    def _set_permissions(self, group, params):
        # Apply default permissions if this is a new group
        if not group.permissions:
            group.permissions = SystemPermissions(
                group, False, False, False, False, False, False, False
            )
        # Update permissions only if the current user has permissions admin
        if permissions_engine.is_permitted(
            SystemPermissions.PERMIT_ADMIN_PERMISSIONS, get_session_user()
        ):
            group.permissions.folios = params['access_folios']
            group.permissions.reports = params['access_reports']
            group.permissions.admin_users = params['access_admin_users']
            group.permissions.admin_files = params['access_admin_files']
            group.permissions.admin_folios = params['access_admin_folios']
            group.permissions.admin_permissions = params['access_admin_permissions']
            group.permissions.admin_all = params['access_admin_all']
            return True
        return False

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'name': data_dict['name'].strip(),
            'description': data_dict['description'],
            'group_type': parse_int(data_dict['group_type']),
            'access_folios': parse_boolean(data_dict.get('access_folios', '')),
            'access_reports': parse_boolean(data_dict.get('access_reports', '')),
            'access_admin_users': parse_boolean(data_dict.get('access_admin_users', '')),
            'access_admin_files': parse_boolean(data_dict.get('access_admin_files', '')),
            'access_admin_folios': parse_boolean(data_dict.get('access_admin_folios', '')),
            'access_admin_permissions': parse_boolean(data_dict.get('access_admin_permissions', '')),
            'access_admin_all': parse_boolean(data_dict.get('access_admin_all', ''))
        }
        validate_string(params['description'], 0, 5 * 1024)
        validate_number(params['group_type'], Group.GROUP_TYPE_SYSTEM, Group.GROUP_TYPE_LDAP)
        if params['group_type'] == Group.GROUP_TYPE_LOCAL:
            validate_string(params['name'], 1, 120)
        return params


class UserGroupAPI(MethodView):
    """
    Provides the REST admin API to add or remove group members.

    Required access:
    - Minimum admin_users
    - Also requires admin_permissions to add a user to a group that itself
      grants admin_permissions or admin_all access
    """
    @add_api_error_handler
    def post(self, group_id):
        params = self._get_validated_object_parameters(request.form)
        group = data_engine.get_group(group_id=group_id, load_users=True)
        if group is None:
            raise DoesNotExistError(str(group_id))

        # Check permissions! The current user must have user admin to be here.
        # But if they don't also have permissions admin or superuser then we
        # must block the change if the new group would grant one of the same.
        if group.permissions.admin_permissions or group.permissions.admin_all:
            if not permissions_engine.is_permitted(
                SystemPermissions.PERMIT_ADMIN_PERMISSIONS, get_session_user()
            ):
                raise SecurityError(
                    'You cannot add users to a group that ' +
                    'grants permissions administration, because you do not ' +
                    'have permissions administration access yourself.'
                )

        user = data_engine.get_user(user_id=params['user_id'])
        if user is not None:
            if user not in group.users:
                group.users.append(user)
                data_engine.save_object(group)
                reset_user_sessions(user)
                permissions_engine.reset()
        return make_api_success_response()

    @add_api_error_handler
    def delete(self, group_id, user_id):
        group = data_engine.get_group(group_id=group_id, load_users=True)
        if group is None:
            raise DoesNotExistError(str(group_id))
        # Back up the object in case we need to restore it
        backup_group = copy.deepcopy(group)
        # Update group membership
        for idx, member in enumerate(group.users):
            if member.id == user_id:
                del group.users[idx]
                data_engine.save_object(group)
                reset_user_sessions(member)
                permissions_engine.reset()
                _check_for_user_lockout(backup_group)
                break
        return make_api_success_response()

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {'user_id': parse_int(data_dict['user_id'])}
        validate_number(params['user_id'], 1, sys.maxint)
        return params


class FolderPermissionAPI(MethodView):
    """
    Provides the REST admin API to list, create, get, update or delete
    folder permission database records.

    Required access:
    - admin_permissions
    """
    @add_api_error_handler
    def get(self, permission_id=None):
        if permission_id is None:
            # List all permissions
            fp_list = data_engine.list_objects(FolderPermission)
            return make_api_success_response(object_to_dict_list(fp_list))
        else:
            # Get permission entry
            fp = data_engine.get_object(FolderPermission, permission_id)
            if fp is None:
                raise DoesNotExistError(str(permission_id))
            return make_api_success_response(object_to_dict(fp))

    @add_api_error_handler
    def post(self):
        params = self._get_validated_object_parameters(request.form)
        db_session = data_engine.db_get_session()
        db_commit = False
        try:
            db_group = data_engine.get_group(params['group_id'], _db_session=db_session)
            if db_group is None:
                raise DoesNotExistError(str(params['group_id']))
            db_folder = data_engine.get_folder(params['folder_id'], _db_session=db_session)
            if db_folder is None:
                raise DoesNotExistError(str(params['folder_id']))

            # This commits (needed for refresh to get the new ID)
            fp = FolderPermission(db_folder, db_group, params['access'])
            fp = data_engine.save_object(
                fp, refresh=True, _db_session=db_session, _commit=True
            )
            db_commit = True
            return make_api_success_response(object_to_dict(fp))
        finally:
            try:
                if db_commit:
                    db_session.commit()
                    permissions_engine.reset_folder_permissions()
                else:
                    db_session.rollback()
            finally:
                db_session.close()

    @add_api_error_handler
    def put(self, permission_id):
        params = self._get_validated_object_parameters(request.form)
        fp = data_engine.get_object(FolderPermission, permission_id)
        if fp is None:
            raise DoesNotExistError(str(permission_id))
        fp.access = params['access']
        data_engine.save_object(fp)
        permissions_engine.reset_folder_permissions()
        return make_api_success_response(object_to_dict(fp))

    @add_api_error_handler
    def delete(self, permission_id):
        db_session = data_engine.db_get_session()
        db_commit = False
        try:
            fp = data_engine.get_object(
                FolderPermission,
                permission_id,
                _db_session=db_session
            )
            if fp is None:
                raise DoesNotExistError(str(permission_id))
            try:
                data_engine.delete_folder_permission(
                    fp, _db_session=db_session, _commit=False
                )
            except ValueError as e:
                raise ParameterError(str(e))

            db_commit = True
            return make_api_success_response()
        finally:
            if db_commit:
                db_session.commit()
                permissions_engine.reset_folder_permissions()
            else:
                db_session.rollback()
            db_session.close()

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'group_id': parse_int(data_dict['group_id']),
            'folder_id': parse_int(data_dict['folder_id']),
            'access': parse_int(data_dict['access'])
        }
        validate_number(params['group_id'], 1, sys.maxint)
        validate_number(params['folder_id'], 1, sys.maxint)
        validate_number(params['access'], FolderPermission.ACCESS_NONE, FolderPermission.ACCESS_ALL)
        return params


class PropertyAPI(MethodView):
    """
    Provides the REST admin API to get or update system properties.
    This API is not intended for general consumption, but any super user can use it.

    Required access:
    - Super user
    """
    @add_api_error_handler
    def get(self, property_id):
        db_prop = data_engine.get_object(Property, property_id)
        if db_prop is None:
            raise DoesNotExistError(str(property_id))
        return make_api_success_response(object_to_dict(db_prop))

    @add_api_error_handler
    def put(self, property_id):
        params = self._get_validated_object_parameters(request.form)
        db_prop = data_engine.get_object(Property, property_id)
        if db_prop is None:
            raise DoesNotExistError(str(property_id))
        db_prop.value = params['value']
        data_engine.save_object(db_prop)
        if property_id == Property.DEFAULT_TEMPLATE:
            image_engine.reset_templates()
        return make_api_success_response(object_to_dict(db_prop))

    @add_parameter_error_handler
    def _get_validated_object_parameters(self, data_dict):
        params = {
            'value': data_dict['value']
        }
        validate_string(params['value'], 0, 10000)
        return params


def _user_api_permission_required(f):
    """
    A decorator that replaces api_permission_required() to implement custom
    access rules for the UserAPI class. In general, any access to UserAPI
    should require user admin permission. This requirement is dropped however,
    for GET and PUT requests only, if the user id to administer is that of the
    current user.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        res = _check_internal_request(
            request, session, False, True, SystemPermissions.PERMIT_ADMIN_USERS
        )
        # If not admin_users, allow GET and PUT for current user's record
        if res:
            allow = (
                request.method in ['GET', 'PUT'] and
                'user_id' in kwargs and
                kwargs['user_id'] > 0 and
                kwargs['user_id'] == get_session_user_id()
            )
            if not allow:
                return res
        return f(*args, **kwargs)
    return decorated_function


# #2054 Don't allow users to revoke their own admin (subsequent API and UI
#       calls fall over), or to accidentally lock out the admin user
def _check_for_user_lockout(original_object):
    """
    Only to be called when the current user is known to have PERMIT_ADMIN_USERS
    permission, checks that the current user hasn't locked themselves out from
    user administration.
    Also checks that the admin user's administration permission has not been
    accidentally revoked.
    If a lockout has occurred, the supplied original object is re-saved and a
    ParameterError is raised.
    """
    user_ids = [get_session_user_id(), 1]
    for user_id in user_ids:
        db_user = data_engine.get_user(user_id=user_id)
        if db_user:
            try:
                # Require user administration
                if not permissions_engine.is_permitted(
                    SystemPermissions.PERMIT_ADMIN_USERS,
                    db_user
                ): raise ParameterError()
                # For the admin user, also require permissions administration
                if user_id == 1 and not permissions_engine.is_permitted(
                    SystemPermissions.PERMIT_ADMIN_PERMISSIONS,
                    db_user
                ): raise ParameterError()
            except ParameterError:
                # Roll back permissions
                data_engine.save_object(original_object)
                permissions_engine.reset()
                # Raise API error
                who = 'the \'admin\' user' if user_id == 1 else 'you'
                raise ParameterError(
                    'This change would lock %s out of administration' % who
                )


# Add URL routing and minimum required system permissions
#          (some classes add further permission checking)

_dapi_image_views = api_permission_required(ImageAPI.as_view('admin.image'))
api_add_url_rules(
    [url_version_prefix + '/admin/images/<int:image_id>/',
     '/admin/images/<int:image_id>/'],
    view_func=_dapi_image_views,
    methods=['GET', 'PUT']
)

_dapi_user_views = _user_api_permission_required(UserAPI.as_view('admin.user'))
api_add_url_rules(
    [url_version_prefix + '/admin/users/',
     '/admin/users/'],
    view_func=_dapi_user_views,
    methods=['GET', 'POST']
)
api_add_url_rules(
    [url_version_prefix + '/admin/users/<int:user_id>/',
     '/admin/users/<int:user_id>/'],
    view_func=_dapi_user_views,
    methods=['GET', 'PUT', 'DELETE']
)

_dapi_group_views = api_permission_required(GroupAPI.as_view('admin.group'),
                                            SystemPermissions.PERMIT_ADMIN_USERS)
api_add_url_rules(
    [url_version_prefix + '/admin/groups/',
     '/admin/groups/'],
    view_func=_dapi_group_views,
    methods=['GET', 'POST']
)
api_add_url_rules(
    [url_version_prefix + '/admin/groups/<int:group_id>/',
     '/admin/groups/<int:group_id>/'],
    view_func=_dapi_group_views,
    methods=['GET', 'PUT', 'DELETE']
)

_dapi_usergroup_views = api_permission_required(UserGroupAPI.as_view('admin.usergroup'),
                                                SystemPermissions.PERMIT_ADMIN_USERS)
api_add_url_rules(
    [url_version_prefix + '/admin/groups/<int:group_id>/members/',
     '/admin/groups/<int:group_id>/members/'],
    view_func=_dapi_usergroup_views,
    methods=['POST']
)
api_add_url_rules(
    [url_version_prefix + '/admin/groups/<int:group_id>/members/<int:user_id>/',
     '/admin/groups/<int:group_id>/members/<int:user_id>/'],
    view_func=_dapi_usergroup_views,
    methods=['DELETE']
)

_dapi_fperm_views = api_permission_required(FolderPermissionAPI.as_view('admin.folderpermission'),
                                            SystemPermissions.PERMIT_ADMIN_PERMISSIONS)
api_add_url_rules(
    [url_version_prefix + '/admin/permissions/',
     '/admin/permissions/'],
    view_func=_dapi_fperm_views,
    methods=['GET', 'POST']
)
api_add_url_rules(
    [url_version_prefix + '/admin/permissions/<int:permission_id>/',
     '/admin/permissions/<int:permission_id>/'],
    view_func=_dapi_fperm_views,
    methods=['GET', 'PUT', 'DELETE']
)

_dapi_template_views = api_permission_required(TemplateAPI.as_view('admin.template'))
api_add_url_rules(
    [url_version_prefix + '/admin/templates/',
     '/admin/templates/'],
    view_func=_dapi_template_views,
    methods=['GET', 'POST']
)
api_add_url_rules(
    [url_version_prefix + '/admin/templates/<int:template_id>/',
     '/admin/templates/<int:template_id>/'],
    view_func=_dapi_template_views,
    methods=['GET', 'PUT', 'DELETE']
)

_dapi_property_views = api_permission_required(PropertyAPI.as_view('admin.property'),
                                               SystemPermissions.PERMIT_SUPER_USER)
api_add_url_rules(
    [url_version_prefix + '/admin/properties/<property_id>/',
     '/admin/properties/<property_id>/'],
    view_func=_dapi_property_views,
    methods=['GET', 'PUT']
)
