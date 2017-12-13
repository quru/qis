#
# Quru Image Server
#
# Document:      views_api.py
# Date started:  05 Dec 2011
# By:            Matt Fozard
# Purpose:       Developer API views (aside from the core public image serving)
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
# 13Jan2015  Matt  Upload API to take and return multiple files
# 10Mar2015  Matt  Use signed tokens to access the API
#

from time import sleep

from flask import request

from imageserver.api import blueprint, url_version_prefix
from imageserver.api_util import add_api_error_handler
from imageserver.api_util import create_api_error_dict
from imageserver.api_util import make_api_success_response
from imageserver.csrf import csrf_exempt
from imageserver.errors import (
    AuthenticationError, DoesNotExistError, ImageError,
    ParameterError, SecurityError
)
from imageserver.filesystem_manager import get_directory_listing, path_exists
from imageserver.filesystem_sync import auto_sync_file, auto_sync_existing_file
from imageserver.filesystem_sync import auto_sync_folder
from imageserver.flask_app import (
    app, logger,
    cache_engine, data_engine, image_engine, permissions_engine, task_engine
)
from imageserver.flask_ext import TimedTokenBasicAuthentication
from imageserver.flask_util import api_permission_required, external_url_for, login_point
from imageserver.models import FolderPermission, Image, User
from imageserver.session_manager import get_session_user
from imageserver.user_auth import authenticate_user
from imageserver.util import add_sep, get_file_extension, secure_filename
from imageserver.util import parse_boolean, parse_int
from imageserver.util import validate_number, validate_string


# API login - generates a token to use the API outside of the web site
@blueprint.route('/token', methods=['POST'])
@blueprint.route(url_version_prefix + '/token', methods=['POST'])  # Legacy (no slash)
@blueprint.route('/token/', methods=['POST'], strict_slashes=False)
@blueprint.route(url_version_prefix + '/token/', methods=['POST'], strict_slashes=False)  # v2.6.1 onwards
@csrf_exempt
@login_point(from_web=False)
@add_api_error_handler
def token():
    username = None
    password = None
    # Get credentials - prefer HTTP Basic Auth
    if request.authorization:
        username = request.authorization.username
        password = request.authorization.password
    # Get credentials - but fall back to POST data
    if not username and not password:
        username = request.form.get('username', '')
        password = request.form.get('password', '')
    # Get credentials - ensure no blanks
    if not username:
        raise ParameterError('Username value cannot be blank')
    if not password:
        raise ParameterError('Password value cannot be blank')

    try:
        user = authenticate_user(username, password, data_engine, logger)
    except AuthenticationError as e:
        # Return 500 rather than 401 for authentication runtime errors
        raise Exception(str(e))

    if user is not None:
        if not user.allow_api:
            raise SecurityError('This account is not API enabled')
        elif user.status != User.STATUS_ACTIVE:
            raise SecurityError('This account is disabled')
        else:
            # Success
            http_auth = TimedTokenBasicAuthentication(app)
            token = http_auth.generate_auth_token({'user_id': user.id})
            return make_api_success_response({'token': token})

    # Login incorrect
    logger.warn('Incorrect API login for username ' + username)
    # Slow down scripted attacks
    sleep(1)
    raise SecurityError('Incorrect username or password')


# Returns a JSON encoded list of files in a folder (max 1000),
# optionally with the title, description, width, height attributes of each.
# Any additional parameters are passed on for inclusion in the returned image URLs.
@blueprint.route('/list', methods=['GET'])
@blueprint.route(url_version_prefix + '/list', methods=['GET'])  # Legacy (no slash)
@blueprint.route('/list/', methods=['GET'], strict_slashes=False)
@blueprint.route(url_version_prefix + '/list/', methods=['GET'], strict_slashes=False)  # v2.6.1 onwards
@add_api_error_handler
def imagelist():
    # Check parameters
    try:
        from_path = request.args.get('path', '')
        want_info = parse_boolean(request.args.get('attributes', ''))
        start = parse_int(request.args.get('start', '0'))
        limit = parse_int(request.args.get('limit', '1000'))
        validate_string(from_path, 1, 1024)
        validate_number(start, 0, 999999999)
        validate_number(limit, 1, 1000)
    except ValueError as e:
        raise ParameterError(e)

    # Get extra parameters for image URL construction
    image_params = request.args.to_dict()
    if 'path' in image_params:
        del image_params['path']
    if 'attributes' in image_params:
        del image_params['attributes']
    if 'start' in image_params:
        del image_params['start']
    if 'limit' in image_params:
        del image_params['limit']

    # Get directory listing
    directory_info = get_directory_listing(from_path, False, 2, start, limit)
    if not directory_info.exists():
        raise DoesNotExistError('Invalid path')

    ret_list = []
    db_session = data_engine.db_get_session()
    db_commit = False
    try:
        # Auto-populate the folders database
        db_folder = auto_sync_folder(
            from_path, data_engine, task_engine, _db_session=db_session
        )
        db_session.commit()

        # Require view permission or file admin
        permissions_engine.ensure_folder_permitted(
            db_folder,
            FolderPermission.ACCESS_VIEW,
            get_session_user()
        )

        # Create the response
        file_list = directory_info.contents()
        img_types = image_engine.get_image_formats()
        base_folder = add_sep(directory_info.name())
        for f in file_list:
            # v2.6.4 Return unsupported files too. If you want to reverse this change,
            # the filtering needs to be elsewhere for 'start' and 'limit' to work properly
            supported_file = get_file_extension(f['filename']) in img_types
            file_path = base_folder + f['filename']
            file_url = (
                external_url_for('image', src=file_path, **image_params)
                if supported_file else ''
            )
            entry = {
                'filename': f['filename'],
                'supported': supported_file,
                'url': file_url
            }
            if want_info:
                db_entry = None
                if supported_file:
                    db_entry = auto_sync_existing_file(
                        file_path,
                        data_engine,
                        task_engine,
                        burst_pdf=False,  # Don't burst a PDF just by finding it here
                        _db_session=db_session
                    )
                entry['id'] = db_entry.id if db_entry else 0
                entry['folder_id'] = db_entry.folder_id if db_entry else 0
                entry['title'] = db_entry.title if db_entry else ''
                entry['description'] = db_entry.description if db_entry else ''
                entry['width'] = db_entry.width if db_entry else 0
                entry['height'] = db_entry.height if db_entry else 0
            ret_list.append(entry)

        db_commit = True
    finally:
        try:
            if db_commit:
                db_session.commit()
            else:
                db_session.rollback()
        finally:
            db_session.close()

    return make_api_success_response(ret_list)


# Returns JSON encoded basic image attributes.
@blueprint.route('/details', methods=['GET'])
@blueprint.route(url_version_prefix + '/details', methods=['GET'])  # Legacy (no slash)
@blueprint.route('/details/', methods=['GET'], strict_slashes=False)
@blueprint.route(url_version_prefix + '/details/', methods=['GET'], strict_slashes=False)  # v2.6.1 onwards
@add_api_error_handler
def imagedetails():
    # Get/check parameters
    try:
        src = request.args.get('src', '')
        validate_string(src, 1, 1024)
    except ValueError as e:
        raise ParameterError(e)

    # v2.6.4 Don't allow this call to populate the database with unsupported files
    supported_file = get_file_extension(src) in image_engine.get_image_formats()
    if not supported_file and path_exists(src, require_file=True):
        raise ImageError('The file is not a supported image format')

    # Get the image database entry
    db_image = auto_sync_file(src, data_engine, task_engine)
    if not db_image or db_image.status == Image.STATUS_DELETED:
        raise DoesNotExistError(src)

    # Require view permission or file admin
    permissions_engine.ensure_folder_permitted(
        db_image.folder,
        FolderPermission.ACCESS_VIEW,
        get_session_user()
    )

    return make_api_success_response(_image_dict(db_image))


# Raw image(s) upload, returns a dict of original filename to image details
# (as for /details), or filename to error message if an upload failed
@blueprint.route('/upload', methods=['POST'])
@blueprint.route(url_version_prefix + '/upload', methods=['POST'])  # Legacy (no slash)
@blueprint.route('/upload/', methods=['POST'], strict_slashes=False)
@blueprint.route(url_version_prefix + '/upload/', methods=['POST'], strict_slashes=False)  # v2.6.1 onwards
@api_permission_required
@add_api_error_handler
def upload():
    # Get URL parameters for the upload
    file_list = request.files.getlist('files')
    path_index = request.form.get('path_index', '-1')   # Index into IMAGE_UPLOAD_DIRS or -1
    path = request.form.get('path', '')                 # Manual path when path_index is -1
    overwrite = request.form.get('overwrite')

    ret_dict = {}
    try:
        current_user = get_session_user()
        assert current_user is not None

        # Check params
        path_index = parse_int(path_index)
        overwrite = parse_boolean(overwrite)
        validate_string(path, 0, 1024)
        if len(file_list) < 1:
            raise ValueError('No files have been attached')

        # Loop over the upload files
        put_image_exception = None
        can_download = None
        for wkfile in file_list:
            original_filename = wkfile.filename
            if original_filename:
                db_image = None
                try:
                    # Save (also checks user-folder permissions)
                    _, db_image = image_engine.put_image(
                        current_user,
                        wkfile,
                        secure_filename(
                            original_filename,
                            app.config['ALLOW_UNICODE_FILENAMES']
                        ),
                        path_index,
                        path,
                        overwrite
                    )
                except Exception as e:
                    # Save the error to use as our overall return value
                    if put_image_exception is None:
                        put_image_exception = e
                    # This loop failure, add the error info to our return data
                    ret_dict[original_filename] = {'error': create_api_error_dict(e)}

                if db_image:
                    # Calculate download permission once (all files are going to same folder)
                    if can_download is None:
                        can_download = permissions_engine.is_folder_permitted(
                            db_image.folder,
                            FolderPermission.ACCESS_DOWNLOAD,
                            get_session_user()
                        )
                    # This loop success
                    ret_dict[original_filename] = _image_dict(db_image, can_download)

        # Loop complete. If we had an exception, raise it now.
        if put_image_exception is not None:
            raise put_image_exception

    except Exception as e:
        # put_image returns ValueError for parameter errors
        if type(e) is ValueError:
            e = ParameterError(str(e))
        # Attach whatever data we have to return with the error
        # Caller can then decide whether to continue if some files worked
        e.api_data = ret_dict
        raise e
    finally:
        # Store the result for the upload_complete page
        cache_engine.raw_put(
            'UPLOAD_API:' + str(current_user.id),
            ret_dict,
            expiry_secs=(60 * 60 * 24 * 7),
            integrity_check=True
        )

    # If here, all files were uploaded successfully
    return make_api_success_response(ret_dict)


def _image_dict(db_image, can_download=None):
    """
    Returns the common data dictionary for the imagedetails and upload APIs.
    Provide an Image data model object and optionally the pre-calculated
    boolean download permission. If the download permission is None,
    it is calculated for the image's folder and the current user.
    """
    if can_download is None:
        can_download = permissions_engine.is_folder_permitted(
            db_image.folder,
            FolderPermission.ACCESS_DOWNLOAD,
            get_session_user()
        )
    return {
        'src': db_image.src,
        'url': external_url_for('image', src=db_image.src),
        'id': db_image.id,
        'folder_id': db_image.folder_id,
        'title': db_image.title,
        'description': db_image.description,
        'width': db_image.width,
        'height': db_image.height,
        'download': can_download
    }
