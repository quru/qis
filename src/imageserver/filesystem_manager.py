#
# Quru Image Server
#
# Document:      filesystem_manager.py
# Date started:  30 Jun 2011
# By:            Matt Fozard
# Purpose:       File system management
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
# 03 Mar 12  Matt  Apply custom file permissions for uploaded images
# 19 Mar 13  Matt  Bug fixes to support unicode paths
# 17 Jul 14  Matt  Handle possible os.chmod error when overwriting files
#

import errno
import os
import shutil
import stat
import time

from datetime import datetime, timedelta

from errors import AlreadyExistsError, DoesNotExistError, SecurityError
from flask_app import app
from util import filepath_parent


def path_exists(rel_path, require_file=False, require_directory=False):
    """
    Returns whether a relative file or directory exists (path relative to
    IMAGES_BASE_DIR). Set one of the optional parameters to require that
    the path refers specifically to either a file or a directory.

    Raises a SecurityError if the requested path and filename evaluates
    to a location outside of IMAGES_BASE_DIR.
    """
    abs_path = unicode(get_abs_path(rel_path))
    if not os.path.exists(abs_path):
        return False
    if (require_file and not os.path.isfile(abs_path)):
        return False
    if (require_directory and not os.path.isdir(abs_path)):
        return False
    return True


def ensure_path_exists(rel_path, require_file=False, require_directory=False):
    """
    Assertion function that checks for the existence of a relative file or
    directory (path relative to IMAGES_BASE_DIR). Set one of the optional
    parameters to require that the path refers specifically to either a file
    or a directory.

    Raises a DoesNotExistError if the path does not exist, or exists but is not
    of the required type. Raises a SecurityError if the requested path and
    filename evaluates to a location outside of IMAGES_BASE_DIR.

    Returns with no action if the path does exist and is of the required type.
    """
    abs_path = unicode(get_abs_path(rel_path))
    if not os.path.exists(abs_path):
        raise DoesNotExistError(u'Path \'' + rel_path + '\' does not exist')
    if (require_file and not os.path.isfile(abs_path)):
        raise DoesNotExistError(u'Path \'' + rel_path + '\' is not a file')
    if (require_directory and not os.path.isdir(abs_path)):
        raise DoesNotExistError(u'Path \'' + rel_path + '\' is not a directory')


def get_abs_path(rel_path):
    """
    Combines rel_path with IMAGES_BASE_DIR and returns the absolute path
    to a file or directory on the server. Existence of the path is not checked.

    Raises a SecurityError if the resulting path evaluates to a
    location outside of IMAGES_BASE_DIR.
    """
    # Strip any leading path char from the path
    if rel_path[0:1] == '/' or rel_path[0:1] == '\\':
        rel_path = rel_path[1:]
    # Security check path
    abs_path_base = os.path.abspath(app.config['IMAGES_BASE_DIR'])
    abs_path = os.path.abspath(os.path.join(abs_path_base, rel_path))
    if not abs_path.startswith(abs_path_base):
        raise SecurityError(u'Requested path \'' + rel_path + '\' lies outside of IMAGES_BASE_DIR')
    return abs_path


def put_file_data(file_wrapper, dest_path, filename, create_path=False, overwrite_existing=False):
    """
    Saves a Werkzeug FileStorage object 'file_wrapper' into the relative
    directory path given by 'dest_path' and with file name 'filename'.
    When 'create_path' is True, 'dest_path' will be created inside
    IMAGES_BASE_DIR if it does not exist. When 'overwrite_existing' is True,
    any existing file with the same name will be replaced.

    Raises an IOError if the file could not be saved.
    Raises an AlreadyExistsError if the file already exists and
    'overwrite_existing' is False. Raises a DoesNotExistError if 'create_path'
    is False and 'dest_path' does not exist. Raises an OSError if 'create_path'
    is True and 'dest_path' cannot be created. Raises a SecurityError if the
    requested path and filename evaluates to a location outside of IMAGES_BASE_DIR.
    """
    # Test/create destination directory
    if not path_exists(dest_path):
        if create_path:
            make_dirs(dest_path)
        else:
            raise DoesNotExistError(u'Path \'' + dest_path + '\' does not exist')
    # Get (and security check) the absolute file path
    abs_path = unicode(get_abs_path(os.path.join(dest_path, filename)))
    # Check for file existence
    if os.path.exists(abs_path) and not overwrite_existing:
        raise AlreadyExistsError(
            u'File \'' + filename + '\' already exists at this location on the server'
        )
    # Save the file
    file_wrapper.save(abs_path, 65536)
    # (Try to) set the file permissions
    try:
        os.chmod(abs_path, app.config['IMAGES_FILE_MODE'])
    except:
        # Not allowed if we just overwrote an existing file that was owned by
        # a different o/s user. Shouldn't error if we just created the file.
        pass


def get_file_data(rel_path):
    """
    Returns the original raw binary content of the specified file
    (path relative to IMAGES_BASE_DIR), or None if the file could not
    be read. Raises a SecurityError if the file path requested evaluates
    to a location outside of IMAGES_BASE_DIR.
    """
    try:
        # Security check, get actual path
        abs_path = get_abs_path(rel_path)
        # Read the file content
        f = open(abs_path, 'rb')
    except IOError:
        return None
    try:
        return f.read()
    finally:
        f.close()


def get_file_info(rel_path):
    """
    Returns file properties for the specified file (path relative to
    IMAGES_BASE_DIR), or None if the path resolves to a directory or if the
    file could not be read.

    On success, a dictionary is returned in the format:
    { 'path': 'yourpath/yourfile.ext', 'size': 12345, 'modified': 12345678 }
    where size is the file size in bytes, and modified is the file modification
    time in UTC seconds.

    Raises a SecurityError if the file path requested evaluates to a location
    outside of IMAGES_BASE_DIR.
    """
    try:
        # Security check, get actual path
        abs_path = unicode(get_abs_path(rel_path))
        # Check that the file exists and is a file
        if not os.path.exists(abs_path) or os.path.isdir(abs_path):
            return None
        # Read file stats
        item_stat = os.stat(abs_path)
        return {
            'path': rel_path,
            'size': item_stat[stat.ST_SIZE],
            'modified': item_stat[stat.ST_MTIME]
        }
    except OSError:
        return None


def get_burst_path(rel_path):
    """
    Returns the folder path to contain the burst files for a given file path.
    """
    return rel_path + '.d'


def get_portfolio_directory(folio):
    """
    Returns the relative path to the directory where a portfolio's export
    files will be placed.
    """
    return os.path.join(
        app.config['FOLIO_EXPORTS_DIR'],
        str(folio.id)
    )


def get_portfolio_export_file_path(folio_export):
    """
    Returns the relative path to a portfolio export (zip) file,
    or an empty string if the export has not completed.
    """
    if folio_export.filename:
        return os.path.join(
            app.config['FOLIO_EXPORTS_DIR'],
            str(folio_export.folio_id),
            folio_export.filename
        )
    return ''


def get_upload_directory(dir_index):
    """
    Returns a tuple of (display name, relative path) for a given index into
    IMAGE_UPLOAD_DIRS, where path will be fully expanded if it is a template.
    Raises a ValueError if the index provided is invalid.
    """
    # Check index is OK
    upload_dirs = app.config['IMAGE_UPLOAD_DIRS']
    if len(upload_dirs) == 0:
        raise ValueError('There are no entries defined in IMAGE_UPLOAD_DIRS.')

    # Get the name and path/template
    try:
        (dir_name, dir_path) = upload_dirs[dir_index]
    except IndexError:
        raise ValueError('Invalid index %d into IMAGE_UPLOAD_DIRS' % dir_index)

    # If the path contains date/time placeholders, apply the current time
    if dir_path.find('%') != -1:
        dir_path = time.strftime(dir_path, time.gmtime())

    return (dir_name, dir_path)


def get_directory_listing(rel_path, include_folders=False, sort=0, start=0, limit=0):
    """
    Returns a DirectoryInfo object describing all files and (optionally) folders
    in the relative path supplied, where an image_path of "" or "/" is the root
    of IMAGES_BASE_DIR. The path does not have to exist.

    The sorting value can be 0 for no sorting, 1 for case sensitive,
    or 2 for case insensitive sorting of the file/folder name.

    If a start index (zero based) is supplied, the DirectoryInfo object's internal
    list will start from this offset in the results. If a limit is supplied, the
    number of results will be capped at this value and the caller can make another
    call (with a different start index) to get the next page of results.

    Raises an OSError on error querying the underlying file system.
    Raises a SecurityError if the supplied relative path is outside IMAGES_BASE_DIR.
    """
    # Security check, get actual path
    abs_dir = unicode(get_abs_path(rel_path))
    # Check if the directory exists
    if not os.path.exists(abs_dir) or not os.path.isdir(abs_dir):
        return DirectoryInfo(rel_path, exists=False)
    # Get a basic listing
    dir_items = os.listdir(abs_dir)
    if sort > 0:
        dir_items = sorted(
            dir_items,
            key=(lambda s: s) if sort == 1 else (lambda s: s.lower())
        )
    # Convert results into a DirectoryInfo object
    res_index = -1
    res_total = 0
    dir_info = DirectoryInfo(os.path.sep if rel_path == '' else rel_path)
    for item_name in dir_items:
        if not item_name.startswith('.'):
            item_stat = os.stat(os.path.join(abs_dir, item_name))
            if include_folders or not stat.S_ISDIR(item_stat[stat.ST_MODE]):
                # Filter matches so consider this a result
                res_index += 1
                # Have we reached the start index?
                if res_index < start:
                    continue
                # Add the result
                dir_info.add_entry(
                    item_name,
                    stat.S_ISDIR(item_stat[stat.ST_MODE]),
                    item_stat[stat.ST_SIZE],
                    item_stat[stat.ST_MTIME]
                )
                # Have we reached the limit?
                res_total += 1
                if limit > 0 and res_total == limit:
                    break
    return dir_info


def get_directory_subdirs(rel_path, sort=0):
    """
    Returns a list of sub-folder names in the given relative folder path.
    The path must exist. Sub-folder names beginning with '.' are excluded.

    The sorting value can be 0 for no sorting, 1 for case sensitive,
    or 2 for case insensitive.

    Raises a DoesNotExistError if the path does not exist.
    Raises a SecurityError if the requested path is outside IMAGES_BASE_DIR.
    """
    ensure_path_exists(rel_path, require_directory=True)
    abs_dir = unicode(get_abs_path(rel_path))
    subdirs = [
        sf for sf in os.listdir(abs_dir)
        if not sf.startswith('.') and os.path.isdir(os.path.join(abs_dir, sf))
    ]
    if sort > 0:
        subdirs = sorted(
            subdirs,
            key=(lambda s: s) if sort == 1 else (lambda s: s.lower())
        )
    return subdirs


def count_files(rel_path, recurse=True, recurse_timeout_secs=0):
    """
    Counts the number of ordinary files in a relative directory path.
    No filtering of filenames is performed.
    Optionally recurses to count the files in all sub-directories too.
    When recursing, a timeout (in seconds, with fractions allowed) can be
    specified to prevent the operation from taking too long.

    Returns a (long integer, boolean) tuple for the number of files found
    and whether a timeout occurred before completion (only when recursing).

    Raises a DoesNotExistError if the path does not exist.
    Raises a SecurityError if the requested path is outside IMAGES_BASE_DIR.
    """
    ensure_path_exists(rel_path, require_directory=True)
    abs_dir = unicode(get_abs_path(rel_path))
    timed_out = False
    timeout_at = None
    total = 0L
    if recurse:
        if recurse_timeout_secs > 0:
            timeout_at = datetime.utcnow() + timedelta(seconds=recurse_timeout_secs)
        for _, _, files in os.walk(abs_dir, followlinks=True):
            total += len(files)
            if (timeout_at is not None) and (datetime.utcnow() > timeout_at):
                timed_out = True
                break
    else:
        total += len([
            f for f in os.listdir(abs_dir) if os.path.isfile(os.path.join(abs_dir, f))
        ])
    return (total, timed_out)


def make_dirs(rel_path):
    """
    Creates a directory path (including intermediate directories), relative to
    IMAGES_BASE_DIR, and applies the access mode setting IMAGES_DIR_MODE.
    Takes no action if the directory path already exists.

    Raises a SecurityError if the requested path evaluates to a location
    outside of IMAGES_BASE_DIR. Raises an OSError if the directory path cannot
    be created due to e.g. a permissions error.
    """
    abs_dir = unicode(get_abs_path(rel_path))
    old_umask = os.umask(0)
    try:
        os.makedirs(abs_dir, app.config['IMAGES_DIR_MODE'])
    except OSError as e:
        # Another process or thread could have created it
        if e.errno == errno.EEXIST:
            pass
        else:
            raise
    finally:
        os.umask(old_umask)


def copy_file(rel_src, rel_dst):
    """
    Copies a source file to a destination file or directory, both relative to
    IMAGES_BASE_DIR. File metadata is copied too (access times and mode bits,
    but not owner and group).

    Raises a SecurityError if the relative paths evaluate to a location
    outside of IMAGES_BASE_DIR. Raises an IOError or OSError if the destination
    file cannot be created or on error copying.
    """
    try:
        abs_src = get_abs_path(rel_src)
        abs_dst = get_abs_path(rel_dst)
        shutil.copy2(abs_src, abs_dst)
    except shutil.Error as e:
        raise OSError(unicode(e))


def delete_file(rel_path):
    """
    Deletes the file with path relative to IMAGES_BASE_DIR.
    Takes no action if the file does not exist.

    Raises a SecurityError if the relative path evaluates to a location
    outside of IMAGES_BASE_DIR. Raises an OSError if the file cannot be deleted.
    """
    try:
        abs_path = get_abs_path(rel_path)
        os.remove(abs_path)
    except OSError as e:
        # Another process or thread could have deleted it
        if e.errno == errno.ENOENT:
            pass
        else:
            raise


def delete_dir(rel_path, recursive=False):
    """
    Deletes a directory and optionally (if recursive is True) all its files
    and sub-directories. If recursive is False, the directory must be empty.
    The path is relative to IMAGES_BASE_DIR.
    Takes no action if the directory does not exist.

    Raises a SecurityError if the relative path evaluates to a location
    outside of IMAGES_BASE_DIR. Raises an OSError if the directory or any
    of the directory content cannot be deleted.
    """
    try:
        if path_exists(rel_path, require_directory=True):
            abs_dir = get_abs_path(rel_path)
            if recursive:
                shutil.rmtree(abs_dir, ignore_errors=False)
            else:
                os.rmdir(abs_dir)
    except shutil.Error as e:
        raise OSError(unicode(e))


def move(rel_src, rel_dst):
    """
    Moves a source file or directory to another path, both relative to
    IMAGES_BASE_DIR. File metadata is copied too (access times and mode bits,
    but not owner and group). The move is achieved by renaming if possible,
    else copying then deleting.

    Raises a SecurityError if the relative paths evaluate to a location
    outside of IMAGES_BASE_DIR. Raises an IOError or OSError if the destination
    files cannot be created or on error copying.
    """
    try:
        abs_src = get_abs_path(rel_src)
        abs_dst = get_abs_path(rel_dst)
        shutil.move(abs_src, abs_dst)
    except shutil.Error as e:
        raise OSError(unicode(e))


class DirectoryInfo(object):
    """
    Holds information about a server directory, including its total size, and
    the files and directories it contains. The contents list, if supplied,
    should be a list of dictionaries in the format: [{
        "filename": "foo.txt", "is_directory": False, "size": 1234, "modified": 1309348291
    }]
    """
    def __init__(self, name, contents_list=None, exists=True):
        self._name = name
        self._exists = exists
        self._contents = contents_list or []
        self._content_size = sum(f['size'] for f in self._contents if not f['is_directory'])

    def name(self):
        """
        Returns the path and name of this directory
        """
        return self._name

    def exists(self):
        """
        Returns whether the directory exists.
        """
        return self._exists

    def parent_name(self):
        """
        Returns the path and name of this directory's parent
        ('\\' or '/' if the parent is the root directory),
        or None if this directory is the root.
        """
        return filepath_parent(self._name)

    def size(self):
        """
        Returns the total size of all files in this directory's content list
        (not including the size of any sub-directories).
        """
        return self._content_size

    def count(self):
        """
        Returns the number of files and sub-directories in this directory's
        content list.
        """
        return len(self._contents)

    def add_entry(self, filename, is_directory, size, modified):
        """
        Adds an entry to this directory's content list. Size is the file
        size in bytes (ignored if the entry is a directory), and modified is
        the file or directory modification time in UTC seconds.
        """
        self._contents.append({
            "filename": filename,
            "is_directory": is_directory,
            "size": size,
            "modified": modified
        })
        if not is_directory:
            self._content_size += size

    def __iter__(self):
        """
        Returns an iterator over this directory's content list.
        """
        return iter(self._contents)

    def contents(self):
        """
        Returns the list of dictionaries as described for the class constructor
        that have been added with add_entry().
        """
        return self._contents

    def files(self):
        """
        Returns just the files from the contents() list.
        """
        return [f for f in self._contents if not f['is_directory']]

    def directories(self):
        """
        Returns just the sub-directories from the contents() list.
        """
        return [d for d in self._contents if d['is_directory']]
