#
# Quru Image Server
#
# Document:      filesystem_sync.py
# Date started:  6 Dec 2012
# By:            Matt Fozard
# Purpose:       File system - Database synchronisation
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

import os
from datetime import datetime

import filesystem_manager

from errors import AlreadyExistsError, DBError, DoesNotExistError
from filesystem_manager import get_burst_path, path_exists, ensure_path_exists
from flask_app import app
from models import Folder, Image, ImageHistory, Task
from models import FolderPermission
from util import add_sep, strip_sep, strip_seps
from util import filepath_components, filepath_filename, filepath_parent, filepath_normalize
from util import get_file_extension, secure_filename, validate_filename


def on_folder_db_create(db_folder):
    """
    Callback to validate and set folder properties in the database when a new
    folder record is to be created. Returns no value on success.

    Raises a DoesNotExistError if the folder path is invalid.
    Raises a SecurityError if the folder path is outside of IMAGES_BASE_DIR.
    """
    # Throw an exception before creating db record if the path is invalid
    ensure_path_exists(db_folder.path, require_directory=True)


def on_image_db_create(db_image):
    """
    Callback to validate and set image properties in the database when a new
    image record is to be created. Returns no value on success.

    Raises a DoesNotExistError if the image path is invalid.
    Raises a SecurityError if the image path is outside of IMAGES_BASE_DIR.
    """
    # Throw an exception before creating db record if the image path is invalid
    ensure_path_exists(db_image.src, require_file=True)
    # Set the width and height attributes if possible
    set_image_properties(db_image)


def on_image_db_create_anon_history(db_image):
    """
    As for on_image_db_create, but additionally adds an anonymous image
    history record for ACTION_CREATED saying simply 'image file detected'.
    """
    on_image_db_create(db_image)
    db_image.history.append(ImageHistory(
        db_image, None, ImageHistory.ACTION_CREATED,
        'File detected: ' + db_image.src
    ))


def set_image_properties(db_image):
    """
    Sets image properties (width and height) in the database record db_image
    by reading the image file on disk.
    """
    from image_manager import ImageManager
    (w, h) = ImageManager.get_image_dimensions(db_image.src)
    db_image.width = w
    db_image.height = h


def auto_sync_file(rel_path, data_manager, task_manager,
                   anon_history=True, burst_pdf='auto', _db_session=None):
    """
    Returns the database record for an image file, creating a new record if
    required, otherwise syncing the status flag with the existence of the file.
    Returns None if the file does not exist and there is also no database record
    for the path. Otherwise the status flag of the returned image record indicates
    whether the disk file still exists.

    This method creates anonymous image history entries when anon_history is
    True. If the current user should be recorded against an action, the caller
    should set anon_history to False and manually add a history record.

    The bursting of PDF files is also initiated here. If the file exists and is a
    PDF, by default it will be burst if no burst folder already exists. Setting
    burst_pdf to False disables this, or setting burst_pdf to True will force it
    to be burst again.

    Raises a SecurityError if the image path is outside of IMAGES_BASE_DIR.
    Raises a DBError if the database record cannot be created.
    """
    db_own = (_db_session is None)
    db_session = _db_session or data_manager.db_get_session()
    db_error = False
    try:
        if path_exists(rel_path, require_file=True):
            return auto_sync_existing_file(
                rel_path,
                data_manager,
                task_manager,
                anon_history,
                burst_pdf,
                _db_session=db_session
            )
        else:
            # No file on disk; see how that compares with the database
            db_image = data_manager.get_image(src=rel_path, _db_session=db_session)
            if not db_image:
                # No file, no database record
                return None
            elif db_image.status == Image.STATUS_DELETED:
                # Database record is already deleted
                return db_image
            else:
                # We need to delete the database record
                data_manager.delete_image(
                    db_image,
                    purge=False,
                    _db_session=db_session,
                    _commit=False
                )
                # Add history
                if anon_history:
                    data_manager.add_image_history(
                        db_image, None, ImageHistory.ACTION_DELETED,
                        'File not found: ' + rel_path,
                        _db_session=db_session,
                        _commit=False
                    )
                # Check whether the file's folder might need to be deleted too
                if db_image.folder.status == Folder.STATUS_ACTIVE:
                    auto_sync_folder(
                        db_image.folder.path,
                        data_manager,
                        task_manager,
                        _db_session=db_session
                    )
                return db_image
    except:
        db_error = True
        raise
    finally:
        if db_own:
            try:
                if db_error:
                    db_session.rollback()
                else:
                    db_session.commit()
            finally:
                db_session.close()


def auto_sync_existing_file(rel_path, data_manager, task_manager,
                            anon_history=True, burst_pdf='auto', _db_session=None):
    """
    Returns the database record for an image file that is known to exist,
    creating a new record or un-deleting an old record if required,
    and always returning a value.

    This method creates anonymous image history entries when anon_history is
    True. If the current user should be recorded against an action, the caller
    should set anon_history to False and manually add a history record.

    The bursting of PDF files is also initiated here. By default, a PDF file
    will be burst if no burst folder already exists. Setting burst_pdf to False
    disables this, or setting burst_pdf to True will force it to be burst again.

    Raises a DoesNotExistError if the image path is in fact invalid.
    Raises a SecurityError if the image path is outside of IMAGES_BASE_DIR.
    Raises a DBError if the database record cannot be created.
    """
    db_own = (_db_session is None)
    db_session = _db_session or data_manager.db_get_session()
    db_error = False
    try:
        # Get (or create) db record for the file
        on_create = on_image_db_create_anon_history if anon_history \
            else on_image_db_create
        db_image = data_manager.get_or_create_image(
            rel_path, on_create, _db_session=db_session
        )
        if not db_image:
            # Not expected
            raise DBError('Failed to add image to database: ' + rel_path)

        # Burst PDF if we need to
        # TODO This would be better in on_image_db_create if we can get a task_manager without
        #      importing the one from flask_app. Needs to be compatible with the task server.
        if burst_pdf and app.config['PDF_BURST_TO_PNG']:
            can_burst = get_file_extension(rel_path) in app.config['PDF_FILE_TYPES']
            if can_burst:
                if burst_pdf == 'auto':
                    burst_pdf = not path_exists(
                        get_burst_path(rel_path),
                        require_directory=True
                    )
                if burst_pdf:
                    burst_pdf_file(rel_path, task_manager)

        if db_image.status == Image.STATUS_ACTIVE:
            # The normal case
            return db_image
        else:
            # We need to undelete the database record
            db_image.status = Image.STATUS_ACTIVE
            if anon_history:
                on_image_db_create_anon_history(db_image)
            else:
                on_image_db_create(db_image)

            # Check whether the file's folder needs to be undeleted too
            if db_image.folder.status == Folder.STATUS_DELETED:
                auto_sync_existing_folder(
                    db_image.folder.path,
                    data_manager,
                    _db_session=db_session
                )
            return db_image
    except:
        db_error = True
        raise
    finally:
        if db_own:
            try:
                if db_error:
                    db_session.rollback()
                else:
                    db_session.commit()
            finally:
                db_session.close()


def auto_sync_folder(rel_path, data_manager, task_manager,
                     anon_history=True, _db_session=None):
    """
    Returns the database record for a folder, creating a new record if required,
    otherwise syncing the status flag with the existence of the folder.
    Returns None if the folder does not exist and there is also no database record
    for the path. Otherwise the status flag of the returned folder record indicates
    whether the disk folder still exists.

    If the disk folder no longer exists, the database records for all sub-folders
    and images within are also marked as deleted. This is performed asynchronously
    as a background task. When marking the images as deleted, this method creates
    anonymous image history entries when anon_history is True. If the current
    user should be recorded against an action, the caller should set anon_history
    to False and manually add history records.

    Raises a SecurityError if the folder path is outside of IMAGES_BASE_DIR.
    Raises a DBError if the database record cannot be created.
    """
    db_own = (_db_session is None)
    db_session = _db_session or data_manager.db_get_session()
    db_error = False
    try:
        if path_exists(rel_path, require_directory=True):
            return auto_sync_existing_folder(
                rel_path,
                data_manager,
                _db_session=db_session
            )
        else:
            # No folder on disk; see how that compares with the database
            db_folder = data_manager.get_folder(folder_path=rel_path, _db_session=db_session)
            if not db_folder:
                # No folder, no database record
                return None
            elif db_folder.status == Folder.STATUS_DELETED:
                # Database record is already deleted
                return db_folder
            else:
                # We need to delete the database record and folder content.
                # This is done as an async task, as it can take a long time.
                task_manager.add_task(
                    None,
                    'Delete data for folder %d' % db_folder.id,
                    'delete_folder_data',
                    {
                        'folder_id': db_folder.id,
                        'purge': False,
                        'history_user': None,
                        'history_info': 'Containing folder deleted' if anon_history else None
                    },
                    Task.PRIORITY_NORMAL,
                    'info', 'error'
                )
                # But for returning now, set the status flag to deleted.
                # This will also prevent a duplicate delete task being created
                # the next time this function is called for the same folder.
                db_folder.status = Folder.STATUS_DELETED
                return db_folder
    except:
        db_error = True
        raise
    finally:
        if db_own:
            try:
                if db_error:
                    db_session.rollback()
                else:
                    db_session.commit()
            finally:
                db_session.close()


def auto_sync_existing_folder(rel_path, data_manager, _db_session=None):
    """
    Returns the database record for a folder that is known to exist,
    creating a new record or un-deleting an old record if required,
    and always returning a value.

    Raises a DoesNotExistError if the folder path is in fact invalid.
    Raises a SecurityError if the path is outside of IMAGES_BASE_DIR.
    Raises a DBError if the database record cannot be created.
    """
    db_own = (_db_session is None)
    db_session = _db_session or data_manager.db_get_session()
    db_error = False
    try:
        db_folder = data_manager.get_or_create_folder(
            rel_path, on_folder_db_create, _db_session=db_session
        )
        if not db_folder:
            # Not expected
            raise DBError('Failed to add folder to database: ' + rel_path)
        elif db_folder.status == Folder.STATUS_ACTIVE:
            # The normal case
            return db_folder
        else:
            # We need to undelete the database record
            db_folder.status = Folder.STATUS_ACTIVE
            on_folder_db_create(db_folder)
            # We may also need to undelete the parent folder(s)
            p_folder = db_folder.parent
            while p_folder is not None:
                if p_folder.status != Folder.STATUS_ACTIVE:
                    p_folder.status = Folder.STATUS_ACTIVE
                    on_folder_db_create(p_folder)
                    p_folder = p_folder.parent
                else:
                    break
            return db_folder
    except:
        db_error = True
        raise
    finally:
        if db_own:
            try:
                if db_error:
                    db_session.rollback()
                else:
                    db_session.commit()
            finally:
                db_session.close()


def burst_pdf_file(rel_path, task_manager):
    """
    Initiates background bursting of a PDF file. If the burst files already exist,
    they will be generated again and overwritten. This method returns immediately.
    """
    task_manager.add_task(
        None,
        'Bursting PDF ' + rel_path,
        'burst_pdf',
        {'src': rel_path},
        Task.PRIORITY_NORMAL,
        'info', 'error',
        60
    )


def move_file(db_image, target_path, user_account, data_manager, permissions_manager):
    """
    Moves an image file to the given new path and filename (the folder component
    of which must already exist), adds image history and updates the associated
    database records. The image file is effectively renamed if the folder part
    of the path remains the same.

    The user account must have Delete File permission for the source folder
    and Upload File permission for the target folder, or alternatively have
    the file admin system permission.

    This method creates and commits its own separate database connection
    so that the operation is atomic.

    Returns the updated image object.

    Raises a DoesNotExistError if the source image file does not exist
    or the target folder does not exist.
    Raises an AlreadyExistsError if the target file already exists.
    Raises an IOError or OSError if the target file cannot be created.
    Raises a ValueError if the target filename is invalid.
    Raises a DBError for database errors.
    Raises a SecurityError if the current user does not have sufficient
    permission to perform the move or if the target path is outside of
    IMAGES_BASE_DIR.
    """
    db_session = data_manager.db_get_session()
    file_moved = False
    success = False
    try:
        _validate_path_chars(target_path)
        target_path = filepath_normalize(target_path)

        # Connect db_image to our database session
        db_image = data_manager.get_image(db_image.id, _db_session=db_session)
        if not db_image:
            raise DoesNotExistError('Image ID %d does not exist' % db_image.id)

        # Save the old path for rolling back
        source_path = db_image.src
        source_folder = filepath_parent(source_path)
        source_filename = filepath_filename(source_path)

        # Get and secure the target filename
        target_folder = filepath_parent(target_path)
        target_filename = filepath_filename(target_path)
        target_filename = secure_filename(
            target_filename,
            app.config['ALLOW_UNICODE_FILENAMES']
        )
        target_path = os.path.join(target_folder, target_filename)

        # Insist on minimum a.xyz file name (else raise ValueError)
        validate_filename(target_filename)
        # Target folder must exist
        ensure_path_exists(target_folder, require_directory=True)

        # Do nothing if target path is the same as the source
        if strip_sep(db_image.src, leading=True) == strip_sep(target_path, leading=True):
            success = True
            return db_image

        # Get source and target folder data
        db_source_folder = db_image.folder
        db_target_folder = auto_sync_existing_folder(
            target_folder, data_manager, _db_session=db_session
        )
        if db_target_folder is None:
            raise DoesNotExistError(target_folder)  # Should never happen

        # Check source file exists
        ensure_path_exists(db_image.src, require_file=True)
        # Check target file does not exist (we cannot merge)
        if path_exists(target_path, require_file=True):
            raise AlreadyExistsError('Target file already exists: ' + target_path)

        renaming = (db_source_folder == db_target_folder)

        # Check permissions for source and destination folders
        permissions_manager.ensure_folder_permitted(
            db_target_folder,
            FolderPermission.ACCESS_UPLOAD,
            user_account
        )
        if not renaming:
            permissions_manager.ensure_folder_permitted(
                db_source_folder,
                FolderPermission.ACCESS_DELETE,
                user_account
            )

        # We know there's no physical target file, but if there is an
        # old (deleted) db record for the target path, purge it first
        db_old_target_image = data_manager.get_image(
            src=target_path, _db_session=db_session
        )
        if db_old_target_image:
            data_manager.delete_image(
                db_old_target_image,
                purge=True,
                _db_session=db_session,
                _commit=False
            )

        # Move the physical file
        filesystem_manager.move(source_path, target_path)
        file_moved = True

        # Update the database
        db_image.status = Image.STATUS_ACTIVE
        db_image.folder = db_target_folder
        data_manager.set_image_src(db_image, target_path)

        # Add history
        if renaming:
            history_info = 'Renamed from ' + source_filename + ' to ' + target_filename
        else:
            history_info = 'Moved from ' + source_folder + ' to ' + target_folder
        data_manager.add_image_history(
            db_image,
            user_account,
            ImageHistory.ACTION_MOVED,
            history_info,
            _db_session=db_session,
            _commit=False
        )

        # OK!
        success = True
        return db_image

    finally:
        # Rollback file move?
        if not success and file_moved:
            try:
                filesystem_manager.move(target_path, source_path)
            except:
                pass
        # Commit or rollback database
        try:
            if success:
                db_session.commit()
            else:
                db_session.rollback()
        finally:
            db_session.close()


def delete_file(db_image, user_account, data_manager, permissions_manager):
    """
    Deletes an image file, adds image history and marks as deleted the
    associated database records.

    The user account must have Delete File permission for the image's folder,
    or alternatively have the file admin system permission.

    This method creates and commits its own separate database connection
    so that the operation is atomic.

    Returns the updated image object.

    Raises an OSError if the file cannot be created.
    Raises a DBError for database errors.
    Raises a SecurityError if the current user does not have sufficient
    permission to perform the delete.
    """
    db_session = data_manager.db_get_session()
    success = False
    try:
        # Connect db_image to our database session
        db_image = data_manager.get_image(db_image.id, _db_session=db_session)
        if not db_image:
            raise DoesNotExistError('Image ID %d does not exist' % db_image.id)

        # Check permissions for the image folder
        permissions_manager.ensure_folder_permitted(
            db_image.folder,
            FolderPermission.ACCESS_DELETE,
            user_account
        )

        # Delete the physical file
        filesystem_manager.delete_file(db_image.src)

        # Update database
        if db_image.status == Image.STATUS_ACTIVE:
            data_manager.delete_image(
                db_image,
                purge=False,
                _db_session=db_session,
                _commit=False
            )
            # Add history
            data_manager.add_image_history(
                db_image,
                user_account,
                ImageHistory.ACTION_DELETED,
                'Deleted by user',
                _db_session=db_session,
                _commit=False
            )

        # OK!
        success = True
        return db_image

    finally:
        # Commit or rollback database
        try:
            if success:
                db_session.commit()
            else:
                db_session.rollback()
        finally:
            db_session.close()


def create_folder(rel_path, user_account, data_manager, permissions_manager, logger):
    """
    Creates a folder on disk and the associated database record.
    The folder path cannot be blank and should not already exist.

    The user account must have Create Folder permission for the parent folder,
    or alternatively have the file admin system permission.

    This method creates and commits its own separate database connection
    so that the operation is atomic.

    Returns the new folder object.

    Raises an AlreadyExistsError if the folder path already exists.
    Raises an OSError if the new folder cannot be created.
    Raises a ValueError if the folder path is invalid.
    Raises a DBError for database errors.
    Raises a SecurityError if the current user does not have sufficient
    permission to create the folder, or if the folder path is outside of
    IMAGES_BASE_DIR.
    """
    db_session = data_manager.db_get_session()
    success = False
    try:
        _validate_path_chars(rel_path)
        rel_path = filepath_normalize(rel_path)
        rel_path = _secure_folder_path(
            rel_path,
            True,
            app.config['ALLOW_UNICODE_FILENAMES']
        )

        # Don't allow blank path
        if strip_seps(rel_path) == '':
            raise ValueError('Folder path to create cannot be empty')
        # Check for existing (physical) path
        if path_exists(rel_path):
            raise AlreadyExistsError('Path already exists: ' + rel_path)

        # Check permissions for the (nearest existing) db parent folder
        if user_account:
            db_parent_folder = _get_nearest_parent_folder(
                rel_path, data_manager, db_session
            )
            permissions_manager.ensure_folder_permitted(
                db_parent_folder,
                FolderPermission.ACCESS_CREATE_FOLDER,
                user_account
            )

        # Create the physical folder
        filesystem_manager.make_dirs(rel_path)

        # Update the database
        db_folder = auto_sync_existing_folder(
            rel_path,
            data_manager,
            _db_session=db_session
        )

        # OK!
        logger.info(
            'Disk folder %s created by %s' %
            (rel_path, user_account.username if user_account else 'System')
        )
        success = True
        return db_folder

    finally:
        # Commit or rollback database
        try:
            if success:
                db_session.commit()
            else:
                db_session.rollback()
        finally:
            db_session.close()


def move_folder(db_folder, target_path, user_account, data_manager, permissions_manager, logger):
    """
    Moves a disk folder to the given new path (which must not already exist),
    and updates the associated database records. The folder is effectively
    renamed if the parent folder path remains the same.

    This method may take a long time, as the folder's sub-folders and images
    must also be moved, both on disk and in the database. The audit trail is
    also updated for every affected image, image IDs cached under the old path
    are cleared, and folder tree permissions are re-calculated.

    The user account must have Delete Folder permission for the original
    parent folder and Create Folder permission for the target parent folder,
    or alternatively have the file admin system permission.

    This method creates and commits its own separate database connection
    in an attempt to keep the operation is as atomic as possible. Note however
    that if there is an error moving the folder tree (in the database or on
    disk), operations already performed are not rolled back, and the database
    may become out of sync with the file system.

    Returns the updated folder object, including all affected sub-folders.

    Raises a DoesNotExistError if the source folder does not exist.
    Raises an AlreadyExistsError if the target path already exists.
    Raises an IOError or OSError on error moving the disk files or folders.
    Raises a ValueError if the source folder or target path is invalid.
    Raises a DBError for database errors.
    Raises a SecurityError if the current user does not have sufficient
    permission to perform the move or if the target path is outside of
    IMAGES_BASE_DIR.
    """
    db_session = data_manager.db_get_session()
    success = False
    try:
        _validate_path_chars(target_path)
        target_path = filepath_normalize(target_path)
        target_path = _secure_folder_path(
            target_path,
            True,
            app.config['ALLOW_UNICODE_FILENAMES']
        )
        norm_src = strip_seps(db_folder.path)
        norm_tgt = strip_seps(target_path)

        # Cannot move the root folder
        if norm_src == '':
            raise ValueError('Cannot move the root folder')
        # Don't allow blank path (move to become root) either
        if norm_tgt == '':
            raise ValueError('Target folder path cannot be empty')
        # Cannot move a folder into itself
        if norm_tgt.startswith(add_sep(norm_src)):
            raise ValueError('Cannot move a folder into itself')

        # Do nothing if target path is the same as the source
        if norm_src == norm_tgt:
            success = True
            return db_folder

        # Connect db_folder to our database session
        db_folder = data_manager.get_folder(db_folder.id, _db_session=db_session)
        if not db_folder:
            raise DoesNotExistError('Folder ID %d does not exist' % db_folder.id)

        # Source folder must exist
        ensure_path_exists(db_folder.path, require_directory=True)
        # Target folder must not yet exist (we cannot merge)
        if path_exists(target_path):
            raise AlreadyExistsError('Path already exists: ' + target_path)

        renaming = (
            strip_seps(filepath_parent(db_folder.path)) ==
            strip_seps(filepath_parent(target_path))
        )

        # Get parent folders for permissions checking
        # Target parent may not exist yet so use the closest node in the tree
        db_source_parent = db_folder.parent
        db_target_parent = _get_nearest_parent_folder(
            target_path, data_manager, db_session
        )
        # Require Create Folder permission for destination folder
        if user_account:
            permissions_manager.ensure_folder_permitted(
                db_target_parent,
                FolderPermission.ACCESS_CREATE_FOLDER,
                user_account
            )
        # Require Delete Folder permission for source parent folder
        if user_account and not renaming:
            permissions_manager.ensure_folder_permitted(
                db_source_parent,
                FolderPermission.ACCESS_DELETE_FOLDER,
                user_account
            )

        logger.info(
            'Disk folder %s is being moved to %s by %s' %
            (db_folder.path, target_path,
             user_account.username if user_account else 'System')
        )

        # We know there's no physical target folder, but if there is an
        # old (deleted) db record for the target path, purge it first.
        db_old_target_folder = data_manager.get_folder(
            folder_path=target_path, _db_session=db_session
        )
        if db_old_target_folder:
            # This recurses to purge files and sub-folders too
            data_manager.delete_folder(
                db_old_target_folder,
                purge=True,
                _db_session=db_session,
                _commit=False
            )

        # Move the disk files first, as this is the most likely thing to fail.
        # Note that this might involve moving files and directories we haven't
        # got database entries for (but that doesn't matter).
        filesystem_manager.move(db_folder.path, target_path)

        # Prep image history
        if renaming:
            history_info = 'Folder renamed from ' + filepath_filename(db_folder.path) + \
                           ' to ' + filepath_filename(target_path)
        else:
            history_info = 'Folder moved from ' + db_folder.path + ' to ' + target_path

        # Update the database
        data_manager.set_folder_path(
            db_folder,
            target_path,
            user_account,
            history_info,
            _db_session=db_session,
            _commit=False
        )

        # OK!
        logger.info(
            'Disk folder %s successfully moved to %s by %s' %
            (db_folder.path, target_path,
             user_account.username if user_account else 'System')
        )
        success = True
        return db_folder

    finally:
        # Commit or rollback database
        try:
            if success:
                db_session.commit()
            else:
                db_session.rollback()
        finally:
            db_session.close()

        # Clear folder permissions cache as folder tree has changed
        if success:
            permissions_manager.reset_folder_permissions()


def delete_folder(db_folder, user_account, data_manager, permissions_manager, logger):
    """
    Recursively deletes a disk folder, it's sub-folders and images, adds image
    deletion history, and marks as deleted all the associated database records.
    This method may therefore take a long time.

    The user account must have Delete Folder permission for the containing
    folder, or alternatively have the file admin system permission.
    The root folder cannot be deleted.

    This method creates and commits its own separate database connection
    in an attempt to keep the operation is as atomic as possible. Note however
    that if there is an error deleting the folder tree (in the database or on
    disk), operations already performed are not rolled back, and the database
    may become out of sync with the file system.

    Returns the updated folder object, including all affected sub-folders.

    Raises a ValueError if the source folder is the root folder.
    Raises an OSError on error deleting disk files or folders.
    Raises a DBError for database errors.
    Raises a SecurityError if the current user does not have sufficient
    permission to perform the delete.
    """
    db_session = data_manager.db_get_session()
    success = False
    try:
        # Connect db_folder to our database session
        db_folder = data_manager.get_folder(db_folder.id, _db_session=db_session)
        if not db_folder:
            raise DoesNotExistError('Folder ID %d does not exist' % db_folder.id)

        # Don't allow deletion of root folder
        if db_folder.is_root():
            raise ValueError('Cannot delete the root folder')

        # Require Delete Folder permission on the parent folder
        if user_account:
            permissions_manager.ensure_folder_permitted(
                db_folder.parent,
                FolderPermission.ACCESS_DELETE_FOLDER,
                user_account
            )

        logger.info(
            'Disk folder %s is being deleted by %s' %
            (db_folder.path, user_account.username if user_account else 'System')
        )

        # Delete the disk folder first, as this is the most likely thing to fail.
        # Note that this might involve deleting files and directories we haven't
        # got database entries for (but that doesn't matter).
        filesystem_manager.delete_dir(db_folder.path, recursive=True)

        # Now delete all the data
        data_manager.delete_folder(
            db_folder,
            purge=False,
            history_user=user_account,
            history_info='Folder deleted by user',
            _db_session=db_session,
            _commit=False
        )

        # OK!
        logger.info(
            'Disk folder %s successfully deleted by %s' %
            (db_folder.path, user_account.username if user_account else 'System')
        )
        success = True
        return db_folder

    finally:
        # Commit or rollback database
        try:
            if success:
                db_session.commit()
            else:
                db_session.rollback()
        finally:
            db_session.close()


def _get_nearest_parent_folder(rel_path, data_manager, db_session):
    """
    Returns the nearest active parent folder object for rel_path that
    already exists in the database.

    E.g. For rel_path a/b/c/d
    If the database contains all folders then c is returned.
    If the database contains only a and b so far then b is returned.
    If no folders in rel_path exist then the root folder is returned.

    Raises a DBError if no parent folder can be found at all
    (but this should never happen).
    """
    # Convert a/b/c/d to ['a','b','c','d']
    _, _, f_list = filepath_components(add_sep(rel_path))
    # Start at root folder
    try_path = ''
    db_parent_folder = data_manager.get_folder(
        folder_path=try_path,
        _db_session=db_session
    )
    # Then try to get more specific
    if len(f_list) > 1:
        # Loop to len-1 to stop at c in a/b/c/d
        for idx in range(len(f_list) - 1):
            try_path += (os.path.sep + f_list[idx])
            db_f = data_manager.get_folder(
                folder_path=try_path,
                _db_session=db_session
            )
            if db_f and db_f.status == Folder.STATUS_ACTIVE:
                db_parent_folder = db_f
            else:
                break
    # db_parent_folder should at least be the root folder
    if not db_parent_folder:
        raise DBError('Failed to identify a parent folder for: ' + rel_path)
    return db_parent_folder


def _validate_path_chars(path_str):
    """
    Raises a ValueError if the path starts with ".", contains ".." anywhere,
    or contains "/.". Otherwise returns no value.
    """
    if path_str.startswith('.'):
        raise ValueError('Path cannot begin with \'.\'')
    if '..' in path_str:
        raise ValueError('Path cannot contain \'..\'')
    if (os.path.sep + '.') in path_str:
        raise ValueError('Path entries cannot begin with \'.\'')


def _secure_folder_path(folderpath, skip_existing, keep_unicode):
    """
    Splits a folder path, runs each component through the secure_filename
    function, and returns the reconstituted folder path. If skip_existing
    is True, components of the path that already exist will not be modified.
    Raises a ValueError if any of the path components becomes empty.
    """
    _, _, f_list = filepath_components(add_sep(folderpath))
    built_path = ''
    for component in f_list:
        if component:
            next_path = os.path.join(built_path, component)
            if not skip_existing or not path_exists(next_path, require_directory=True):
                try:
                    component = secure_filename(component, keep_unicode)
                except ValueError as e:
                    raise ValueError(unicode(e) + u': ' + component)
            built_path = os.path.join(built_path, component)
    return built_path
