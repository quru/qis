#
# Quru Image Server
#
# Document:      models.py
# Date started:  08 Aug 2011
# By:            Matt Fozard
# Purpose:       Image server SQLAlchemy-based database models
# Requires:      Flask, SQLAlchemy
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
# 19Mar2015  Matt  Added DatabaseModel base class
#

import os.path

from sqlalchemy import text
from sqlalchemy import ForeignKey
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Index
from sqlalchemy import Integer, LargeBinary, String, Table, Text
from sqlalchemy.orm import backref, relationship
from werkzeug.security import generate_password_hash, check_password_hash


class DatabaseModel(object):
    """
    Base class for all our database models.
    """
    def __unicode__(self):
        return unicode(self.__class__.__name__)

    def __str__(self):
        return self.__unicode__().encode('UTF-8')


class IDEqualityMixin(object):
    """
    Helper class to provide __eq__, __ne__, and __hash__ functionality
    for any class defining a unique 'id' attribute.
    """
    def __eq__(self, other):
        if type(other) is type(self):
            return self.id == other.id if self.id > 0 else object.__eq__(self, other)
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return self.id if self.id > 0 else object.__hash__(self)


class CacheEntry(DatabaseModel):
    """
    SQLAlchemy ORM wrapper for an entry in the image cache control database.
    """
    __table_name__ = 'cachectl'

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            CacheEntry.__table_name__, alchemy_metadata,
            # Cache object control
            Column('key', String(256), nullable=False, primary_key=True),
            Column('valuesize', BigInteger, nullable=False),
            # User searchable fields
            Column('searchfield1', BigInteger, nullable=True),
            Column('searchfield2', BigInteger, nullable=True),
            Column('searchfield3', BigInteger, nullable=True),
            Column('searchfield4', BigInteger, nullable=True),
            Column('searchfield5', BigInteger, nullable=True),
            # Value metadata
            Column('metadata', LargeBinary, nullable=True),
            # Indexes
            # Index('idx_cc_key', 'key', unique=True),  # Auto-created from primary_key
            Index('idx_cc_search', 'searchfield1', 'searchfield2')
        )

    def __init__(self, key, valuesize, searchfield1=None, searchfield2=None,
                 searchfield3=None, searchfield4=None, searchfield5=None, metadata=None):
        self.key = key
        self.valuesize = valuesize
        self.searchfield1 = searchfield1
        self.searchfield2 = searchfield2
        self.searchfield3 = searchfield3
        self.searchfield4 = searchfield4
        self.searchfield5 = searchfield5
        self.metadata = metadata


class User(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for a basic user record.
    """
    __table_name__ = 'users'

    AUTH_TYPE_PASSWORD = 1
    AUTH_TYPE_LDAP = 2

    STATUS_DELETED = 0
    STATUS_ACTIVE = 1

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            User.__table_name__, alchemy_metadata,
            Column('id', Integer, nullable=False, autoincrement=True, primary_key=True),
            Column('first_name', String(120), nullable=False),
            Column('last_name', String(120), nullable=False),
            Column('email', String(120), nullable=False),
            Column('username', String(120), nullable=False),
            Column('password', String(120), nullable=False),
            Column('auth_type', Integer, nullable=False),
            Column('allow_api', Boolean, nullable=False),
            Column('status', Integer, nullable=False),
            # Indexes
            # Index('idx_us_id', 'id', unique=True),  # Auto-created from primary_key
            Index('idx_us_username', text('lower(username)'), unique=True)
        )

    @staticmethod
    def get_alchemy_mapping_properties(table, user_group_table):
        return {
            'groups': relationship(Group, secondary=user_group_table, order_by=lambda: Group.name)
        }

    def __init__(self, first_name, last_name, email, username, password, auth_type, allow_api, status):
        self.id = None
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.username = username
        self.set_password(password)
        self.auth_type = auth_type
        self.allow_api = allow_api
        self.status = status

    def __unicode__(self):
        return self.get_full_name()

    def set_password(self, pwd):
        self.password = generate_password_hash(pwd, 'sha1') if pwd else ''

    def check_password(self, pwd):
        return check_password_hash(self.password, pwd)

    def get_full_name(self):
        fname = ' '.join((self.first_name, self.last_name)).strip()
        if not fname:
            fname = self.username
        return fname


class Group(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for a group record.
    """
    __table_name__ = 'groups'

    ID_PUBLIC = 1
    ID_EVERYONE = 2
    ID_ADMINS = 3

    GROUP_TYPE_SYSTEM = 1
    GROUP_TYPE_LOCAL = 2
    GROUP_TYPE_LDAP = 3

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            Group.__table_name__, alchemy_metadata,
            Column('id', Integer, nullable=False, autoincrement=True, primary_key=True),
            Column('name', String(120), nullable=False),
            Column('description', Text, nullable=False),
            Column('group_type', Integer, nullable=False),
            # Indexes
            # Index('idx_gp_id', 'id', unique=True),  # Auto-created from primary_key
            Index('idx_gp_name', 'name', unique=True)
        )

    @staticmethod
    def get_alchemy_mapping_properties(table, user_group_table):
        return {
            'users': relationship(User, secondary=user_group_table, order_by=lambda: User.username),
            'permissions': relationship(SystemPermissions, lazy='joined', uselist=False, cascade='all, delete-orphan'),
            'folder_permissions': relationship(FolderPermission, cascade='all, delete-orphan')
        }

    def __init__(self, name, description, group_type):
        self.id = None
        self.name = name
        self.description = description
        self.group_type = group_type

    def __unicode__(self):
        return self.name


class UserGroup(DatabaseModel):
    """
    SQLAlchemy ORM wrapper for a user-group link record.
    This class is only used internally by SQLAlchemy - these records are
    normally maintained via the user.groups or group.users properties.
    """
    __table_name__ = 'usergroups'

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            UserGroup.__table_name__, alchemy_metadata,
            Column('user_id', Integer, ForeignKey('users.id'), nullable=False, primary_key=True),
            Column('group_id', Integer, ForeignKey('groups.id'), nullable=False, primary_key=True),
            # Indexes
            # Index('idx_ugp_pk', 'user_id', 'group_id', unique=True)  # Auto-created from primary_key
        )


class SystemPermissions(DatabaseModel):
    """
    SQLAlchemy ORM wrapper for a system permissions record.
    These control access to global functions
    (all other permissions being based on the file-system/folder tree).
    """
    __table_name__ = 'syspermissions'

    PERMIT_FOLIOS = 'folios'
    PERMIT_REPORTS = 'reports'
    PERMIT_ADMIN_USERS = 'admin_users'
    PERMIT_ADMIN_FILES = 'admin_files'
    PERMIT_ADMIN_FOLIOS = 'admin_folios'
    PERMIT_ADMIN_PERMISSIONS = 'admin_permissions'
    PERMIT_SUPER_USER = 'admin_all'

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            SystemPermissions.__table_name__, alchemy_metadata,
            Column('group_id', Integer, ForeignKey('groups.id'), nullable=False, unique=True, primary_key=True),
            Column('folios', Boolean, nullable=False),
            Column('reports', Boolean, nullable=False),
            Column('admin_users', Boolean, nullable=False),
            Column('admin_files', Boolean, nullable=False),
            Column('admin_folios', Boolean, nullable=False),
            Column('admin_permissions', Boolean, nullable=False),
            Column('admin_all', Boolean, nullable=False),
            # Indexes
            # Index('idx_sysp_id', 'group_id', unique=True),  # Auto-created from primary_key
        )

    @staticmethod
    def get_alchemy_mapping_properties(table):
        return {
            'group': relationship(Group)
        }

    def __init__(self, group, folios, reports, admin_users, admin_files,
                 admin_folios, admin_permissions, admin_all):
        self.group = group
        self.folios = folios
        self.reports = reports
        self.admin_users = admin_users
        self.admin_files = admin_files
        self.admin_folios = admin_folios
        self.admin_permissions = admin_permissions
        self.admin_all = admin_all

    def __unicode__(self):
        return u'SystemPermissions: Group ' + str(self.group_id)


class Folder(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for a disk folder record.
    """
    __table_name__ = 'folders'

    STATUS_DELETED = 0
    STATUS_ACTIVE = 1

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            Folder.__table_name__, alchemy_metadata,
            Column('id', BigInteger, nullable=False, autoincrement=True, primary_key=True),
            Column('name', String(1024), nullable=False),
            Column('path', String(1024), nullable=False),
            Column('parent_id', BigInteger, ForeignKey('folders.id'), nullable=True),
            Column('status', Integer, nullable=False),
            # Indexes
            # Index('idx_fr_id', 'id', unique=True),  # Auto-created from primary_key
            Index('idx_fr_path', 'path', unique=True),
            Index('idx_fr_parent', 'parent_id')
        )

    @staticmethod
    def get_alchemy_mapping_properties(table):
        return {
            'children': relationship(
                Folder, join_depth=1,
                backref=backref('parent', remote_side=table.c.id),
                order_by=lambda: Folder.name
            )
        }

    def __init__(self, name, path, parent, status):
        self.id = None
        self.name = name
        self.path = path
        self.parent = parent
        self.status = status

    def __unicode__(self):
        return self.path

    def is_root(self):
        # Use path to avoid lazy load (rather than "parent is None")
        return self.path == '' or self.path == os.path.sep


class FolderPermission(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for a folder permissions record.
    These specify the image access levels across the folder tree, by group.
    """
    __table_name__ = 'folderpermissions'

    ACCESS_NONE = 0
    ACCESS_VIEW = 10
    ACCESS_DOWNLOAD = 20
    ACCESS_EDIT = 30
    ACCESS_UPLOAD = 40
    ACCESS_DELETE = 50
    ACCESS_CREATE_FOLDER = 60
    ACCESS_DELETE_FOLDER = 70
    ACCESS_ALL = ACCESS_DELETE_FOLDER

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            FolderPermission.__table_name__, alchemy_metadata,
            Column('id', BigInteger, nullable=False, autoincrement=True, primary_key=True),
            Column('folder_id', BigInteger, ForeignKey('folders.id'), nullable=False),
            Column('group_id', Integer, ForeignKey('groups.id'), nullable=False),
            Column('access', Integer, nullable=False),
            # Indexes
            # Index('idx_fp_id', 'id', unique=True),  # Auto-created from primary_key
            Index('idx_fp_pk', 'folder_id', 'group_id', unique=True)
        )

    @staticmethod
    def get_alchemy_mapping_properties(table):
        return {
            'group': relationship(Group),
            'folder': relationship(Folder)
        }

    def __init__(self, folder, group, access):
        self.id = None
        self.folder = folder
        self.group = group
        self.access = access

    def __unicode__(self):
        return u'FolderPermission: Folder %d + Group %d = %d' % (
            self.folder_id, self.group_id, self.access
        )


class Image(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for an image record.
    """
    __table_name__ = 'images'

    STATUS_DELETED = 0
    STATUS_ACTIVE = 1

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            Image.__table_name__, alchemy_metadata,
            Column('id', BigInteger, nullable=False, autoincrement=True, primary_key=True),
            Column('src', String(1024), nullable=False),
            Column('folder_id', BigInteger, ForeignKey('folders.id'), nullable=False),
            Column('title', String(255), nullable=False),
            Column('description', Text, nullable=False),
            Column('width', Integer, nullable=False),
            Column('height', Integer, nullable=False),
            Column('status', Integer, nullable=False),
            # Indexes
            # Index('idx_im_id', 'id', unique=True),  # Auto-created from primary_key
            Index('idx_im_src', 'src', unique=True),
            Index('idx_im_folder', 'folder_id', 'status')
        )

    @staticmethod
    def get_alchemy_mapping_properties(table):
        return {
            'folder': relationship(Folder, lazy='joined'),
            'history': relationship(
                lambda: ImageHistory, order_by=lambda: ImageHistory.id,
                cascade='all, delete-orphan'
            )
        }

    def __init__(self, src, folder, title, description, width, height, status):
        self.id = None
        self.src = src
        self.folder = folder
        self.title = title
        self.description = description
        self.width = width
        self.height = height
        self.status = status

    def __unicode__(self):
        return self.src + ' [' + str(self.width) + ',' + str(self.height) + ']'


class ImageHistory(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for an image history (audit) record.
    """
    __table_name__ = 'imagesaudit'

    ACTION_DELETED = 0
    ACTION_CREATED = 1
    ACTION_REPLACED = 2
    ACTION_EDITED = 3
    ACTION_MOVED = 4

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            ImageHistory.__table_name__, alchemy_metadata,
            Column('id', BigInteger, nullable=False, autoincrement=True, primary_key=True),
            Column('image_id', BigInteger, ForeignKey('images.id'), nullable=False),
            Column('user_id', Integer, ForeignKey('users.id'), nullable=True),
            Column('action', Integer, nullable=False),
            Column('action_info', Text, nullable=False),
            Column('action_time', DateTime, nullable=False),
            # Indexes
            Index('idx_ia_image_action', 'image_id', 'action', unique=False),
            Index('idx_ia_user', 'user_id', unique=False),
            Index('idx_ia_time', 'action_time', unique=False)
        )

    @staticmethod
    def get_alchemy_mapping_properties(table):
        return {
            'image': relationship(Image),
            'user': relationship(User, lazy='joined', innerjoin=False)
        }

    def __init__(self, image, user, action, action_info, action_time):
        self.id = None
        self.image = image
        self.user = user
        self.action = action
        self.action_info = action_info
        self.action_time = action_time

    def __unicode__(self):
        return u'Image ' + str(self.image_id) + ': Action ' + \
               str(self.action) + ' at ' + str(self.action_time)


class ImageStats(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for an image statistics record.
    """
    __table_name__ = 'imagestats'

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            ImageStats.__table_name__, alchemy_metadata,
            Column('id', BigInteger, nullable=False, autoincrement=True, primary_key=True),
            Column('image_id', BigInteger, ForeignKey('images.id'), nullable=False),
            Column('requests', BigInteger, nullable=False),
            Column('views', BigInteger, nullable=False),
            Column('cached_views', BigInteger, nullable=False),
            Column('downloads', BigInteger, nullable=False),
            Column('total_bytes', BigInteger, nullable=False),
            Column('request_seconds', Float, nullable=False),
            Column('max_request_seconds', Float, nullable=False),
            Column('from_time', DateTime, nullable=False),
            Column('to_time', DateTime, nullable=False),
            # Indexes
            Index('idx_is_image', 'image_id', 'from_time', unique=False),
            Index('idx_is_time', 'from_time', unique=False)
        )

    def __init__(self, image_id, req_count, view_count, view_cached_count, download_count,
                 total_bytes, request_seconds, max_request_seconds, from_time, to_time):
        self.id = None
        self.image_id = image_id
        self.requests = req_count
        self.views = view_count
        self.cached_views = view_cached_count
        self.downloads = download_count
        self.total_bytes = total_bytes
        self.request_seconds = request_seconds
        self.max_request_seconds = max_request_seconds
        self.from_time = from_time
        self.to_time = to_time

    def __unicode__(self):
        return u'ImageStats: ' + str(self.image_id) + ' v=' + str(self.views) + \
               ', d=' + str(self.downloads) + ' at ' + str(self.to_time)


class SystemStats(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for a system statistics record.
    """
    __table_name__ = 'systemstats'

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            SystemStats.__table_name__, alchemy_metadata,
            Column('id', BigInteger, nullable=False, autoincrement=True, primary_key=True),
            Column('requests', BigInteger, nullable=False),
            Column('views', BigInteger, nullable=False),
            Column('cached_views', BigInteger, nullable=False),
            Column('downloads', BigInteger, nullable=False),
            Column('total_bytes', BigInteger, nullable=False),
            Column('request_seconds', Float, nullable=False),
            Column('max_request_seconds', Float, nullable=False),
            Column('cpu_pc', Float, nullable=False),
            Column('memory_pc', Float, nullable=False),
            Column('cache_pc', Float, nullable=False),
            Column('from_time', DateTime, nullable=False),
            Column('to_time', DateTime, nullable=False),
            # Indexes
            Index('idx_ss_time', 'from_time', unique=True)
        )

    def __init__(self, req_count, view_count, view_cached_count, download_count,
                 total_bytes, request_seconds, max_request_seconds,
                 cpu_percent, memory_percent, cache_percent,
                 from_time, to_time):
        self.id = None
        self.requests = req_count
        self.views = view_count
        self.cached_views = view_cached_count
        self.downloads = download_count
        self.total_bytes = total_bytes
        self.request_seconds = request_seconds
        self.max_request_seconds = max_request_seconds
        self.cpu_pc = cpu_percent
        self.memory_pc = memory_percent
        self.cache_pc = cache_percent
        self.from_time = from_time
        self.to_time = to_time

    def __unicode__(self):
        return u'SystemStats: To ' + str(self.to_time)


class Task(DatabaseModel, IDEqualityMixin):
    """
    SQLAlchemy ORM wrapper for a background task record.
    """
    __table_name__ = 'tasks'

    STATUS_PENDING = 0
    STATUS_ACTIVE = 1
    STATUS_COMPLETE = 2

    PRIORITY_HIGH = 10
    PRIORITY_NORMAL = 20
    PRIORITY_LOW = 30

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            Task.__table_name__, alchemy_metadata,
            Column('id', BigInteger, nullable=False, autoincrement=True, primary_key=True),
            Column('user_id', Integer, ForeignKey('users.id'), nullable=True),
            Column('name', String(100), nullable=False),
            Column('funcname', String(100), nullable=False),
            Column('params', LargeBinary, nullable=True),
            Column('priority', Integer, nullable=False),
            Column('log_level', String(8), nullable=False),
            Column('error_log_level', String(8), nullable=False),
            Column('status', Integer, nullable=False),
            Column('result', LargeBinary, nullable=True),
            Column('lock_id', String(50), nullable=True),
            Column('keep_for', Integer, nullable=False),
            Column('keep_until', DateTime, nullable=True),
            # Indexes
            Index('idx_tk_function', 'funcname', 'params', unique=True)
        )

    @staticmethod
    def get_alchemy_mapping_properties(table):
        return {
            'user': relationship(User, lazy='joined', innerjoin=False)
        }

    def __init__(self, user, name, funcname, params, priority, log_level, error_log_level, keep_for):
        self.id = None
        self.user = user
        self.name = name
        self.funcname = funcname
        self.params = params
        self.priority = priority
        self.log_level = log_level
        self.error_log_level = error_log_level
        self.status = Task.STATUS_PENDING
        self.result = None
        self.lock_id = None
        self.keep_for = keep_for
        self.keep_until = None

    def __unicode__(self):
        return u'Task: ' + self.name


class Property(DatabaseModel):
    """
    SQLAlchemy ORM wrapper for a simple key/value properties store.
    """
    __table_name__ = 'properties'

    FOLDER_PERMISSION_VERSION = 'fp_version'

    @staticmethod
    def get_alchemy_mapping(alchemy_metadata):
        return Table(
            Property.__table_name__, alchemy_metadata,
            Column('key', String(50), nullable=False, unique=True, primary_key=True),
            Column('value', Text, nullable=True),
            # Indexes
            # Index('idx_prop_pk', 'key', unique=True)  # Auto-created from primary_key
        )

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __unicode__(self):
        return u'Property: ' + self.key + '=' + str(self.value)
