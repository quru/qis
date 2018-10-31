#
# Quru Image Server
#
# Document:      views_files_api.py
# Date started:  30 Nov 2012
# By:            Matt Fozard
# Purpose:       Developer / Admin API for managing the file system
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
# 30Oct2018  Matt  v4.1 #12 No longer return deleted sub-folders by default
#

import pickle

from flask import request
from flask.views import MethodView

from . import api_add_url_rules, url_version_prefix
from .helpers import _prep_image_object
from imageserver.api_util import (
    api_permission_required, add_api_error_handler,
    add_parameter_error_handler, make_api_success_response
)
from imageserver.errors import DoesNotExistError, ParameterError, TimeoutError
from imageserver.filesystem_manager import path_exists
from imageserver.filesystem_sync import delete_file, move_file
from imageserver.filesystem_sync import create_folder, auto_sync_folder
from imageserver.flask_app import logger
from imageserver.flask_app import data_engine, image_engine, permissions_engine, task_engine
from imageserver.models import Folder, FolderPermission, Image, Task
from imageserver.session_manager import get_session_user
from imageserver.util import object_to_dict, validate_string, validate_string_in


class ImageFileAPI(MethodView):
    """
    Provides a REST admin API to move or delete image files,
    and update the associated database records.

    Required access:
    - It's complicated
    - Permissions are enforced by filesystem_sync
    """
    @add_api_error_handler
    def put(self, image_id):
        """ Moves or renames a file on disk """
        params = self._get_validated_parameters(request.form)
        # Get image data
        db_img = data_engine.get_image(image_id=image_id)
        if not db_img:
            raise DoesNotExistError(str(image_id))
        # Move
        try:
            db_img = move_file(
                db_img,
                params['path'],
                get_session_user(),
                data_engine,
                permissions_engine
            )
        except ValueError as e:
            if type(e) is ValueError:
                raise ParameterError(str(e))
            else:
                raise  # Sub-classes of ValueError
        # Remove cached images for the old path
        image_engine._uncache_image_id(db_img.id)
        # Return updated image
        return make_api_success_response(object_to_dict(
            _prep_image_object(db_img)
        ))

    @add_api_error_handler
    def delete(self, image_id):
        """ Deletes a file from disk """
        # Get image data
        db_img = data_engine.get_image(image_id=image_id)
        if not db_img:
            raise DoesNotExistError(str(image_id))
        # v4.1 #10 delete_file() doesn't care whether the file exists, but we
        #          want the API to return a "not found" if the file doesn't exist
        #          (and as long as the database is already in sync with that)
        if not path_exists(db_img.src, require_file=True) and db_img.status == Image.STATUS_DELETED:
            raise DoesNotExistError(db_img.src)
        # Delete
        db_img = delete_file(db_img, get_session_user(), data_engine, permissions_engine)
        # Remove cached images for old path
        image_engine._uncache_image_id(db_img.id)
        # Return updated image
        return make_api_success_response(object_to_dict(
            _prep_image_object(db_img)
        ))

    @add_parameter_error_handler
    def _get_validated_parameters(self, data_dict):
        params = {'path': data_dict['path'].strip()}
        validate_string(params['path'], 5, 1024)
        return params


class FolderAPI(MethodView):
    """
    Provides a REST admin API to get, create, move or delete disk folders,
    and update the associated database records.

    Required access:
    - View access for GET
    - Otherwise, it's complicated
    - Permissions are enforced by filesystem_sync
    """
    @add_api_error_handler
    def get(self, folder_id=None):
        """ Gets a folder by path or ID, returning 1 level of children (sub-folders) """
        if folder_id is None:
            # Get folder from path, using auto_sync to pick up new and deleted disk folders
            path = self._get_validated_path_arg(request)
            db_folder = auto_sync_folder(path, data_engine, task_engine)
            if db_folder is None:
                raise DoesNotExistError(path)
        else:
            # Get folder from ID
            db_folder = data_engine.get_folder(folder_id)
            if db_folder is None:
                raise DoesNotExistError(str(folder_id))
        # View permission is required (ignoring view permission on parent+children)
        permissions_engine.ensure_folder_permitted(
            db_folder,
            FolderPermission.ACCESS_VIEW,
            get_session_user()
        )
        # Get the folder again, this time with parent and children
        # (children possibly faked - see the get_folder() docs - which is why
        # we can't use db_folder mk2 normally, only serialize it and exit)
        status_filter = self._get_validated_status_arg(request)
        db_folder = data_engine.get_folder(
            db_folder.id, load_parent=True,
            load_children=True, children_status=status_filter
        )
        if db_folder is None:
            raise DoesNotExistError(str(folder_id))
        return make_api_success_response(object_to_dict(db_folder))

    @add_api_error_handler
    def post(self):
        """ Creates a disk folder """
        params = self._get_validated_parameters(request.form)
        try:
            db_folder = create_folder(
                params['path'],
                get_session_user(),
                data_engine,
                permissions_engine,
                logger
            )
            # Return a "fresh" object (without relationships loaded) to match PUT, DELETE
            db_folder = data_engine.get_folder(db_folder.id)
            return make_api_success_response(object_to_dict(db_folder))
        except ValueError as e:
            if type(e) is ValueError:
                raise ParameterError(str(e))
            else:
                raise  # Sub-classes of ValueError

    @add_api_error_handler
    def put(self, folder_id):
        """ Moves or renames a disk folder """
        params = self._get_validated_parameters(request.form)
        # Run this as a background task in case it takes a long time
        task = task_engine.add_task(
            get_session_user(),
            'Move disk folder %d' % folder_id,
            'move_folder', {
                'folder_id': folder_id,
                'path': params['path']
            },
            Task.PRIORITY_HIGH,
            'info', 'error',
            10
        )
        if task is None:  # Task already submitted
            return make_api_success_response(task_accepted=True)
        else:
            return self._task_response(task, 30)

    @add_api_error_handler
    def delete(self, folder_id):
        """ Deletes a disk folder """
        # v4.1 #10 delete_folder() doesn't care whether it exists, but we want the
        #          API to return a "not found" if the folder doesn't exist on disk
        #          (and as long as the database is already in sync with that)
        db_folder = data_engine.get_folder(folder_id)
        if db_folder is None:
            raise DoesNotExistError(str(folder_id))
        if not path_exists(db_folder.path, require_directory=True) and db_folder.status == Folder.STATUS_DELETED:
            raise DoesNotExistError(db_folder.path)
        # Run this as a background task in case it takes a long time
        task = task_engine.add_task(
            get_session_user(),
            'Delete disk folder %d' % folder_id,
            'delete_folder', {
                'folder_id': folder_id
            },
            Task.PRIORITY_HIGH,
            'info', 'error',
            10
        )
        if task is None:  # Task already submitted
            return make_api_success_response(task_accepted=True)
        else:
            return self._task_response(task, 30)

    @add_parameter_error_handler
    def _get_validated_status_arg(self, request):
        status = request.args.get('status', str(Folder.STATUS_ACTIVE)).lower()
        validate_string_in(status, [
            'any', '-1', str(Folder.STATUS_DELETED), str(Folder.STATUS_ACTIVE)
        ])
        return int(status) if status not in ('any', '-1') else None

    @add_parameter_error_handler
    def _get_validated_path_arg(self, request):
        path = request.args['path'].strip()
        validate_string(path, 1, 1024)
        return path

    @add_parameter_error_handler
    def _get_validated_parameters(self, data_dict):
        params = {'path': data_dict['path'].strip()}
        validate_string(params['path'], 1, 1024)
        return params

    def _task_response(self, task, timeout_secs):
        task_completed = False
        try:
            # Wait for task to complete
            task = task_engine.wait_for_task(task.id, timeout_secs)
            if task is None:
                # Someone else deleted it? Shouldn't normally get here.
                raise TimeoutError()
            task_completed = True
            # Return the updated folder (or raise the exception)
            if isinstance(task.result, Exception):
                raise task.result
            return make_api_success_response(object_to_dict(task.result))
        except TimeoutError:
            # Return a 202 "task ongoing" response
            task_dict = object_to_dict(task) if task is not None else None
            # Decode the params before returning
            if task_dict and task_dict.get('params'):
                task_dict['params'] = pickle.loads(task_dict['params'])
            return make_api_success_response(task_dict, task_accepted=True)
        finally:
            if task and task_completed:
                try:
                    # Delete the task so another API call can be made immediately
                    data_engine.delete_object(task)
                except Exception:
                    pass


# Add URL routing and minimum required permissions
# (class functions will add further permission checking)

_fapi_file_views = api_permission_required(ImageFileAPI.as_view('admin-file-image'))
api_add_url_rules(
    [url_version_prefix + '/admin/filesystem/images/<int:image_id>/',
     '/admin/filesystem/images/<int:image_id>/'],
    view_func=_fapi_file_views
)

_fapi_folder_views = api_permission_required(FolderAPI.as_view('admin-file-folder'))
api_add_url_rules(
    [url_version_prefix + '/admin/filesystem/folders/',
     '/admin/filesystem/folders/'],
    view_func=_fapi_folder_views,
    methods=['GET', 'POST']
)
api_add_url_rules(
    [url_version_prefix + '/admin/filesystem/folders/<int:folder_id>/',
     '/admin/filesystem/folders/<int:folder_id>/'],
    view_func=_fapi_folder_views,
    methods=['GET', 'PUT', 'DELETE']
)
