#
# Quru Image Server
#
# Document:      views_tasks_api.py
# Date started:  29 Jan 2013
# By:            Matt Fozard
# Purpose:       Admin API for running system tasks
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

import cPickle

from flask import request
from flask.views import MethodView

from imageserver.api import api_add_url_rules, url_version_prefix
from imageserver.api_util import add_api_error_handler, add_parameter_error_handler
from imageserver.api_util import make_api_success_response
from imageserver.errors import AlreadyExistsError, DoesNotExistError, ParameterError
from imageserver.flask_app import data_engine, permissions_engine, task_engine
from imageserver.flask_util import api_permission_required
from imageserver.models import SystemPermissions, Task
from imageserver.session_manager import get_session_user, get_session_user_id
from imageserver.util import object_to_dict, parse_iso_date, validate_string

import imageserver.tasks as tasks


class TaskAPI(MethodView):
    """
    Provides the REST admin API to invoke and poll system tasks.

    Required access:
    - Be the task owner for GET
    - Otherwise super user
    """
    @add_api_error_handler
    def get(self, task_id):
        db_task = task_engine.get_task(task_id=task_id, decode_attrs=True)
        if not db_task:
            raise DoesNotExistError(str(task_id))
        else:
            # Requires super user or task owner
            if not db_task.user or db_task.user.id != get_session_user_id():
                permissions_engine.ensure_permitted(
                    SystemPermissions.PERMIT_SUPER_USER, get_session_user()
                )
            tdict = object_to_dict(db_task)
            if tdict.get('user') is not None:
                # Do not give out anything password related
                del tdict['user']['password']
            return make_api_success_response(tdict)

    @add_api_error_handler
    def post(self, function_name):
        """ Launches a system task """
        # Validate function name
        if getattr(tasks, function_name, None) is None:
            raise DoesNotExistError(function_name)
        # Requires super user
        permissions_engine.ensure_permitted(
            SystemPermissions.PERMIT_SUPER_USER, get_session_user()
        )
        # API parameters depend on the function
        params = self._get_validated_parameters(function_name, request.form)
        # Set remaining parameters for the task
        (description, task_params, priority,
         log_level, error_log_level, keep_secs) = self._get_task_data(
            function_name, params
        )
        # Queue the task
        db_task = task_engine.add_task(
            get_session_user(),
            description,
            function_name,
            task_params,
            priority,
            log_level,
            error_log_level,
            keep_secs
        )
        if db_task is None:
            raise AlreadyExistsError('Task is already running')
        # Decode the params before returning
        db_task.params = cPickle.loads(db_task.params)
        tdict = object_to_dict(db_task)
        if tdict.get('user') is not None:
            # Do not give out anything password related
            del tdict['user']['password']
        return make_api_success_response(tdict)

    @add_parameter_error_handler
    def _get_task_data(self, function_name, api_params):
        # Return the task-specific options and parameters
        if function_name == 'purge_system_stats':
            return (
                'Purge system statistics',
                {'before_time': api_params['before_time']},
                Task.PRIORITY_NORMAL,
                'info', 'error', 3600
            )
        elif function_name == 'purge_image_stats':
            return (
                'Purge image statistics',
                {'before_time': api_params['before_time']},
                Task.PRIORITY_NORMAL,
                'info', 'error', 3600
            )
        elif function_name == 'purge_deleted_folder_data':
            # Get folder ID from path
            db_folder = data_engine.get_folder(folder_path=api_params['path'])
            if db_folder is None:
                raise ParameterError(api_params['path'] + ' is not a valid folder path')
            return (
                'Purge deleted data',
                {'folder_id': db_folder.id},
                Task.PRIORITY_NORMAL,
                'info', 'error', 0
            )
        else:
            raise ParameterError(function_name + ' task is not yet supported')

    @add_parameter_error_handler
    def _get_validated_parameters(self, function_name, data_dict):
        # Get the API / URL parameters
        if function_name == 'purge_system_stats' or \
           function_name == 'purge_image_stats':
            # Purge to date
            params = {'before_time': parse_iso_date(data_dict['date_to'])}
        elif function_name == 'purge_deleted_folder_data':
            # Purge folder path
            params = {'path': data_dict['path'].strip()}
            validate_string(params['path'], 0, 1024)
        else:
            raise ParameterError(function_name + ' task is not yet supported')
        return params


# Add URL routing and minimum required system permissions

_tapi_task_views = api_permission_required(TaskAPI.as_view('admin.task'))
api_add_url_rules(
    [url_version_prefix + '/admin/tasks/<int:task_id>/',
     '/admin/tasks/<int:task_id>/'],
    view_func=_tapi_task_views,
    methods=['GET']
)
api_add_url_rules(
    [url_version_prefix + '/admin/tasks/<function_name>/',
     '/admin/tasks/<function_name>/'],
    view_func=_tapi_task_views,
    methods=['POST']
)
