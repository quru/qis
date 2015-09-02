#
# Quru Image Server
#
# Document:      views_pages.py
# Date started:  16 May 2011
# By:            Matt Fozard
# Purpose:       Built-in web page URLs and views
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

from datetime import datetime, timedelta
import os.path
from time import sleep

from flask import redirect, request, session

from errors import DoesNotExistError
from exif import get_exif_geo_position
from filesystem_manager import get_upload_directory, get_file_info
from filesystem_manager import get_directory_listing, path_exists
from filesystem_manager import DirectoryInfo
from filesystem_sync import auto_sync_file, auto_sync_folder
from flask_app import app
from flask_app import logger
from flask_app import cache_engine, data_engine, image_engine, permissions_engine, task_engine
from flask_util import external_url_for, internal_url_for, render_template
from flask_util import login_point, login_required
from image_attrs import ImageAttrs
from models import Folder, FolderPermission, Image, ImageHistory, User
from session_manager import get_session_user, get_session_user_id
from session_manager import log_in, log_out, logged_in
from user_auth import authenticate_user
from util import filepath_filename, filepath_parent
from util import get_timezone_code, parse_boolean
from util import strip_seps
from views_util import log_security_error


# The "About" page
@app.route('/')
def index():
    return render_template(
        'index.html'
    )


# The login page and form target
@app.route('/login/', methods=['GET', 'POST'])
@login_point(from_web=True)
def login():
    username = ''
    password = ''
    next_url = ''
    login_error = ''
    next_url_default = internal_url_for('browse')

    if request.method == 'POST':
        try:
            # Get parameters
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            next_url = request.form.get('next', '')
            if not password:
                login_error = 'You must enter your password'
            if not username:
                login_error = 'You must enter your username'
            if not login_error:
                # Log in
                user = authenticate_user(username, password, data_engine, logger)
                if user is not None:
                    if user.status == User.STATUS_ACTIVE:
                        # Success
                        log_in(user)
                        return redirect(next_url or next_url_default)
                    else:
                        login_error = 'Sorry, your account is disabled.'
                else:
                    login_error = '''Sorry, your username and password were not recognised.
                                     Please try again.'''
                    # Slow down scripted attacks
                    logger.warn('Incorrect login for username ' + username)
                    sleep(1)
        except Exception as e:
            if not log_security_error(e, request):
                logger.error('Error performing login: ' + str(e))
            if app.config['DEBUG']:
                raise
            login_error = 'Sorry, an error occurred. Please try again later.'
    else:
        # If already logged in, go to the default page
        if logged_in():
            next_url = request.args.get('next', '')
            return redirect(next_url or next_url_default)

    # Not logged in, or unsuccessful login
    return render_template(
        'login.html',
        username=username,
        next=next_url,
        err_msg=login_error
    )


# The logout page
@app.route('/logout/')
def logout():
    log_out()
    return redirect(internal_url_for('login'))


# The image API help page
@app.route('/help/')
@login_required
def image_help():
    embed = request.args.get('embed', '')

    http_server_url = external_url_for('index')
    server_url_idx = http_server_url.find(':') + 1
    server_url = http_server_url[server_url_idx:]

    help_image_attrs = ImageAttrs('test_images/cathedral.jpg')
    logo_image_attrs = ImageAttrs('test_images/quru110.png')
    logo_pad_image_attrs = ImageAttrs('test_images/quru470.png')

    available_formats = image_engine.get_image_formats()
    available_formats.sort()
    available_templates = image_engine.get_template_names()
    available_templates.sort()
    available_iccs = {}
    icc_types = image_engine.get_icc_profile_colorspaces()
    for cspace in icc_types:
        available_iccs[cspace] = image_engine.get_icc_profile_names(cspace)
        available_iccs[cspace].sort()

    default_settings_html = render_template(
        'inc_default_settings.html',
        formats=available_formats,
        templates=available_templates,
        iccs=available_iccs
    )

    return render_template(
        'image_help.html',
        embed=embed,
        subs={
            '//images.example.com/': server_url,
            'cathedral.jpg': help_image_attrs.filename(with_path=False),
            'buildings': help_image_attrs.folder_path(),
            'quru.png': logo_image_attrs.filename(with_path=False),
            'quru-padded.png': logo_pad_image_attrs.filename(with_path=False),
            'logos': logo_image_attrs.folder_path(),
            'View this page from within QIS to see the'
            ' default image settings for your server.': default_settings_html
        }
    )


# The image uploading form
@app.route('/upload/')
@login_required
def upload_form():
    # Get upload directory options, and convert path templates to actual paths
    upload_dirs = [
        get_upload_directory(i) for i in range(len(app.config['IMAGE_UPLOAD_DIRS']))
    ]
    # Add in whether the user is allowed to upload and view
    upload_dirs = [(
        udir[0],
        udir[1],
        permissions_engine.is_folder_permitted(
            udir[1],
            FolderPermission.ACCESS_UPLOAD,
            get_session_user(),
            folder_must_exist=False
        ),
        permissions_engine.is_folder_permitted(
            udir[1],
            FolderPermission.ACCESS_VIEW,
            get_session_user(),
            folder_must_exist=False
        )
    ) for udir in upload_dirs]

    # Determine which radio button to pre-select
    dir_idx = -1
    to_path = request.args.get('path', None)
    if not to_path or to_path == os.path.sep:
        # Default to the first entry that allows upload
        for (idx, udir) in enumerate(upload_dirs):
            if udir[2]:
                dir_idx = idx
                break
    else:
        # Try matching the defined paths
        to_path = strip_seps(to_path)
        for (idx, udir) in enumerate(upload_dirs):
            if strip_seps(udir[1]) == to_path:
                dir_idx = idx
                break

    # If it's a manual path, use it only if it exists
    manual_path = ''
    if dir_idx == -1 and to_path and path_exists(to_path, require_directory=True):
        manual_path = to_path

    return render_template(
        'upload.html',
        upload_dirs=upload_dirs,
        sel_radio_num=dir_idx,
        manual_path=manual_path
    )


# The post-image upload view
@app.route('/uploadcomplete/')
@login_required
def upload_complete():
    # v1.20 Multiple images - get user's last upload data
    assert get_session_user_id() > 0
    upload_results = cache_engine.raw_get(
        'UPLOAD_API:' + str(get_session_user_id()),
        integrity_check=True
    )
    if not upload_results:
        upload_results = {}

    # Only send through the images that worked
    success_images = []
    for v in upload_results.itervalues():
        if v.get('id', 0) > 0:
            success_images.append(v)

    # Folder path should be the same for all images
    image_folder = os.path.sep
    if len(success_images) > 0:
        image_folder = ImageAttrs(success_images[0]['src']).folder_path()

    return render_template(
        'upload_complete.html',
        uploaded_images=success_images,
        image_folder=image_folder
    )


# Demo page - a simple HTML and JavaScript image viewing interface
@app.route('/simpleview/')
@login_required
def simple_view_index():
    demo_image_attrs = ImageAttrs('test_images/cathedral.jpg')
    return render_template(
        'simple_view.html',
        image_src=demo_image_attrs.filename()
    )


# User's guide for the simple JavaScript image viewing interface
@app.route('/simpleview/help/')
@login_required
def simple_view_help():
    return _standard_help_page('simple_view_help.html')


# Demo page - an HTML5/JavaScript image viewing interface
@app.route('/canvasview/')
@login_required
def canvas_view_index():
    demo_image_attrs = ImageAttrs('test_images/cathedral.jpg')
    return render_template(
        'canvas_view.html',
        image_src=demo_image_attrs.filename()
    )


# User's guide for the HTML5 JavaScript image viewing interface
@app.route('/canvasview/help/')
@login_required
def canvas_view_help():
    return _standard_help_page('canvas_view_help.html')


# Demo page - a JavaScript image folder gallery
@app.route('/gallery/')
@login_required
def gallery_view_index():
    demo_image_srcs = [
        'test_images/cathedral.jpg',
        'test_images/dorset.jpg',
        'test_images/thames.jpg'
    ]
    return render_template(
        'gallery_view.html',
        image_srcs=demo_image_srcs
    )


# User's guide for the image folder gallery interface
@app.route('/gallery/help/')
@login_required
def gallery_view_help():
    return _standard_help_page('gallery_view_help.html')


# Demo page - a JavaScript image slideshow
@app.route('/slideshow/')
@login_required
def slideshow_view_index():
    demo_image_attrs = ImageAttrs('test_images/cathedral.jpg')
    return render_template(
        'slideshow_view.html',
        image_src=demo_image_attrs.filename()
    )


# User's guide for the image slideshow
@app.route('/slideshow/help/')
@login_required
def slideshow_view_help():
    return _standard_help_page('slideshow_view_help.html')


# File system browsing
@app.route('/list/')
@login_required
def browse():
    from_path = request.args.get('path', '')
    if from_path == '':
        from_path = os.path.sep

    # #2475 Default this in case of error in get_directory_listing()
    directory_info = DirectoryInfo(from_path)

    db_session = data_engine.db_get_session()
    db_committed = False
    try:
        directory_info = get_directory_listing(from_path, True)

        # Auto-populate the folders database
        db_folder = auto_sync_folder(
            from_path,
            data_engine,
            task_engine,
            _db_session=db_session
        )
        db_session.commit()
        db_committed = True

        if db_folder is not None:
            # Require view permission or file admin
            permissions_engine.ensure_folder_permitted(
                db_folder,
                FolderPermission.ACCESS_VIEW,
                get_session_user()
            )

        # Remember last path for the Browse and Upload menus
        if directory_info.exists() and db_folder:
            session['last_browse_path'] = from_path

        return render_template(
            'list.html',
            formats=image_engine.get_image_formats(),
            pathsep=os.path.sep,
            timezone=get_timezone_code(),
            directory_info=directory_info,
            folder_name=filepath_filename(from_path),
            db_info=db_folder,
            db_parent_info=db_folder.parent if db_folder else None,
            STATUS_ACTIVE=Folder.STATUS_ACTIVE
        )
    except Exception as e:
        log_security_error(e, request)
        if app.config['DEBUG']:
            raise
        return render_template(
            'list.html',
            directory_info=directory_info,
            err_msg='This folder cannot be viewed: ' + str(e)
        )
    finally:
        try:
            if not db_committed:
                db_session.rollback()
        finally:
            db_session.close()


@app.route('/publish/')
@login_required
def publish():
    src = request.args.get('src', '')
    embed = request.args.get('embed', '')

    return render_template(
        'publish.html',
        fields=ImageAttrs.validators(),
        image_info=image_engine.get_image_properties(src, False),
        embed=embed,
        src=src,
        path=filepath_parent(src)
    )


# View image details
@app.route('/details/')
@login_required
def details():
    # Get parameters
    src = request.args.get('src', '')
    reset = request.args.get('reset', None)
    src_path = ''
    try:
        # Check parameters
        if src == '':
            raise ValueError('No filename was specified.')
        if reset is not None:
            reset = parse_boolean(reset)

        file_disk_info = None
        file_image_info = None
        file_geo_info = None
        db_img = None
        db_history = None
        db_image_stats = None

        (src_path, src_filename) = os.path.split(src)

        # Require view permission or file admin
        permissions_engine.ensure_folder_permitted(
            src_path,
            FolderPermission.ACCESS_VIEW,
            get_session_user()
        )

        # Get file info from disk
        file_disk_info = get_file_info(src)
        if file_disk_info:
            # Get EXIF info
            file_image_info = image_engine.get_image_properties(src, True)
            # Get geo location if we have the relevant profile fields
            file_geo_info = get_exif_geo_position(file_image_info)

        # Reset image if requested, then remove the reset from the URL
        if reset and file_disk_info:
            image_engine.reset_image(ImageAttrs(src))
            return redirect(internal_url_for('details', src=src))

        # Get database info
        db_session = data_engine.db_get_session()
        db_commit = False
        try:
            db_img = auto_sync_file(src, data_engine, task_engine, _db_session=db_session)
            if db_img:
                # Trigger lazy load of history
                db_history = db_img.history

                # Get stats
                stats_day = data_engine.summarise_image_stats(
                    datetime.utcnow() - timedelta(days=1),
                    datetime.utcnow(),
                    db_img.id,
                    _db_session=db_session
                )
                stats_month = data_engine.summarise_image_stats(
                    datetime.utcnow() - timedelta(days=30),
                    datetime.utcnow(),
                    db_img.id,
                    _db_session=db_session
                )
                stats_day = stats_day[0] if len(stats_day) > 0 else \
                    (0, 0, 0, 0, 0, 0, 0, 0)
                stats_month = stats_month[0] if len(stats_month) > 0 else \
                    (0, 0, 0, 0, 0, 0, 0, 0)
                db_image_stats = {
                    'day': {
                        'requests': stats_day[1],
                        'views': stats_day[2],
                        'cached_views': stats_day[3],
                        'downloads': stats_day[4],
                        'bytes': stats_day[5],
                        'seconds': stats_day[6],
                        'max_seconds': stats_day[7]
                    },
                    'month': {
                        'requests': stats_month[1],
                        'views': stats_month[2],
                        'cached_views': stats_month[3],
                        'downloads': stats_month[4],
                        'bytes': stats_month[5],
                        'seconds': stats_month[6],
                        'max_seconds': stats_month[7]
                    }
                }
            db_commit = True
        finally:
            try:
                if db_commit:
                    db_session.commit()
                else:
                    db_session.rollback()
            finally:
                db_session.close()

        return render_template(
            'details.html',
            src=src,
            path=src_path,
            filename=src_filename,
            file_info=file_disk_info,
            image_info=file_image_info,
            geo_info=file_geo_info,
            db_info=db_img,
            db_history=db_history,
            db_stats=db_image_stats,
            STATUS_ACTIVE=Image.STATUS_ACTIVE,
            ACTION_DELETED=ImageHistory.ACTION_DELETED,
            ACTION_CREATED=ImageHistory.ACTION_CREATED,
            ACTION_REPLACED=ImageHistory.ACTION_REPLACED,
            ACTION_EDITED=ImageHistory.ACTION_EDITED,
            ACTION_MOVED=ImageHistory.ACTION_MOVED,
            pathsep=os.path.sep,
            timezone=get_timezone_code()
        )
    except Exception as e:
        log_security_error(e, request)
        if app.config['DEBUG']:
            raise
        return render_template(
            'details.html',
            src=src,
            path=src_path,
            err_msg='This file cannot be viewed: ' + str(e)
        )


# Edit image details
@app.route('/edit/')
@login_required
def edit():
    # Get parameters
    src = request.args.get('src', '')
    embed = request.args.get('embed', '')
    try:
        # Check parameters
        if src == '':
            raise ValueError('No filename was specified.')

        db_img = auto_sync_file(src, data_engine, task_engine)
        if not db_img or db_img.status == Image.STATUS_DELETED:
            raise DoesNotExistError(src + ' does not exist')

        # Require edit permission or file admin
        permissions_engine.ensure_folder_permitted(
            db_img.folder,
            FolderPermission.ACCESS_EDIT,
            get_session_user()
        )

        return render_template(
            'details_edit.html',
            embed=embed,
            src=src,
            db_info=db_img
        )
    except Exception as e:
        log_security_error(e, request)
        if app.config['DEBUG']:
            raise
        return render_template(
            'details_edit.html',
            embed=embed,
            src=src,
            err_msg='The file details cannot be viewed: ' + str(e)
        )


# Edit user account details, separate from the admin pages so that
# admin permission is not required
@app.route('/account/')
@login_required
def account():
    # Get parameters
    embed = request.args.get('embed', '')

    return render_template(
        'account_edit.html',
        embed=embed,
        AUTH_TYPE_PASSWORD=User.AUTH_TYPE_PASSWORD
    )


# File and folder selection
@app.route('/folder_list/')
@login_required
def folder_browse():
    from_path = request.args.get('path', '')
    show_files = request.args.get('show_files', '')
    embed = request.args.get('embed', '')
    msg = request.args.get('msg', '')
    if from_path == '':
        from_path = os.path.sep

    db_session = data_engine.db_get_session()
    db_committed = False
    try:
        # This also checks for path existence
        folder_list = get_directory_listing(from_path, True)

        # Auto-populate the folders database
        db_folder = auto_sync_folder(
            from_path,
            data_engine,
            task_engine,
            _db_session=db_session
        )
        db_session.commit()
        db_committed = True

        # Should never happen
        if db_folder is None:
            raise DoesNotExistError(from_path)

        # Require view permission or file admin
        permissions_engine.ensure_folder_permitted(
            db_folder,
            FolderPermission.ACCESS_VIEW,
            get_session_user()
        )

        return render_template(
            'folder_list.html',
            formats=image_engine.get_image_formats(),
            embed=embed,
            msg=msg,
            name=filepath_filename(from_path),
            path=from_path,
            pathsep=os.path.sep,
            parent_path=filepath_parent(from_path),
            folder_list=folder_list,
            show_files=show_files,
            db_info=db_folder,
            db_parent_info=db_folder.parent,
            STATUS_ACTIVE=Folder.STATUS_ACTIVE
        )
    except Exception as e:
        log_security_error(e, request)
        if app.config['DEBUG']:
            raise
        return render_template(
            'folder_list.html',
            embed=embed,
            msg=msg,
            name=filepath_filename(from_path),
            path=from_path,
            err_msg='This folder cannot be viewed: ' + str(e)
        )
    finally:
        try:
            if not db_committed:
                db_session.rollback()
        finally:
            db_session.close()


def _standard_help_page(template_file):
    """
    Calls and returns a render_template() with standard help page parameters.
    """
    http_server_url = external_url_for('index')
    server_url_idx = http_server_url.find(':') + 1
    server_url = http_server_url[server_url_idx:]

    return render_template(
        template_file,
        subs={
            '//images.example.com/': server_url,
            'View this page from within QIS to see a demo.': 'A demo page is [available here](..).'
        }
    )
