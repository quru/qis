#
# Quru Image Server
#
# Document:      permissions_manager.py
# Date started:  13 Nov 2012
# By:            Matt Fozard
# Purpose:       Permissions engine and utilities
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
# 05Apr2013  Matt  Allow folder permission checking for non-existent folders-to-be
# 01Mar2018  Matt  Added portfolio permissions calculation
#

from datetime import datetime, timedelta
import os.path
import threading
import zlib

from errors import DoesNotExistError, SecurityError
from filesystem_sync import auto_sync_folder, _get_nearest_parent_folder
from models import FolderPermission, FolioPermission, Group, Property, SystemPermissions
from util import object_to_dict_dict
from util import filepath_normalize, strip_seps
from util import KeyValueCache

FOLIO_ACCESS_TEXT = {
    FolioPermission.ACCESS_NONE: 'No',
    FolioPermission.ACCESS_VIEW: 'View',
    FolioPermission.ACCESS_DOWNLOAD: 'Download',
    FolioPermission.ACCESS_EDIT: 'Edit',
    FolioPermission.ACCESS_DELETE: 'Delete'
}

FOLDER_ACCESS_TEXT = {
    FolderPermission.ACCESS_NONE: 'No',
    FolderPermission.ACCESS_VIEW: 'View',
    FolderPermission.ACCESS_DOWNLOAD: 'Download',
    FolderPermission.ACCESS_EDIT: 'Edit',
    FolderPermission.ACCESS_UPLOAD: 'Upload',
    FolderPermission.ACCESS_DELETE: 'Delete',
    FolderPermission.ACCESS_CREATE_FOLDER: 'Create-Folder',
    FolderPermission.ACCESS_DELETE_FOLDER: 'Delete-Folder'
}

SYS_PERMISSIONS_TEXT = {
    'admin_any': 'Administration',  # Special flag
    SystemPermissions.PERMIT_FOLIOS: 'Portfolio',
    SystemPermissions.PERMIT_REPORTS: 'Reporting',
    SystemPermissions.PERMIT_ADMIN_USERS: 'User administration',
    SystemPermissions.PERMIT_ADMIN_FILES: 'File administration',
    SystemPermissions.PERMIT_ADMIN_FOLIOS: 'Portfolio administration',
    SystemPermissions.PERMIT_ADMIN_PERMISSIONS: 'Permissions administration',
    SystemPermissions.PERMIT_SUPER_USER: 'Super-user'
}


class PermissionsManager(object):
    """
    Provides permissions checking routines for the image server,
    backed by various caches for performance.

    Implementation notes:

    System permissions are calculated by combining a user's group permissions.
    Only logged-in users have system permissions.

    Folder permissions are more difficult to calculate (because they are more
    granular, span across groups, and employ inheritance) and accessing them
    requires the app's singleton instance of PermissionsManager.

    Folder permissions for unknown users are cached in our own in-memory cache.
    Because this looks only at the Public group, it has a finite (and relatively
    small) size, and entries can be stored "permanently" (until the permissions
    definitions change in the database).

    Folder permissions for logged-in users must be calculated on a per user +
    folder basis, giving potentially a very large number of combinations. These
    are cached in Memcached, entries therefore being shared among all image
    server processes, with a timeout, and subject to Memcached's LRU eviction
    policy.

    Changes made to the logic of:
        is_folder_permitted() or
        calculate_folder_permissions()
    need to be mirrored in trace_folder_permissions().
    """
    FP_CACHE_SYNC_INTERVAL = 60
    FP_CACHE_TIMEOUT = 3600

    def __init__(self, data_manager, cache_manager, task_manager, settings, logger):
        self._db = data_manager
        self._cache = cache_manager
        self._tasks = task_manager
        self._settings = settings
        self._logger = logger
        # Our current folder permissions data version number.
        # If the database has a newer version we need to re-read it.
        # If a cached item has a lower version we need to discard it.
        self._fp_data_version = 0
        self._fp_last_check = None
        self._fp_public_cache = KeyValueCache()      # Public (unknown user) folder permissions
        # Our current folio permissions data version number.
        # If the database has a newer version we need to re-read it.
        self._foliop_data_version = 0
        self._foliop_last_check = None
        self._foliop_public_cache = KeyValueCache()  # Public (unknown user) folio permissions
        # Lock flag for syncing caches
        self._data_refresh_lock = threading.Lock()

    def is_permitted(self, flag, user=None):
        """
        Returns whether a user has a particular system permission.

        The flag parameter should be the name of a system permission or a
        SystemPermissions.PERMIT constant e.g. 'admin_files'. The following special
        flag names are also supported:

        'admin_any' - any admin flag

        This method checks for superuser access automatically.
        If user is None, the returned value is always False.
        """
        if user is not None:
            sys_perms = self.calculate_system_permissions(user)
            if sys_perms is not None:
                if sys_perms.admin_all:
                    # Superuser
                    return True
                elif flag == 'admin_any':
                    # Special flag
                    return (
                        sys_perms.admin_users or sys_perms.admin_files or
                        sys_perms.admin_folios or sys_perms.admin_permissions
                    )
                else:
                    # Check just the specified flag name
                    return getattr(sys_perms, flag)
        return False

    def ensure_permitted(self, flag, user=None):
        """
        Calls is_permitted(), raising a SecurityError if the
        requested flag is not permitted, otherwise performing no action.
        """
        if not self.is_permitted(flag, user):
            raise SecurityError(
                SYS_PERMISSIONS_TEXT.get(flag, '<Unknown>') + ' permission is required'
            )

    def calculate_system_permissions(self, user):
        """
        Returns a SystemPermissions object containing a user's final/combined
        system permissions, based on the user's group membership.
        If user is None, the returned permissions are always False.
        """
        final_perms = SystemPermissions(None, False, False, False, False, False, False, False)
        if user is not None:
            db_user = user if self._db.attr_is_loaded(user, 'groups') else \
                              self._db.get_user(user.id, load_groups=True)
            for group in db_user.groups:
                group_perms = group.permissions
                final_perms.folios = final_perms.folios or group_perms.folios
                final_perms.reports = final_perms.reports or group_perms.reports
                final_perms.admin_users = final_perms.admin_users or group_perms.admin_users
                final_perms.admin_files = final_perms.admin_files or group_perms.admin_files
                final_perms.admin_folios = final_perms.admin_folios or group_perms.admin_folios
                final_perms.admin_permissions = final_perms.admin_permissions or group_perms.admin_permissions
                final_perms.admin_all = final_perms.admin_all or group_perms.admin_all
        return final_perms

    def is_portfolio_permitted(self, folio, folio_access, user=None):
        """
        Returns whether a user has the requested access level for the given
        portfolio, or alternatively has the folio administration system permission.

        The folio_access parameter should be a FolioPermission.ACCESS constant.
        If user is None, the anonymous user's permissions are checked.

        This method checks for superuser access automatically.

        Raises a ValueError if folio is None.
        Raises a DoesNotExistError if a user is provided but is not a valid user.
        """
        if folio is None:
            raise ValueError('Empty portfolio provided for permissions checking')

        # Check portfolio ownership
        if (user is not None) and (folio.owner_id == user.id):
            return True
        # Check system permissions
        if self.is_permitted(SystemPermissions.PERMIT_ADMIN_FOLIOS, user):
            return True
        # Check portfolio permissions
        level = self.calculate_portfolio_permissions(folio, user)
        return level >= folio_access

    def ensure_portfolio_permitted(self, folio, folio_access, user=None):
        """
        Calls is_portfolio_permitted(), additionally raising a SecurityError if
        the requested flag is not permitted, otherwise performing no action.
        """
        if not self.is_portfolio_permitted(folio, folio_access, user):
            raise SecurityError(
                FOLIO_ACCESS_TEXT.get(folio_access, '<Unknown>') +
                ' permission is required for portfolio ' + folio.human_id
            )

    def calculate_portfolio_permissions(self, folio, user=None):
        """
        Returns an integer indicating the highest access level that is permitted
        for a portfolio, based on all a user's groups. This value will be returned
        from cache if possible.

        If user is None, the anonymous user's permissions are checked, using
        the Public group.

        Raises a ValueError if folio is None.
        Raises a DoesNotExistError if a user is provided but is not a valid user.
        """
        if folio is None:
            raise ValueError('Empty portfolio provided for permissions checking')

        # Portfolio owners have full access
        if (user is not None) and (folio.owner_id == user.id):
            return FolioPermission.ACCESS_ALL

        # Periodically ensure our data is up to date
        self._check_data_version()

        # Try the cache first (we're only caching public permissions currently)
        if user is None:
            cache_val = self._foliop_public_cache.get(folio.id)
            if cache_val is not None:
                return cache_val

        # OK let's look at the FolioPermission records
        db_session = self._db.db_get_session()
        db_commit = False
        try:
            # Get the public group object
            db_public_group = self._db.get_group(
                group_id=Group.ID_PUBLIC,
                load_users=False,
                _db_session=db_session
            )
            if db_public_group is None:
                raise DoesNotExistError('Public group')

            # Get the Public group access
            public_permission = self._db.get_portfolio_permission(
                folio,
                db_public_group,
                _db_session=db_session
            )
            public_access = public_permission.access if (
                public_permission is not None
            ) else FolioPermission.ACCESS_NONE

            if user is None:
                # Cache and return the public access
                self._logger.debug(
                    'Public access to portfolio ' + str(folio) + ' is ' + str(public_access)
                )
                self._foliop_public_cache.set(folio.id, public_access)
                db_commit = True
                return public_access
            else:
                # Get the user's groups
                db_user = user if self._db.attr_is_loaded(user, 'groups') else \
                          self._db.get_user(user.id, load_groups=True, _db_session=db_session)
                if db_user is None:
                    raise DoesNotExistError('User %d' % user.id)

                # Get the highest permission from the user's groups
                top_permission = self._db.get_top_portfolio_permission(
                    folio,
                    db_user.groups,
                    _db_session=db_session
                )
                final_access = top_permission.access if (
                    top_permission is not None
                ) else FolioPermission.ACCESS_NONE
                final_access = max(public_access, final_access)
                self._logger.debug(
                    str(user) + ' access to portfolio ' + str(folio) + ' is ' + str(final_access)
                )
                db_commit = True
                return final_access
        finally:
            try:
                if db_commit:
                    db_session.commit()
                else:
                    db_session.rollback()
            finally:
                db_session.close()

    def is_folder_permitted(self, folder, folder_access, user=None, folder_must_exist=True):
        """
        Returns whether a user has the requested access level for the given
        folder, or alternatively has the file administration system permission.

        The folder parameter can be either a Folder object or a folder path.
        The folder_access parameter should be a FolderPermission.ACCESS constant.
        If user is None, the anonymous user's permissions are checked.
        If folder_must_exist is False, the folder parameter can be a path that
        does not yet exist (access will be checked for the nearest existing path).

        This method checks for superuser access automatically.

        Raises a ValueError if folder is None.
        Raises a DoesNotExistError if folder_must_exist is True but the folder
        is an invalid path, or if a user is provided but is not a valid user.
        """
        #     Check system permissions first as this is faster and easier
        # !!! Also update _trace_folder_permissions() if changing this !!!
        if self.is_permitted(SystemPermissions.PERMIT_ADMIN_FILES, user):
            return True
        # Check folder permissions
        level = self.calculate_folder_permissions(folder, user, folder_must_exist)
        return level >= folder_access

    def ensure_folder_permitted(self, folder, folder_access, user=None, folder_must_exist=True):
        """
        Calls is_folder_permitted(), additionally raising a SecurityError if
        the requested flag is not permitted, otherwise performing no action.
        """
        if not self.is_folder_permitted(folder, folder_access, user, folder_must_exist):
            folder_path = folder.path if hasattr(folder, 'path') else folder
            raise SecurityError(
                FOLDER_ACCESS_TEXT.get(folder_access, '<Unknown>') +
                ' permission is required for ' + folder_path
            )

    def calculate_folder_permissions(self, folder, user=None, folder_must_exist=True):
        """
        Returns an integer indicating the highest access level that is permitted
        for a folder, based on all a user's groups. This value will be returned
        from cache if possible.

        The folder parameter can be either a Folder object or a folder path.
        If user is None, the anonymous user's permissions are checked, using
        the Public group.
        If folder_must_exist is False, the folder parameter can be a path that
        does not yet exist (access will be calculated for the nearest existing
        path).

        Raises a ValueError if folder is None.
        Raises a DoesNotExistError if folder_must_exist is True but the folder
        is an invalid path, or if a user is provided but is not a valid user.
        """
        if folder is None:
            raise ValueError('Empty folder provided for permissions checking')

        folder_path = self._normalize_path(
            folder.path if hasattr(folder, 'path') else folder
        )

        # Periodically ensure our data is up to date
        self._check_data_version()
        # Note this now in case another thread changes it mid-flow further on
        current_version = self._fp_data_version

        # Try the cache first
        if user is None:
            cache_val = self._fp_public_cache.get(folder_path)
        else:
            cache_val = self._cache.raw_get(
                self._get_cache_key(user, folder_path),
                integrity_check=True
            )
        # Cache entries are (value, version)
        if cache_val and cache_val[1] == current_version:
            return cache_val[0]

        #     We need to (re)calculate the folder access
        # !!! Also update _trace_folder_permissions() if changing this !!!
        db_session = self._db.db_get_session()
        db_commit = False
        try:
            # Get the folder and public group objects
            db_folder = db_session.merge(folder, load=False) if hasattr(folder, 'path') else \
                        auto_sync_folder(folder, self._db, self._tasks, _db_session=db_session)
            db_public_group = self._db.get_group(
                group_id=Group.ID_PUBLIC,
                load_users=False,
                _db_session=db_session
            )
            # Handle non-existent folder
            if db_folder is None and not folder_must_exist:
                db_folder = _get_nearest_parent_folder(folder_path, self._db, db_session)
            # Hopefully won't need these
            if db_folder is None:
                raise DoesNotExistError(folder_path)
            if db_public_group is None:
                raise DoesNotExistError('Public group')

            # Get the Public group access
            public_permission = self._db.get_nearest_folder_permission(
                db_folder,
                db_public_group,
                _db_session=db_session
            )
            if public_permission is None:
                # Hopefully never get here
                self._logger.error('No root folder permission found for the Public group')
                public_permission = FolderPermission(
                    db_folder, db_public_group, FolderPermission.ACCESS_NONE
                )

            if user is None:
                # Debug log only
                if self._settings['DEBUG']:
                    self._logger.debug(
                        'Public access to folder ' + folder_path +
                        ' is ' + str(public_permission)
                    )
                # Add result to cache and return it
                self._fp_public_cache.set(
                    folder_path,
                    (public_permission.access, current_version)
                )
                db_commit = True
                return public_permission.access
            else:
                db_user = user if self._db.attr_is_loaded(user, 'groups') else \
                          self._db.get_user(user.id, load_groups=True, _db_session=db_session)
                # Hopefully won't need this
                if db_user is None:
                    raise DoesNotExistError('User %d' % user.id)

                # Look at access for each of the user's groups
                final_access = FolderPermission.ACCESS_NONE
                for db_user_group in db_user.groups:
                    g_permission = self._db.get_nearest_folder_permission(
                        db_folder,
                        db_user_group,
                        _db_session=db_session
                    )
                    # The final access = the highest level from all the groups
                    if g_permission is not None and g_permission.access > final_access:
                        final_access = g_permission.access
                        # Fast path
                        if final_access == FolderPermission.ACCESS_ALL:
                            break
                # Use the public group access as a fallback
                final_access = max(public_permission.access, final_access)
                # Debug log only
                if self._settings['DEBUG']:
                    self._logger.debug(
                        str(user) + '\'s access to folder ' + folder_path +
                        ' is ' + str(final_access)
                    )
                # Add result to cache and return it
                self._cache.raw_put(
                    self._get_cache_key(user, folder_path),
                    (final_access, current_version),
                    PermissionsManager.FP_CACHE_TIMEOUT,
                    integrity_check=True
                )
                db_commit = True
                return final_access

        finally:
            try:
                if db_commit:
                    db_session.commit()
                else:
                    db_session.rollback()
            finally:
                db_session.close()

    def reset(self):
        """
        Marks as expired all cached folder permissions data, for all image
        server processes, by incrementing the database data version number.
        """
        with self._data_refresh_lock:
            new_ver = self._db.increment_property(Property.FOLDER_PERMISSION_VERSION)
        self._fp_last_check = datetime.min
        self._logger.info(
            'Folder permissions setting new version ' + new_ver
        )

    def _trace_folder_permissions(self, folder, user=None, check_consistency=True):
        """
        Calculates the separate set of system and folder permissions that go to
        make up a given user's final permission for a particular folder. This
        function is for administration purposes only - it is designed to return
        verbose information and is not optimised for efficiency. It does not
        employ any caching.

        Internally, this function duplicates the logic of the "public" interfaces.
        This is not ideal, but with caching and fast paths removed, the flow is
        sufficiently different as to make code re-use impractical.
        The check_consistency parameter (default True) forces a compare of the
        output of this function with the others, and raises a ValueError if a
        result mismatch is detected. This would indicate a bug.

        If the supplied user is None, the permissions returned are for an
        anonymous user and the Public group.

        The calculated items are returned as a dictionary with the following
        entries:

        {
            'user':   User object requested (or None),
            'folder': Folder object requested,
            'groups': [
                { 'group': Public Group object including (empty) system permissions,
                  'folder_permission': FolderPermission object for Public group +
                                       nearest folder to folder requested
                },
                { 'group': Group object including system permissions,
                  'folder_permission': FolderPermission object for group +
                                       nearest folder to the folder requested
                                       (can be None)
                },
                # The user's next group
            ],
            'access': Overall access level as a FolderPermission.ACCESS constant
        }

        Raises a ValueError if folder is None or if the consistency check fails.
        Raises a DoesNotExistError if the folder or user provided is invalid.
        """
        # Work from the latest data
        # (and if checking consistency later, ensure the cache is up to date)
        self._check_data_version(_force=True)

        db_session = self._db.db_get_session()
        db_commit = False
        try:
            # Get the folder, user and public group database objects
            db_folder = self._db.get_folder(folder.id, _db_session=db_session)
            db_user = None if user is None else self._db.get_user(user.id, load_groups=True, _db_session=db_session)
            db_public_group = self._db.get_group(group_id=Group.ID_PUBLIC, load_users=False, _db_session=db_session)
            # Hopefully won't need these
            if db_folder is None:
                raise DoesNotExistError(folder.path)
            if db_public_group is None:
                raise DoesNotExistError('Public group')

            # Start the trace
            trace = {
                'user': db_user,
                'folder': db_folder,
                'groups': [],
                'access': FolderPermission.ACCESS_NONE
            }

            # Add the Public group permissions
            public_fp = self._db.get_nearest_folder_permission(
                db_folder, db_public_group,
                _load_nearest_folder=True,
                _db_session=db_session
            )
            trace['groups'].append({
                'group': db_public_group,
                'folder_permission': public_fp
            })
            if public_fp is not None:
                trace['access'] = public_fp.access

            # Add the user's group permissions
            if db_user is not None:
                for db_group in db_user.groups:
                    group_fp = self._db.get_nearest_folder_permission(
                        db_folder, db_group,
                        _load_nearest_folder=True,
                        _db_session=db_session
                    )
                    trace['groups'].append({
                        'group': db_group,
                        'folder_permission': group_fp
                    })
                    # Update overall access
                    if db_group.permissions.admin_files or db_group.permissions.admin_all:
                        trace['access'] = FolderPermission.ACCESS_ALL
                    elif group_fp is not None:
                        if group_fp.access > trace['access']:
                            trace['access'] = group_fp.access

            # Verify the result against ourself
            if check_consistency:
                sp_level = FolderPermission.ACCESS_ALL if \
                           self.is_permitted('admin_files', db_user) else \
                           FolderPermission.ACCESS_NONE
                fp_level = self.calculate_folder_permissions(db_folder, db_user)
                check_access = max(sp_level, fp_level)
                if check_access != trace['access']:
                    raise ValueError('Data integrity error. Permissions manager has access level %d but traced access level %d for folder ID %d and user ID %d.' % (
                        check_access, trace['access'], db_folder.id,
                        0 if db_user is None else db_user.id
                    ))

            db_commit = True
            return trace
        finally:
            try:
                if db_commit:
                    db_session.commit()
                else:
                    db_session.rollback()
            finally:
                db_session.close()

    def _check_data_version(self, _force=False):
        """
        Periodically checks for changes in the permissions data,
        sets the internal data version number and resets caches as necessary.
        Uses an internal lock for thread safety.
        """
        check_secs = PermissionsManager.FP_CACHE_SYNC_INTERVAL

        # Start up (folder permissions)
        if (self._fp_data_version == 0) or (self._fp_last_check is None):
            db_ver = self._db.get_object(Property, Property.FOLDER_PERMISSION_VERSION)
            self._fp_data_version = int(db_ver.value)
            self._fp_last_check = datetime.utcnow()
            self._logger.info(
                'Folder permissions initialising with version ' + str(self._fp_data_version)
            )
        # Start up (folio permissions)
        if (self._foliop_data_version == 0) or (self._foliop_last_check is None):
            db_ver = self._db.get_object(Property, Property.FOLIO_PERMISSION_VERSION)
            self._foliop_data_version = int(db_ver.value)
            self._foliop_last_check = datetime.utcnow()
            self._logger.info(
                'Portfolio permissions initialising with version ' + str(self._foliop_data_version)
            )
        # Check for newer data version (folder permissions)
        if _force or self._fp_last_check < (datetime.utcnow() - timedelta(seconds=check_secs)):
            if self._data_refresh_lock.acquire(0):  # 0 = nonblocking
                try:
                    db_ver = self._db.get_object(Property, Property.FOLDER_PERMISSION_VERSION)
                    if int(db_ver.value) != self._fp_data_version:
                        self._fp_data_version = int(db_ver.value)
                        self._fp_public_cache.clear()
                        self._logger.info(
                            'Folder permissions detected new version ' +
                            str(self._fp_data_version)
                        )
                finally:
                    self._fp_last_check = datetime.utcnow()
                    self._data_refresh_lock.release()
        # Check for newer data version (folio permissions)
        if _force or self._foliop_last_check < (datetime.utcnow() - timedelta(seconds=check_secs)):
            if self._data_refresh_lock.acquire(0):  # 0 = nonblocking
                try:
                    db_ver = self._db.get_object(Property, Property.FOLIO_PERMISSION_VERSION)
                    if int(db_ver.value) != self._foliop_data_version:
                        self._foliop_data_version = int(db_ver.value)
                        self._foliop_public_cache.clear()
                        self._logger.info(
                            'Portfolio permissions detected new version ' +
                            str(self._foliop_data_version)
                        )
                finally:
                    self._foliop_last_check = datetime.utcnow()
                    self._data_refresh_lock.release()

    def _get_cache_key(self, user, path):
        """
        Returns the cache key to use for caching a user+folder permission.
        This takes the folder path so that cache lookups can be performed
        (from the plain image API) without requiring database access.
        """
        phash = path if len(path) < 200 else (
            str(hash(path)) + '_' + str(zlib.crc32(path))
        )
        return "FPERM:" + str(user.id) + ":" + phash

    def _normalize_path(self, path):
        """
        Converts a path to a standard format (removes leading and trailing
        slashes, apart from the root folder).
        """
        np = strip_seps(filepath_normalize(path))
        return np if np else os.path.sep


def _trace_to_str(trace):
    """
    Debugging utility to convert the trace output from
    _trace_folder_permissions() to a human-readable string.
    """
    ret = ['Trace:']
    ret.append('\tUser: ' + str(trace['user'] if trace['user'] else None))
    ret.append('\tFolder: ' + str(trace['folder']))
    ret.append('\tAccess: ' + str(trace['access']))
    ret.append('\tGroups: [')
    for g in trace['groups']:
        ret.append('\t\t' + str(object_to_dict_dict(g)))
    ret.append('\t]')
    return '\n'.join(ret)
