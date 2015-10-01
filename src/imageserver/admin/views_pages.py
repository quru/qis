#
# Quru Image Server
#
# Document:      views_pages.py
# Date started:  11 Aug 2011
# By:            Matt Fozard
# Purpose:       Administration web page URLs and views
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

import os.path

from flask import request
from datetime import datetime, timedelta

from imageserver.admin import blueprint
from imageserver.errors import DoesNotExistError
from imageserver.flask_app import app, data_engine, permissions_engine
from imageserver.flask_util import render_template
from imageserver.image_attrs import ImageAttrs
from imageserver.template_attrs import TemplateAttrs
from imageserver.models import Folder, Group, ImageTemplate, User
from imageserver.util import parse_int
from imageserver.views_util import log_security_error


# The admin index page
@blueprint.route('/')
def index():
    return render_template(
        'admin_index.html'
    )


# The template admin list page
@blueprint.route('/templates/')
def template_list():
    return render_template(
        'admin_template_list.html',
        templates=data_engine.list_objects(ImageTemplate, order_field=ImageTemplate.name)
    )


# The user admin list page
@blueprint.route('/users/')
def user_list():
    return render_template(
        'admin_user_list.html',
        users=data_engine.list_users(order_field=User.username)
    )


# The group admin list page
@blueprint.route('/groups/')
def group_list():
    return render_template(
        'admin_group_list.html',
        groups=data_engine.list_objects(Group, Group.name),
        GROUP_TYPE_SYSTEM=Group.GROUP_TYPE_SYSTEM
    )


# The template admin edit page
@blueprint.route('/templates/<int:template_id>/')
def template_edit(template_id):
    embed = request.args.get('embed', '')
    template = None
    err_msg = None
    try:
        if template_id > 0:
            template = data_engine.get_image_template(template_id)

        fields = ImageAttrs.validators().copy()
        fields.update(TemplateAttrs.validators())
    except Exception as e:
        log_security_error(e, request)
        err_msg = str(e)
    return render_template(
        'admin_template_edit.html',
        fields=fields,
        embed=embed,
        template=template,
        err_msg=err_msg
    )


# The user admin edit page
@blueprint.route('/users/<int:user_id>/')
def user_edit(user_id):
    embed = request.args.get('embed', '')
    user = None
    err_msg = None
    try:
        if user_id > 0:
            user = data_engine.get_user(user_id=user_id, load_groups=True)
    except Exception as e:
        log_security_error(e, request)
        err_msg = str(e)
    return render_template(
        'admin_user_edit.html',
        embed=embed,
        user=user,
        err_msg=err_msg,
        AUTH_TYPE_PASSWORD=User.AUTH_TYPE_PASSWORD,
        STATUS_ACTIVE=User.STATUS_ACTIVE
    )


# The group admin edit page
@blueprint.route('/groups/<int:group_id>/')
def group_edit(group_id):
    embed = request.args.get('embed', '')
    group = None
    users = []
    err_msg = None
    try:
        users = data_engine.list_users(status=User.STATUS_ACTIVE, order_field=User.username)
        if group_id > 0:
            group = data_engine.get_group(group_id=group_id, load_users=True)
    except Exception as e:
        log_security_error(e, request)
        err_msg = str(e)
    return render_template(
        'admin_group_edit.html',
        embed=embed,
        users=users,
        group=group,
        err_msg=err_msg,
        GROUP_ID_PUBLIC=Group.ID_PUBLIC,
        GROUP_TYPE_LOCAL=Group.GROUP_TYPE_LOCAL,
        GROUP_TYPE_SYSTEM=Group.GROUP_TYPE_SYSTEM,
        STATUS_ACTIVE=User.STATUS_ACTIVE
    )


# The folder permissions view/edit page
@blueprint.route('/permissions/')
def folder_permissions():
    folder_path = request.args.get('path', '')
    if folder_path == '':
        folder_path = os.path.sep

    group_id = request.args.get('group', '')
    if group_id == '':
        group_id = Group.ID_PUBLIC

    group = None
    folder = None
    current_perms = None
    groups = []
    err_msg = None
    db_session = data_engine.db_get_session()
    try:
        # Get folder and group info
        group = data_engine.get_group(group_id, _db_session=db_session)
        if group is None:
            raise DoesNotExistError('This group no longer exists')
        folder = data_engine.get_folder(folder_path=folder_path, _db_session=db_session)
        if folder is None or folder.status == Folder.STATUS_DELETED:
            raise DoesNotExistError('This folder no longer exists')

        # Get groups list
        groups = data_engine.list_objects(Group, Group.name, _db_session=db_session)

        # Get the current permissions for the folder+group, which can be None.
        # Note that permissions_manager might fall back to the Public group if
        # this is None, but to keep the admin manageable we're going to deal
        # only with folder inheritance, not group inheritance too.
        current_perms = data_engine.get_nearest_folder_permission(
            folder, group,
            _load_nearest_folder=True,
            _db_session=db_session
        )
    except Exception as e:
        log_security_error(e, request)
        err_msg = str(e)
    finally:
        try:
            return render_template(
                'admin_folder_permissions.html',
                group=group,
                folder=folder,
                folder_is_root=folder.is_root() if folder else False,
                current_permissions=current_perms,
                group_list=groups,
                err_msg=err_msg,
                GROUP_ID_PUBLIC=Group.ID_PUBLIC,
                GROUP_ID_EVERYONE=Group.ID_EVERYONE
            )
        finally:
            db_session.close()


# The user - folder permissions trace page
@blueprint.route('/trace_permissions/')
def trace_permissions():
    embed = request.args.get('embed', '')
    user_id = request.args.get('user', '')
    folder_path = request.args.get('path', '')
    if folder_path == '':
        folder_path = os.path.sep

    folder = None
    user = None
    users = []
    user_has_admin = False
    trace = None
    err_msg = None
    db_session = data_engine.db_get_session()
    try:
        # Get folder and selected user info
        # User can be None for an anonymous user
        user_id = parse_int(user_id)
        if user_id != 0:
            user = data_engine.get_user(user_id, _db_session=db_session)
            if user is None:
                raise DoesNotExistError('This user no longer exists')
        folder = data_engine.get_folder(folder_path=folder_path, _db_session=db_session)
        if folder is None or folder.status == Folder.STATUS_DELETED:
            raise DoesNotExistError('This folder no longer exists')

        # Get users list
        users = data_engine.list_users(
            status=User.STATUS_ACTIVE,
            order_field=User.username,
            _db_session=db_session
        )

        # Get the folder+user traced permissions
        trace = permissions_engine._trace_folder_permissions(folder, user)

        # Flag on the UI if the user has admin
        for gdict in trace['groups']:
            gperms = gdict['group'].permissions
            if gperms.admin_files or gperms.admin_all:
                user_has_admin = True
                break

    except Exception as e:
        log_security_error(e, request)
        err_msg = str(e)
    finally:
        try:
            return render_template(
                'admin_trace_permissions.html',
                embed=embed,
                folder=folder,
                folder_is_root=folder.is_root() if folder else False,
                user=user,
                user_list=users,
                trace=trace,
                user_has_admin=user_has_admin,
                err_msg=err_msg,
                GROUP_ID_PUBLIC=Group.ID_PUBLIC
            )
        finally:
            db_session.close()


# The data maintenance page
@blueprint.route('/maintenance/')
def maintenance():
    purge_to = datetime.utcnow() - (
        timedelta(days=app.config['STATS_KEEP_DAYS'])
        if app.config['STATS_KEEP_DAYS'] > 0 else 31
    )
    return render_template(
        'admin_maintenance.html',
        purge_to=purge_to
    )
