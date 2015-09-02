#
# Quru Image Server
#
# Document:      tasks.py
# Date started:  21 Dec 2012
# By:            Matt Fozard
# Purpose:       Background tasks, shared by main app and task server
# Requires:
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

"""
Each task function should be defined to take keyword args, and the task
server will provide parameters as a dictionary from the database. Use the
_extract_parameters utility in each function to ensure that the expected
parameters are passed in. Use the _get_task utility if you need access to
the task object associated with the function call.

The Flask app context is thread local, and the task server runs tasks in
separate threads. This means that each task function needs to create its
own app context, if required.

The task server catches all exceptions raised here, handling them according
to the defined task settings.
"""

from datetime import datetime, timedelta

import requests

from errors import ParameterError


def move_folder(**kwargs):
    """
    Moves or renames a disk folder and its contents (including sub-folders),
    updates the paths of all affected images and folders in the database,
    and triggers the uncache_folder_images task for the old folder path.
    Returns the updated folder object.

    See filesystem_sync.move_folder() for possible exceptions.
    """
    from flask_app import app
    from filesystem_sync import move_folder
    from errors import DoesNotExistError
    from models import Task

    (folder_id, target_path) = _extract_parameters(['folder_id', 'path'], **kwargs)
    this_task = _get_task(**kwargs)

    # Get folder data
    db_folder = app.data_engine.get_folder(folder_id)
    if not db_folder:
        raise DoesNotExistError(str(folder_id))

    # Move
    try:
        db_folder = move_folder(
            db_folder,
            target_path,
            this_task.user,
            app.data_engine,
            app.permissions_engine,
            app.log
        )
    except ValueError as e:
        if type(e) is ValueError:
            raise ParameterError(str(e))
        else:
            raise  # Sub-classes of ValueError

    # Remove cached images for the old path (as another background task)
    app.task_engine.add_task(
        this_task.user,
        'Uncache moved images',
        'uncache_folder_images', {
            'folder_id': folder_id,
            'recursive': True
        },
        Task.PRIORITY_NORMAL,
        'debug', 'warn',
        10
    )
    return db_folder


def delete_folder(**kwargs):
    """
    Deletes a disk folder and its contents (including sub-folders),
    marks all affected images and folders as deleted in the database,
    and triggers the uncache_folder_images task. Returns the deleted
    folder object.

    See filesystem_sync.delete_folder() for possible exceptions.
    """
    from flask_app import app
    from filesystem_sync import delete_folder
    from errors import DoesNotExistError
    from models import Task

    (folder_id, ) = _extract_parameters(['folder_id'], **kwargs)
    this_task = _get_task(**kwargs)

    # Get folder data
    db_folder = app.data_engine.get_folder(folder_id)
    if not db_folder:
        raise DoesNotExistError(str(folder_id))

    # Delete
    try:
        db_folder = delete_folder(
            db_folder,
            this_task.user,
            app.data_engine,
            app.permissions_engine,
            app.log
        )
    except ValueError as e:
        if type(e) is ValueError:
            raise ParameterError(str(e))
        else:
            raise  # Sub-classes of ValueError

    # Remove cached images for old path (as another background task)
    app.task_engine.add_task(
        this_task.user,
        'Uncache deleted images',
        'uncache_folder_images', {
            'folder_id': folder_id,
            'recursive': True
        },
        Task.PRIORITY_NORMAL,
        'debug', 'warn',
        10
    )
    return db_folder


def delete_folder_data(**kwargs):
    """
    A task to delete (with purge True) or mark as deleted (with purge False)
    all data (folder, sub-folders, and images within) contained within a
    folder.

    This method should only be used to tidy up the database when the disk
    folder has already been deleted. If you want to delete a folder
    (on disk and in the database) normally, use the delete_folder() method.

    Raises an AssertionError if the folder still exists on disk
    Raises a DBError for database errors.
    """
    from flask_app import app
    from filesystem_manager import path_exists

    (folder_id, purge, history_user, history_info) = _extract_parameters(
        ['folder_id', 'purge', 'history_user', 'history_info'],
        **kwargs
    )

    # Get the folder to delete
    db_folder = app.data_engine.get_folder(folder_id)
    if not db_folder:
        app.log.warn('Folder ID %d has already been deleted' % folder_id)
        return
    # Don't continue if the folder still exists on disk
    assert not path_exists(db_folder.path, require_directory=True), \
        'Folder %s still exists on disk!' % db_folder.path
    # Otherwise carry on
    app.log.info('Deleting data for missing disk folder ' + db_folder.path)
    app.data_engine.delete_folder(
        db_folder,
        purge=purge,
        history_user=history_user,
        history_info=history_info
    )


def upload_usage_stats(**kwargs):
    """
    Gather up some system stats and do a phone-home.
    """
    import hashlib
    import json
    from __about__ import __tag__, __version__
    from flask_app import app
    from util import get_computer_id, to_iso_datetime

    report_url = app.config.get('USAGE_DATA_URL')
    if report_url:
        to_time = datetime.utcnow()
        from_time = to_time - timedelta(days=1)

        host_id = get_computer_id()
        sysdata = app.data_engine.summarise_system_stats(from_time, to_time)
        stats = {
            'requests': long(sysdata[0]) if sysdata[0] else 0,
            'views': long(sysdata[1]) if sysdata[1] else 0,
            'cached_views': long(sysdata[2]) if sysdata[2] else 0,
            'downloads': long(sysdata[3]) if sysdata[3] else 0,
            'bytes': long(sysdata[4]) if sysdata[4] else 0,
            'sum_seconds': round(float(sysdata[5]), 3) if sysdata[5] else 0,
            'max_seconds': round(float(sysdata[6]), 3) if sysdata[6] else 0
        }
        payload = {
            'tag': __tag__,
            'version': __version__,
            'host_id': host_id,
            'time': to_iso_datetime(to_time),
            'stats': stats
        }
        h = hashlib.sha256(__tag__ + '_usage_stats')
        h.update(payload['version'])
        h.update(payload['host_id'])
        h.update(payload['time'])
        h.update(str(payload['stats']['requests']))
        h.update(str(payload['stats']['bytes']))
        payload['hash'] = h.hexdigest()
        sent = requests.post(
            report_url,
            data=json.dumps(payload),
            timeout=10
        )
        app.log.info(
            'Usage statistics upload returned status %d '
            'for host ID %s' % (sent.status_code, host_id)
        )


def purge_system_stats(**kwargs):
    """
    A task to delete all system statistics that are older than the
    given UTC datetime. Raises a DBError for database errors.
    """
    from flask_app import app

    (before_time, ) = _extract_parameters(['before_time'], **kwargs)

    app.log.info('Purging system stats earlier than ' + str(before_time))
    app.data_engine.delete_system_stats(before_time)


def purge_image_stats(**kwargs):
    """
    A task to delete all image statistics that are older than the
    given UTC datetime. Raises a DBError for database errors.
    """
    from flask_app import app

    (before_time, ) = _extract_parameters(['before_time'], **kwargs)

    app.log.info('Purging image stats earlier than ' + str(before_time))
    app.data_engine.delete_image_stats(before_time)


def purge_deleted_folder_data(**kwargs):
    """
    A task to purge all image and folder records marked as deleted within
    a particular folder. Specify the root folder to purge all deleted images
    and folders in the database. Raises a DBError for database errors.
    """
    from flask_app import app

    (folder_id, ) = _extract_parameters(['folder_id'], **kwargs)

    db_folder = app.data_engine.get_folder(folder_id)
    if not db_folder:
        app.log.warn('Folder ID %d does not exist' % folder_id)
        return
    app.log.info('Purging deleted images and folders in ' + db_folder.path)
    app.data_engine.purge_deleted_folder_data(db_folder)


def delete_old_temp_files(**kwargs):
    """
    A task to purge old (older than 1 day) temp files. These are supposed
    to be deleted automatically, but ImageMagick sometimes leaves them behind.
    """
    import glob
    import os
    import stat
    from flask_app import app

    temp_file_patterns = ['magick*', 'img-libpdf*']
    delete_before_time = datetime.now() - timedelta(days=1)
    tf_count = 0
    tf_removed = 0
    tf_errors = 0
    for pattern in temp_file_patterns:
        temp_files = glob.glob(unicode(
            os.path.join(app.config['TEMP_DIR'], pattern)
        ))
        for temp_file in temp_files:
            try:
                tf_count += 1
                file_stat = os.stat(temp_file)
                if datetime.fromtimestamp(file_stat[stat.ST_MTIME]) < delete_before_time:
                    os.remove(temp_file)
                    tf_removed += 1
            except:
                tf_errors += 1
    app.log.info(
        'Found %d temp file(s), removed %d, failed on %d, skipped %d' % (
            tf_count, tf_removed, tf_errors,
            (tf_count - (tf_removed + tf_errors))
        )
    )


def uncache_image(**kwargs):
    """
    A task to delete all cached images for a particular image ID.
    """
    from flask_app import app

    (image_id, ) = _extract_parameters(['image_id'], **kwargs)
    app.image_engine._uncache_image_id(image_id)


def uncache_folder_images(**kwargs):
    """
    A task to delete all cached active images in a particular folder,
    optionally recursively.
    """
    from flask_app import app

    folder_id, recursive = _extract_parameters(
        ['folder_id', 'recursive'],
        **kwargs
    )

    db_folder = app.data_engine.get_folder(folder_id)
    if not db_folder:
        app.log.warn('Folder ID %d does not exist' % folder_id)
        return
    # Get both active and deleted, in case we are clearing deleted images
    image_ids = app.data_engine.list_image_ids(db_folder, recursive)
    for image_id in image_ids:
        app.image_engine._uncache_image_id(image_id)


def burst_pdf(**kwargs):
    """
    A task that creates a sub-folder next to a PDF file and extracts all
    pages from the PDF as PNG files into the sub-folder.
    """
    from flask_app import app
    from filesystem_manager import get_abs_path, get_burst_path, get_file_data
    from filesystem_manager import delete_dir, make_dirs, path_exists
    from filesystem_sync import delete_folder
    from imagemagick import imagemagick_burst_pdf
    from models import Folder
    from util import get_file_extension

    (src, ) = _extract_parameters(['src'], **kwargs)
    burst_folder_rel = get_burst_path(src)

    # Ensure src is a PDF
    if get_file_extension(src) not in app.config['PDF_FILE_TYPES']:
        app.log.warn('Cannot burst non-PDF file: ' + src)
        return

    # See if the burst folder already exists (in the database and on disk)
    db_folder = app.data_engine.get_folder(folder_path=burst_folder_rel)
    if db_folder is not None and db_folder.status == Folder.STATUS_ACTIVE:
        # Wipe the folder, old images, data, and uncache the old images
        delete_folder(db_folder, None, app.data_engine, None, app.log)
        deleted_ids = app.data_engine.list_image_ids(db_folder)
        for image_id in deleted_ids:
            app.image_engine._uncache_image_id(image_id)

    # See if the burst folder already exists (just on disk)
    if path_exists(burst_folder_rel, require_directory=True):
        # Wipe the folder and old images
        delete_dir(burst_folder_rel, recursive=True)

    # Create the burst folder and burst
    pdf_data = get_file_data(src)
    if pdf_data is not None:
        make_dirs(burst_folder_rel)
        burst_folder_abs = get_abs_path(burst_folder_rel)
        if not imagemagick_burst_pdf(
            pdf_data, burst_folder_abs, app.config['PDF_BURST_DPI']
        ):
            app.log.warn('Failed to burst PDF: ' + src)
    else:
        app.log.warn('Cannot burst PDF, file not found: ' + src)


def create_image_pyramid(**kwargs):
    """
    A task that creates resized versions of an image, repeatedly reducing the
    size by 50% until a target size is achieved. These are stored in the image
    cache (which must be running).
    """
    from flask_app import app
    from imageserver.image_attrs import ImageAttrs

    # Parameter notes:
    # page, format, colorspace can be None
    # target_pixels is the target width * height area
    image_id, image_src, page, iformat, colorspace, start_width, start_height, target_pixels = \
        _extract_parameters([
            'image_id', 'image_src', 'page', 'format', 'colorspace',
            'start_width', 'start_height', 'target_pixels'
        ], **kwargs)

    app.log.debug(
        'Starting pyramid images for image ID %d, start %d MP, target %d MP' % (
            image_id,
            (start_width * start_height) / 1000000,
            target_pixels / 1000000
        )
    )
    assert app.cache_engine.connected(), \
        'Cache is not connected, cannot pyramid image %s' % image_src

    # The idea here is to generate images that will be picked up by
    # ImageManager._get_base_image() for faster future image requests
    pcount = 0
    sqrt2 = 1.4142135623731
    aspect = float(start_width) / float(start_height)
    width = start_width
    height = start_height
    while (width * height) > target_pixels:
        width = int(round(width / sqrt2))
        height = int(round(width / aspect))
        # Specifies width only, so that the aspect ratio does not change.
        # Specifies format, strip, dpi, colorspace
        # to prevent the server defaults being applied.
        want_attrs = ImageAttrs(
            image_src,
            image_id,
            page=page,
            iformat=iformat,
            width=width,
            colorspace=colorspace,
            strip=False,
            dpi=0
        )
        app.log.debug('Pyramid creating %d x %d version of image ID %d' % (
            width, height, image_id
        ))
        app.image_engine.finalise_image_attrs(want_attrs)
        app.image_engine.get_image(want_attrs, cache_result=True)
        pcount += 1

    app.log.debug(
        'Pyramid created %d image(s) for image ID %d' % (pcount, image_id)
    )


def test_result_task(**kwargs):
    """
    A null task used for testing return values.
    """
    return_value, raise_exception = _extract_parameters(
        ['return_value', 'raise_exception'], **kwargs
    )
    if raise_exception:
        raise ValueError('An error happened')
    if return_value:
        return return_value


def _extract_parameters(param_list, **kwargs):
    """
    Utility function to return a tuple of one or more parameter values from
    the supplied kwargs. Values are returned in the same order as the given
    parameter names list (or tuple). A ParameterError is raised if any of the
    parameter names in param_list is not found in kwargs.
    """
    values = []
    for param in param_list:
        if param not in kwargs:
            raise ParameterError('Task parameter not supplied: ' + param)
        else:
            values.append(kwargs[param])
    return tuple(values)


def _get_task(**kwargs):
    """
    Utility function to return the task object associated with the current
    task function.
    """
    return kwargs['_task']
