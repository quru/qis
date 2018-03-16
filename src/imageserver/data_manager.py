#
# Quru Image Server
#
# Document:      data_manager.py
# Date started:  09 Aug 2011
# By:            Matt Fozard
# Purpose:       General purpose database access and data management.
#                Specialist areas such as stats and image caching are handled elsewhere.
# Requires:      SQLAlchemy
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
# 19Aug2011  Matt  Pass in settings to remove any dependency on imageserver package
# 30Aug2011  Matt  Added db_operation decorator to trap SQLAlchemy exceptions
#                  and prevent SQL text from reaching the outside world
# 24Feb2012  Matt  Added bulk insert support
# 19Mar2013  Matt  Added defensive checks for accidental password resets
#                  (the request.g.user getting into a database session)
#

from functools import wraps
import os.path
import datetime
import time
import zlib

import sqlalchemy
from sqlalchemy import desc, event, or_
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import eagerload, sessionmaker
from sqlalchemy.sql.expression import bindparam, func

import errors
from models import Base
from models import User, Folder, FolderPermission, Group
from models import Image, ImageTemplate, ImageHistory, ImageStats, Property
from models import SystemPermissions, SystemStats, Task, UserGroup
from models import Folio, FolioImage, FolioPermission, FolioHistory, FolioExport
from util import add_sep, strip_sep
from util import filepath_components, filepath_parent, filepath_normalize
from util import generate_password


def db_operation(f):
    """
    Defines a decorator that wraps any function to trap SQLAlchemy exceptions
    and throw them instead as a DBError, which by default hides any offending SQL.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except SQLAlchemyError as e:
            if hasattr(e, 'statement'):
                msg = str(e.args)
                if '\\n' in msg:
                    msg = msg[0:msg.find('\\n')]
                raise errors.DBError(msg, e.statement)
            else:
                raise errors.DBError(e.__class__.__name__ + ': ' + str(e))
    return wrapper


class DataManager(object):
    """
    Provides data access and management routines for the image server database,
    backed by a connection pool for performance.
    """
    LOG_SQL_TIMING = False

    def __init__(self, cache_manager, logger, db_uri, db_pool_size):
        try:
            self._db_uri = db_uri
            self._db_pool_size = db_pool_size
            self._cache = cache_manager
            self._logger = logger
            self._db = None

            if DataManager.LOG_SQL_TIMING:
                self._enable_sql_time_logging()
            self._open_db()
            self._init_db()
            self._upgrade_db()
        except OperationalError as e:
            raise errors.StartupError('Database connection error: ' + str(e))
        except BaseException as e:
            raise errors.StartupError('Data manager error: ' + type(e).__name__ + ' ' + str(e))

    def _open_db(self):
        """
        Returns a new database engine for the image management database.
        """
        db_engine = sqlalchemy.create_engine(
            self._db_uri,
            echo=False,
            echo_pool=False,
            poolclass=sqlalchemy.pool.QueuePool,
            pool_size=self._db_pool_size,
            max_overflow=1
        )
        db_engine.Session = sessionmaker(
            autocommit=False,        # Manually commit/rollback
            autoflush=True,
            expire_on_commit=False,  # Do not expire object attributes after commit
            bind=db_engine
        )
        db_engine.SessionNF = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=db_engine
        )
        self._db = db_engine

    def _reset_pool(self):
        """
        Drops all database connections and resets the connection pool.
        """
        self._db.pool.dispose()
        self._db.pool.recreate()

    @db_operation
    def db_get_session(self, autoflush=True):
        """
        Returns a database session (client connection) that can be passed to
        multiple functions to perform the stages of a single transaction.

        The caller must commit, rollback, and close the returned session
        object after use as required.

        If autoflush is set to False, pending writes will not take place
        whenever a query is issued.
        """
        return self._db.Session() if autoflush else self._db.SessionNF()

    @db_operation
    def bulk_insert(self, table_name, data, _db_session=None, _commit=True):
        """
        Performs a bulk add operation into the database, bypassing the ORM
        system for greater speed. The created data is therefore not available
        as objects (without reading them all back again).

        The insert data should be provided as a list of dictionaries, with each
        dictionary containing column name/value pairs for a single row.

        Returns the number of rows inserted.
        """
        db_session = _db_session or self._db.Session()
        try:
            ins = Base.metadata.tables[table_name].insert()
            res = db_session.execute(ins, data)
            icount = res.rowcount
            res.close()
            if _commit:
                db_session.commit()
            return icount
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def bulk_update(self, table_name, table_id_column, data_id_column, data,
                    _db_session=None, _commit=True):
        """
        Performs a bulk update operation in the database, bypassing the ORM
        system for greater speed. The updated data is therefore not available
        as objects (without reading the objects back again).

        The update data should be provided as a list of dictionaries, with each
        dictionary containing the column name/value pairs to update a single row.

        In addition to the table name, the function requires the name of the
        table's unique ID column. If the ID column name cannot be used for an
        SQL bind parameter name (e.g. it cannot in Postgres), use a different
        name in the data and pass this as the data ID column name.

        E.g. bulk_update('users', 'id', '_id', [
                 {'_id': 1, 'status': 'D'},
                 {'_id': 2, 'status': 'D'}
             ])
        Sets users.status = 'D' where users.id is 1 or 2.

        Returns the number of rows updated.
        """
        db_session = _db_session or self._db.Session()
        try:
            t = Base.metadata.tables[table_name]
            up = t.update().where(t.c[table_id_column] == bindparam(data_id_column))
            res = db_session.execute(up, data)
            icount = res.rowcount
            res.close()
            if _commit:
                db_session.commit()
            return icount
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def save_object(self, obj, refresh=False, _db_session=None, _commit=True):
        """
        For disconnected database objects, adds or updates the object in the
        database, returning the object. Raises an AlreadyExistsError if adding
        the object causes a duplicate key, or a DBError for any other problem.

        If committing and a refresh is requested, the object is re-read after
        saving so that its newly assigned ID is set. Use the object returned by
        this method, as it may be a different object to that passed in.

        Objects already attached to a database session update automatically when
        the session is flushed without the use of this method.
        """
        db_session = _db_session or self._db.Session()
        try:
            obj = db_session.merge(obj)
            if _commit:
                db_session.commit()
                if refresh:
                    db_session.refresh(obj, ['id'])
            return obj
        except IntegrityError as e:
            if _commit:
                db_session.rollback()  # Prevents InvalidRequestError at session.close()
            raise errors.AlreadyExistsError(
                'Object \'' + str(obj) + '\' contains a duplicate key'
            ) if self._is_duplicate_key(e) else e
        except SQLAlchemyError:
            if _commit:
                db_session.rollback()
            raise
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_object(self, model_class, object_id, _db_session=None):
        """
        Returns a generic database object with the given primary key ID,
        or None if there is no match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(model_class)
            return q.get(object_id)
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_user(self, user_id=0, username=None, load_groups=False,
                 _detach=False, _db_session=None):
        """
        Returns the User object with the given ID or username,
        or None if there is no match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            if not user_id and not username:
                raise ValueError('User ID or username must be provided')
            q = db_session.query(User)
            if load_groups:
                q = q.options(eagerload('groups'))
            db_user = q.get(user_id) if user_id else \
                      q.filter(func.lower(User.username) == func.lower(username)).first()
            if _detach and db_user:
                db_session.expunge(db_user)
            return db_user
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_group(self, group_id=0, groupname=None, load_users=False, _db_session=None):
        """
        Returns the Group object with the given ID or name,
        or None if there is no match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            if not group_id and not groupname:
                raise ValueError('Group ID or name must be provided')
            q = db_session.query(Group)
            if load_users:
                q = q.options(eagerload('users'))
            if group_id:
                return q.get(group_id)
            else:
                return q.filter(Group.name == groupname).first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_folder(self, folder_id=0, folder_path=None,
                   load_parent=False, load_children=False, _db_session=None):
        """
        Returns the Folder object with the given ID or path,
        or None if there is no match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            if not folder_id and folder_path is None:
                raise ValueError('Folder ID or path must be provided')
            q = db_session.query(Folder)
            if load_parent:
                q = q.options(eagerload('parent'))
            if load_children:
                q = q.options(eagerload('children'))
            if folder_id:
                return q.get(folder_id)
            else:
                return q.filter(Folder.path == self._normalize_folder_path(folder_path)).first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_image(self, image_id=0, src=None, load_history=False, _db_session=None):
        """
        Returns the Image object with the given ID or path,
        or None if there is no match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            if not image_id and not src:
                raise ValueError('Image ID or path must be provided')
            q = db_session.query(Image)
            if load_history:
                q = q.options(eagerload('history'))
            if image_id:
                return q.get(image_id)
            else:
                return q.filter(Image.src == self._normalize_image_path(src)).first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_image_template(self, template_id=0, tempname=None, _db_session=None):
        """
        Returns the ImageTemplate object with the given ID or name,
        or None if there is no match in the database.
        For general use in image processing, use the template_manager methods
        rather than loading templates directly from the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            if not template_id and not tempname:
                raise ValueError('Template ID or name must be provided')
            q = db_session.query(ImageTemplate)
            if template_id:
                return q.get(template_id)
            else:
                return q.filter(func.lower(ImageTemplate.name) == func.lower(tempname)).first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_folder_permission(self, folder, group, _db_session=None):
        """
        Returns the FolderPermission object for the given folder and group,
        or None if there is no exact match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(FolderPermission)
            q = q.filter(FolderPermission.folder == folder)
            q = q.filter(FolderPermission.group == group)
            return q.first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_nearest_folder_permission(self, folder, group, _load_nearest_folder=False, _db_session=None):
        """
        Returns the nearest FolderPermission object for the given folder and
        group. If there is no exact match for the given folder, the folder's
        parent is tried, until the root folder is reached.
        Returns None if there are no FolderPermission objects in the database
        for the folder or any of its parents (including root) for this group.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_folder = folder if self.attr_is_loaded(folder, 'parent') else \
                        self.get_folder(folder.id, _db_session=db_session)
            db_fp = None
            while (db_folder is not None) and (db_fp is None):
                db_fp = self.get_folder_permission(
                    db_folder, group, _db_session=db_session
                )
                if db_fp is None:
                    db_folder = db_folder.parent

            if db_fp is not None and _load_nearest_folder:
                _ = db_fp.folder
            return db_fp
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_portfolio(self, folio_id=0, human_id=None,
                      load_images=False, load_history=False, _db_session=None):
        """
        Returns the Folio object with the given ID or human ID,
        or None if there is no match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            if not folio_id and not human_id:
                raise ValueError('Portfolio ID or short-code must be provided')
            q = db_session.query(Folio)
            if load_images:
                q = q.options(eagerload('images'))
            if load_history:
                q = q.options(eagerload('history'))
            if folio_id:
                return q.get(folio_id)
            else:
                return q.filter(Folio.human_id == human_id).first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_portfolio_permission(self, folio, group, _db_session=None):
        """
        Returns the FolioPermission object for the given portfolio and group,
        or None if there is no exact match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(FolioPermission)
            q = q.filter(FolioPermission.folio_id == folio.id)
            q = q.filter(FolioPermission.group_id == group.id)
            return q.first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_portfolio_image(self, folio, image, _db_session=None):
        """
        Returns the FolioImage object for the given portfolio and image,
        or None if there is no exact match in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(FolioImage)
            q = q.filter(FolioImage.folio_id == folio.id)
            q = q.filter(FolioImage.image_id == image.id)
            return q.first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_top_portfolio_permission(self, folio, group_list, _db_session=None):
        """
        Returns the FolioPermission object with the highest access level for
        the given portfolio and list of groups, or returns None if there are
        no permission records for any of the groups.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(FolioPermission)
            q = q.filter(FolioPermission.folio_id == folio.id)
            q = q.filter(FolioPermission.group_id.in_([g.id for g in group_list]))
            return q.order_by(desc(FolioPermission.access)).limit(1).first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def create_user(self, user, _db_session=None, _commit=True):
        """
        Creates a new user account from the supplied User object, applies
        default permissions and records the audit history. If committing (the
        default), the user object will have its new ID property set on success.
        Raises an AlreadyExistsError if the username already exists.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_session.add(user)
            # The user must be a member of Everyone
            everyone_group = db_session.query(Group).get(Group.ID_EVERYONE)
            if everyone_group not in user.groups:
                user.groups.append(everyone_group)
            if _commit:
                db_session.commit()
                db_session.refresh(user, ['id'])  # Avoid DetachedInstanceError after session close
            self._logger.info(
                'Created new user account for username \'' + user.username +
                '\' with ID ' + str(user.id)
            )
        except IntegrityError as e:
            raise errors.AlreadyExistsError(
                'Username \'' + user.username + '\' already exists'
            ) if self._is_duplicate_key(e) else e
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def create_group(self, group, _db_session=None, _commit=True):
        """
        Creates a new group from the supplied Group object
        and applies a default system permissions record. If committing
        (the default) the group will have its new ID property set on success.
        Raises an AlreadyExistsError if the group already exists.
        """
        db_session = _db_session or self._db.Session()
        try:
            # Apply default permissions
            if not group.permissions:
                group.permissions = SystemPermissions(
                    group, False, False, False, False, False, False, False
                )
            db_session.add(group)
            if _commit:
                db_session.commit()
                db_session.refresh(group, ['id'])  # Avoid DetachedInstanceError after session close
            self._logger.info('Created new group \'' + group.name + '\'')
        except IntegrityError as e:
            raise errors.AlreadyExistsError(
                'Group \'' + group.name + '\' already exists'
            ) if self._is_duplicate_key(e) else e
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def create_folder(self, folder, _db_session=None, _commit=True):
        """
        Creates a new folder from the supplied Folder object. The folder object
        may have its path modified to a standard format, and if committing
        (the default) will have its new ID property set on success.
        Raises an AlreadyExistsError if the folder already exists.
        """
        db_session = _db_session or self._db.Session()
        try:
            folder.path = self._normalize_folder_path(folder.path)
            db_session.add(folder)
            if _commit:
                db_session.commit()
                db_session.refresh(folder, ['id'])  # Avoid DetachedInstanceError after session close
            self._logger.info('Created new folder for path: ' + folder.path)
        except IntegrityError as e:
            raise errors.AlreadyExistsError(
                'Folder \'' + folder.path + '\' already exists'
            ) if self._is_duplicate_key(e) else e
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def create_portfolio(self, folio, history_user=None, _db_session=None, _commit=True):
        """
        Creates a new portfolio from the supplied Folio object and adds the
        initial creation history. No explicit permissions are set but the
        portfolio owner and administrators will have access by default.
        If committing (the default) the object will have its new ID property
        set on success. Raises an AlreadyExistsError if another portfolio with
        the same human_id value already exists.
        """
        db_session = _db_session or self._db.Session()
        try:
            # See add_image_history() for why we need to re-get the user object
            folio.owner = db_session.query(User).get(folio.owner.id)
            # If there's no short URL provided, give it one
            if not folio.human_id:
                folio.human_id = Folio.create_human_id()
            db_session.add(folio)
            folio.history.append(self.add_portfolio_history(
                folio,
                history_user,
                FolioHistory.ACTION_CREATED,
                '',
                _db_session=db_session,
                _commit=False
            ))
            if _commit:
                db_session.commit()
                db_session.refresh(folio, ['id', 'history'])
        except IntegrityError as e:
            raise errors.AlreadyExistsError(
                'Portfolio \'' + folio.human_id + '\' already exists'
            ) if self._is_duplicate_key(e) else e
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def add_image_history(self, image, user, action, action_info, _db_session=None, _commit=True):
        """
        Creates, stores and returns a new ImageHistory object.
        The user parameter can be None for recording system actions.
        """
        db_session = _db_session or self._db.Session()
        try:
            # Get clean copies of the related records from session*.
            # Otherwise if they are detached (as the user object may well be),
            # SQLAlchemy tries to be clever and insert them, causing dupes.
            #
            # NOTE! Do not use session.merge here as that copies across the
            #       state of the provided objects. If the user object comes from
            #       request.g, the password field is blanked, and therefore this
            #       would have the side effect of wiping the user's password!
            #
            # *For image, assume it's attached if a db session is passed in.
            #
            db_image = image if _db_session \
                       else db_session.query(Image).get(image.id)
            db_user = db_session.query(User).get(user.id) if user is not None else None

            # Enforce some limit on the info text
            if action_info is None:
                action_info = ''
            if len(action_info) > 4096:
                action_info = action_info[:4093] + '...'

            history = ImageHistory(db_image, db_user, action, action_info)
            db_session.add(history)
            if _commit:
                db_session.commit()
                db_session.refresh(history, ['id'])  # Avoid DetachedInstanceError after session close
            return history
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def add_portfolio_history(self, folio, user, action, action_info, _db_session=None, _commit=True):
        """
        Creates, stores and returns a new FolioHistory object.
        The user parameter can be None for recording anonymous or system actions.
        """
        db_session = _db_session or self._db.Session()
        try:
            # See add_image_history() for why we need to re-get the user object
            db_user = db_session.query(User).get(user.id) if user is not None else None

            # Enforce some limit on the info text
            if action_info is None:
                action_info = ''
            if len(action_info) > 4096:
                action_info = action_info[:4093] + '...'

            history = FolioHistory(folio, db_user, action, action_info)
            db_session.add(history)
            if _commit:
                db_session.commit()
                db_session.refresh(history, ['id'])
            return history
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def list_objects(self, model_class, order_field=None, limit=0, _db_session=None):
        """
        Lists all objects of the given type in the database, with no filtering
        or special field loading behaviour, optionally ordered by the given
        model field, and optionally limited to a number of rows.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(model_class)
            if order_field is not None:
                q = q.order_by(order_field)
            if limit > 0:
                q = q.limit(limit)
            return q.all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def list_users(self, status=None, order_field=None, _db_session=None):
        """
        Returns all User objects, or those with the given status,
        optionally ordered by the given user field.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(User)
            if status is not None:
                q = q.filter(User.status == status)
            if order_field is not None:
                q = q.order_by(order_field)
            return q.all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def list_images(self, folder=None, status=None, order_field=None, limit=0, _db_session=None):
        """
        Returns a list of images, optionally filtered by folder and/or status,
        optionally ordered by the given image field, and optionally limited
        to a number of rows.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(Image)
            if folder is not None:
                q = q.filter(Image.folder == folder)
            if status is not None:
                q = q.filter(Image.status == status)
            if order_field is not None:
                q = q.order_by(order_field)
            if limit > 0:
                q = q.limit(limit)
            return q.all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def list_image_ids(self, folder=None, recursive=False, status=None, limit=0, _db_session=None):
        """
        Returns a list of image IDs, optionally filtered by folder (recursive
        or not), and/or status, and optionally limited to a number of rows.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(Image.id)
            if folder is not None:
                if recursive:
                    search_path = add_sep(
                        self._normalize_image_path(folder.path),
                        leading=False
                    )
                    q = q.filter(Image.src.like(search_path + '%'))
                else:
                    q = q.filter(Image.folder == folder)
            if status is not None:
                q = q.filter(Image.status == status)
            if limit > 0:
                q = q.limit(limit)

            res_tuples = q.all()
            return [r[0] for r in res_tuples]
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def list_portfolios(self, user, folio_access, _db_session=None):
        """
        Returns a list of portfolios that the given user has 'folio_access' to
        or better. If user is None, the public group access will be checked.
        """
        db_session = _db_session or self._db.Session()
        try:
            if user is not None and not self.attr_is_loaded(user, 'groups'):
                user = db_session.query(User).get(user.id)

            groups = user.groups if user is not None else [
                self.get_group(Group.ID_PUBLIC, _db_session=db_session)
            ]

            # Use a sub-query to find any good-enough FolioPermission for any of the groups
            pq = db_session.query(FolioPermission)
            pq = pq.filter(FolioPermission.folio_id == Folio.id)
            pq = pq.filter(FolioPermission.group_id.in_([g.id for g in groups]))
            pq = pq.filter(FolioPermission.access >= folio_access)

            # Return all folios owned by the user or where the sub-query returns something
            q = db_session.query(Folio)
            if user is None:
                q = q.filter(pq.exists())
            else:
                q = q.filter(or_(Folio.owner_id == user.id, pq.exists()))
            return q.order_by(Folio.name).all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_or_create_image_id(self, src, return_deleted=False, on_create=None,
                               _db_session=None):
        """
        Returns the database image ID for an image path, from cache if possible.
        If the image is not in the database, a new record is created, along with
        records for the image's folder path. The image ID will be added to cache
        if it was not there previously.

        Optional callable on_create will be called, with the unsaved new Image
        object as parameter, before a new image database record is created.

        This method does not check the validity of the supplied image path or
        populate the image attribute fields. Use on_create to do this if required.

        A value of 0 is returned if a database record already exists but has a
        status of DELETED, and if return_deleted is False (the default). Also
        when both these conditions are true, the image ID is not cached.

        A value of -1 is returned in the rare event that a new image ID cannot be
        created due to a race condition with another thread handing the same
        image path.
        """
        # Normalize src before we use it for the cache key
        src = self._normalize_image_path(src)
        # Try cache
        cache_key = self._get_id_cache_key(src)
        cache_obj = self._cache.raw_get(cache_key, integrity_check=True)
        # #1589 Check this really is a database ID
        if cache_obj is not None and not (
            isinstance(cache_obj, int) or isinstance(cache_obj, long)
        ):
            self._logger.error('Cached ID is unexpected type: ' + str(type(cache_obj)))
            cache_obj = None

        if cache_obj:
            return cache_obj
        else:
            # Try the database
            db_obj = self.get_or_create_image(src, on_create, _db_session)
            if not db_obj:
                return -1
            if db_obj.status == Image.STATUS_DELETED and not return_deleted:
                return 0
            self._cache.raw_put(cache_key, db_obj.id, integrity_check=True)
            return db_obj.id

    @db_operation
    def get_or_create_image(self, src, on_create=None, _db_session=None):
        """
        Returns the database image object for an image path. If the image is
        not in the database, a new blank record is created, along with records
        for the image's folder path. This method does not employ the cache, so
        if you only require the image ID, use get_or_create_image_id instead.

        A value of None is returned in the rare event that a new image cannot
        be created due to a race condition with another thread handing the same
        image or folder path.

        Optional callable on_create will be called, with the unsaved new Image
        object as parameter, before a new image database record is created.

        This method does not check the validity of the supplied image path or
        populate the image attribute fields. Use on_create to do this if required.
        """
        src = self._normalize_image_path(src)
        retries = 0
        while retries <= 1:
            db_session = _db_session or self._db.Session()
            try:
                db_img = self.get_image(src=src, _db_session=db_session)
                if not db_img:
                    # We need to create the image (and maybe folder) db records
                    db_img = Image(src, None, '', '', 0, 0, Image.STATUS_ACTIVE)
                    if on_create:
                        on_create(db_img)
                    # Assume caller has validated src so that folder on_create can be None
                    folder_path = filepath_parent(src)
                    db_folder = self.get_or_create_folder(
                        folder_path, on_create=None, _db_session=db_session
                    )
                    if not db_folder:
                        return None
                    db_img.folder = db_folder
                    db_session.add(db_img)
                    db_session.commit()
                    db_session.refresh(db_img, ['id'])  # Avoid DetachedInstanceError after session close
                return db_img
            except IntegrityError:
                # Duplicate key, another thread added the image before we did
                self._logger.warn(
                    'Another client added image %s to the database before us, will re-read' % src
                )
            finally:
                if not _db_session:
                    db_session.close()

            # Try again after duplicate key
            retries += 1
        # Retry loop expired, give up. This should almost never happen.
        self._logger.error('Failed to add image ' + src + ' to the database')
        return None

    @db_operation
    def get_or_create_folder(self, folder_path, on_create=None, _db_session=None):
        """
        Returns the database folder object for a folder path. If the folder is
        not in the database, a new record is created, along with records for
        all its parent folders (as necessary). This method does not employ the
        cache.

        A value of None is returned in the rare event that a new folder cannot
        be created due to a race condition with another thread handing the same
        folder path.

        Optional callable on_create will be called, with an unsaved folder
        object as parameter, before each new database record in the folder
        path chain is created.

        This method does not check the validity of the supplied folder path
        (use on_create to do this if required).
        """
        retries = 0
        while retries <= 1:
            db_session = _db_session or self._db.Session()
            try:
                db_folder = self.get_folder(folder_path=folder_path, _db_session=db_session)
                if db_folder:
                    return db_folder
                else:
                    # We need to create the folder chain. Get it as a list.
                    (_, _, f_list) = filepath_components(add_sep(folder_path))
                    # Get root folder as top level parent
                    parent_folder = self.get_folder(folder_path='', _db_session=db_session)
                    if not parent_folder:
                        raise errors.DBDataError('Root folder was not found in the database')
                    next_path = ''
                    next_folder = parent_folder
                    # Create all folders in the chain
                    for idx in range(len(f_list)):
                        next_path += (os.path.sep + f_list[idx])
                        next_folder = self.get_folder(folder_path=next_path, _db_session=db_session)
                        if not next_folder:
                            next_folder = Folder(next_path, next_path, parent_folder, Folder.STATUS_ACTIVE)
                            if on_create:
                                on_create(next_folder)
                            self.create_folder(next_folder, _db_session=db_session, _commit=False)
                        parent_folder = next_folder
                    # Apply changes and return the newly created folder
                    db_session.commit()
                    return next_folder
            except errors.AlreadyExistsError:
                # Duplicate key, another thread added the folder before we did
                self._logger.warn(
                    'Another client added folder %s to the '
                    'database before us, will re-read' % folder_path
                )
            finally:
                if not _db_session:
                    db_session.close()

            # Try again after duplicate key
            retries += 1
        # Retry loop expired, give up. This should almost never happen.
        self._logger.error('Failed to add folder ' + folder_path + ' to the database')
        return None

    @db_operation
    def delete_object(self, obj, _db_session=None, _commit=True):
        """
        Deletes a generic object from the database, with no special
        handling or consideration of related objects.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_obj = db_session.merge(obj)
            db_session.delete(db_obj)
            if _commit:
                db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_user(self, user, _db_session=None, _commit=True):
        """
        Marks a user account as deleted in the database.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_user = db_session.merge(user)
            if db_user:
                # Flag as deleted
                db_user.status = User.STATUS_DELETED
                # Update the supplied object too
                user.status = User.STATUS_DELETED
                if _commit:
                    db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_group(self, group, _db_session=None, _commit=True):
        """
        Deletes a group and its members from the database.
        Raises a ValueError if an attempt is made to delete a system group.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_group = db_session.merge(group)

            if db_group.group_type == Group.GROUP_TYPE_SYSTEM:
                raise ValueError('System groups cannot be deleted')
            if db_group.group_type == Group.GROUP_TYPE_LDAP:
                raise ValueError('Cannot delete LDAP group')

            # Auto cascades system and folder and folio permissions
            db_session.delete(db_group)
            if _commit:
                db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_image(self, image, purge=False, _db_session=None, _commit=True):
        """
        Deletes an image from the database.

        If purge is False, the image record will just have its status flag set
        to deleted. Image deletion history is not added automatically.

        If purge is True, the image record and its associated image statistics
        and audit trail will be physically deleted.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_image = db_session.merge(image)
            if purge:
                # Physically delete (manual cascade of stats and folioimages, auto cascade of history)
                db_session.query(ImageStats).filter(ImageStats.image_id == db_image.id).delete()
                db_session.query(FolioImage).filter(FolioImage.image_id == db_image.id).delete()
                db_session.delete(db_image)
            else:
                # Flag as deleted
                db_image.status = Image.STATUS_DELETED
                # Update the supplied object too
                image.status = Image.STATUS_DELETED

            if _commit:
                db_session.commit()

            # Remove the cached image ID
            cache_key = self._get_id_cache_key(db_image.src)
            self._cache.raw_delete(cache_key)
        except SQLAlchemyError:
            if _commit:
                db_session.rollback()
            raise
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_folder_permission(self, fperm, _db_session=None, _commit=True):
        """
        Deletes a folder permission entry from the database.
        Raises a ValueError if an attempt is made to delete the root folder
        permission for one of the system groups.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_fp = db_session.merge(fperm)

            if db_fp.group.group_type == Group.GROUP_TYPE_SYSTEM and db_fp.folder.is_root():
                raise ValueError('The root permission for system groups cannot be deleted')
            db_session.delete(db_fp)
            if _commit:
                db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_folder(self, folder, purge=False, history_user=None,
                      history_info=None, _db_session=None, _commit=True):
        """
        Deletes from the database a folder, all its sub-folders,
        and all the images within.

        If purge is False, the records will just have their status flags set
        to deleted. An image history user and/or description can optionally be
        supplied, in which case image history will be added to all deleted images.

        If purge is True, the folder records, image records and their associated
        image statistics and audit trails will be physically deleted.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_folder = db_session.merge(folder)

            # First recurse to delete any sub-folders
            for sub_folder in db_folder.children:
                self.delete_folder(
                    sub_folder,
                    purge=purge,
                    history_user=history_user,
                    history_info=history_info,
                    _db_session=db_session,
                    _commit=False
                )

            # Then delete the files in this folder.
            # This would be more efficient as a single delete, but there are also
            # related records and cache entries to delete so for now we'll keep it
            # slower and simple rather than fast and complicated.
            images = self.list_images(
                folder=db_folder,
                status=None if purge else Image.STATUS_ACTIVE,
                _db_session=db_session
            )
            for image in images:
                self.delete_image(
                    image,
                    purge,
                    _db_session=db_session,
                    _commit=False
                )
                if not purge and (history_user or history_info):
                    self.add_image_history(
                        image,
                        history_user,
                        ImageHistory.ACTION_DELETED,
                        history_info,
                        _db_session=db_session,
                        _commit=False
                    )

            # Then delete the folder
            if purge:
                # Physically delete, manual cascade of folder permissions
                db_session.query(FolderPermission).filter(FolderPermission.folder == db_folder).delete()
                db_session.delete(db_folder)
            else:
                # Flag as deleted
                db_folder.status = Image.STATUS_DELETED
                # Update the supplied object too
                folder.status = Image.STATUS_DELETED

            # Flush pending ops after every folder
            db_session.flush()

            if _commit:
                db_session.commit()
        except SQLAlchemyError:
            if _commit:
                db_session.rollback()
            raise
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def purge_deleted_folder_data(self, folder, _db_session=None, _commit=True):
        """
        Starting from (and including) the given folder, recursively purges from
        the database all image records flagged as deleted, and sub-folders
        flagged as deleted, if they are then empty.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_folder = db_session.merge(folder)

            # First recurse to delete sub-folder content
            for sub_folder in db_folder.children:
                self.purge_deleted_folder_data(
                    sub_folder,
                    _db_session=db_session,
                    _commit=False
                )

            # Purge "deleted" images in this folder
            images = self.list_images(
                folder=db_folder,
                status=Image.STATUS_DELETED,
                _db_session=db_session
            )
            for image in images:
                self.delete_image(
                    image,
                    purge=True,
                    _db_session=db_session,
                    _commit=False
                )

            # If this folder is flagged as deleted
            if db_folder.status == Folder.STATUS_DELETED:
                # See if there are any remaining image records
                icount = db_session.query(
                    func.count(Image.id)
                ).filter(Image.folder == db_folder).scalar()
                if icount == 0:
                    # See if there are any remaining sub-folders
                    fcount = db_session.query(
                        func.count(Folder.id)
                    ).filter(Folder.parent == db_folder).scalar()
                    # Purge this folder if it has no content
                    if fcount == 0:
                        # Physically delete, manual cascade of folder permissions
                        db_session.query(FolderPermission).filter(FolderPermission.folder == db_folder).delete()
                        db_session.delete(db_folder)

            # Flush pending ops after every folder
            db_session.flush()

            if _commit:
                db_session.commit()
        except SQLAlchemyError:
            if _commit:
                db_session.rollback()
            raise
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_latest_system_stats(self, since_time=None, _db_session=None):
        """
        Returns the latest system stats object, optionally started since a
        particular UTC datetime, or None if there are no matches.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(SystemStats)
            # Search and order by from_time to use the table index
            if since_time:
                q = q.filter(SystemStats.from_time > since_time)
            return q.order_by(desc(SystemStats.from_time)).limit(1).first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_latest_image_stats(self, image_ids, since_time, _db_session=None):
        """
        Returns an unordered list of stats objects started since a particular UTC
        datetime for a list of image IDs. The returned list may be smaller than
        the image ID list, or larger if the time parameter matches multiple objects.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(ImageStats).filter(ImageStats.image_id.in_(image_ids))
            # Search and order by from_time to use the table index
            q = q.filter(ImageStats.from_time > since_time)
            return q.all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def search_system_stats(self, from_time, to_time, _db_session=None):
        """
        Returns an ordered list of system stats objects covering the period
        from the given start up to the end UTC datetime values.
        """
        db_session = _db_session or self._db.Session()
        try:
            # Use 'from_time' for both parts of query and ordering so the index gets used
            return db_session.query(SystemStats).\
                filter(SystemStats.from_time >= from_time).\
                filter(SystemStats.from_time < to_time).\
                order_by(SystemStats.from_time).all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def search_image_stats(self, from_time, to_time, image_id=0, _db_session=None):
        """
        Returns an ordered list of image stats objects covering the period
        from the given start up to the end UTC datetime values, and optionally
        restricted to a single image ID.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(ImageStats)
            if image_id:
                q = q.filter(ImageStats.image_id == image_id)
            # Use 'from_time' for both parts of query and ordering so the index gets used
            return q.\
                filter(ImageStats.from_time >= from_time).\
                filter(ImageStats.from_time < to_time).\
                order_by(ImageStats.from_time).all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def summarise_image_stats(self, from_time, to_time, image_id=0, limit=0,
                              order_by=None, _db_session=None):
        """
        Returns a list of tuples containing summarised image stats, covering
        the period from the given start up to the end UTC datetime values.

        Each tuple has the form:
        (image_id, sum_requests, sum_views, sum_cached_views, sum_downloads,
        sum_bytes_served, sum_request_seconds, max_request_seconds)

        If an image ID is specified, only one record will be returned, or zero
        records if there are no stats for that image.
        Otherwise the limit parameter optionally sets the maximum number of rows
        to return (which is only useful if the order_by parameter is also set).

        The order_by parameter may have one of the following values:
            'image_id', 'total_requests', 'total_views', 'total_cached_views',
            'total_downloads', 'total_bytes', 'total_seconds' or 'max_seconds'.
        If the value is prefixed with a minus sign,
        descending order will be applied.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(ImageStats.image_id,
                                 func.sum(ImageStats.requests).label('total_requests'),
                                 func.sum(ImageStats.views).label('total_views'),
                                 func.sum(ImageStats.cached_views).label('total_cached_views'),
                                 func.sum(ImageStats.downloads).label('total_downloads'),
                                 func.sum(ImageStats.total_bytes).label('total_bytes'),
                                 func.sum(ImageStats.request_seconds).label('total_seconds'),
                                 func.max(ImageStats.max_request_seconds).label('max_seconds'))
            if image_id:
                q = q.filter(ImageStats.image_id == image_id)
            # Use 'from_time' for both parts of query so the index gets used
            q = q.filter(ImageStats.from_time >= from_time)
            q = q.filter(ImageStats.from_time < to_time)
            q = q.group_by(ImageStats.image_id)
            if order_by:
                if order_by.startswith('-'):
                    q = q.order_by(desc(order_by[1:]))
                else:
                    q = q.order_by(order_by)
            if not image_id and limit:
                q = q.limit(limit)
            return q.all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def summarise_system_stats(self, from_time, to_time, _db_session=None):
        """
        Returns a tuple containing summarised system stats, covering
        the period from the given start up to the end UTC datetime values.

        The tuple has the form:
        (sum_requests, sum_views, sum_cached_views, sum_downloads,
        sum_bytes_served, sum_request_seconds, max_request_seconds)

        If there is no data for the datetime range, all tuple values are None.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(func.sum(SystemStats.requests),
                                 func.sum(SystemStats.views),
                                 func.sum(SystemStats.cached_views),
                                 func.sum(SystemStats.downloads),
                                 func.sum(SystemStats.total_bytes),
                                 func.sum(SystemStats.request_seconds),
                                 func.max(SystemStats.max_request_seconds))
            # Use 'from_time' so the index gets used
            q = q.filter(SystemStats.from_time >= from_time)
            q = q.filter(SystemStats.from_time < to_time)
            return q.first()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_system_stats(self, up_to_time, _db_session=None, _commit=True):
        """
        Deletes all system stats up until the given UTC datetime value.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_session.query(SystemStats).\
                filter(SystemStats.from_time < up_to_time).\
                delete()
            if _commit:
                db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_image_stats(self, up_to_time, _db_session=None, _commit=True):
        """
        Deletes all image stats up until the given UTC datetime value.
        """
        db_session = _db_session or self._db.Session()
        try:
            db_session.query(ImageStats).\
                filter(ImageStats.from_time < up_to_time).\
                delete()
            if _commit:
                db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def get_pending_tasks(self, limit=0, _db_session=None):
        """
        Returns a list of unlocked Task objects that are waiting to be
        processed, highest priority and oldest first, optionally limited to
        the given number of results.
        """
        db_session = _db_session or self._db.Session()
        try:
            q = db_session.query(Task).\
                filter(Task.status == Task.STATUS_PENDING).\
                filter(Task.lock_id == None).\
                order_by(Task.priority, Task.id)
            if limit > 0:
                q = q.limit(limit)
            return q.all()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def lock_task(self, task, lock_id):
        """
        Atomically locks and sets as active the given unlocked task.
        Returns True and modifies the provided task on success, returns False
        if the task is already locked or cannot be locked for some other reason.
        """
        db_session = self._db.Session()
        try:
            task_table = Task.__table__
            up = task_table.update().\
                where(Task.id == task.id).\
                where(Task.status == Task.STATUS_PENDING).\
                where(Task.lock_id == None).\
                values(
                    status=Task.STATUS_ACTIVE,
                    lock_id=lock_id
                )
            res = db_session.execute(up)
            db_session.commit()

            if res.rowcount == 0:
                return False

            task.status = Task.STATUS_ACTIVE
            task.lock_id = lock_id
            return True
        finally:
            db_session.close()

    @db_operation
    def complete_task(self, task, _db_session=None, _commit=True):
        """
        Marks a task as complete, unlocks it, and sets the keep_until date.
        """
        db_session = _db_session or self._db.Session()
        try:
            task = db_session.merge(task)

            task.status = Task.STATUS_COMPLETE
            task.lock_id = None
            if task.keep_for > 0:
                task.keep_until = (
                    datetime.datetime.utcnow() +
                    datetime.timedelta(seconds=task.keep_for)
                )
            if _commit:
                db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def delete_completed_tasks(self, _db_session=None, _commit=True):
        """
        Clears completed tasks that have passed their keep_until date.
        """
        db_session = _db_session or self._db.Session()
        try:
            dt_now = datetime.datetime.utcnow()
            db_session.query(Task).\
                filter(Task.status == Task.STATUS_COMPLETE).\
                filter(or_(Task.keep_until == None, Task.keep_until < dt_now)).\
                delete()
            if _commit:
                db_session.commit()
        finally:
            if not _db_session:
                db_session.close()

    @db_operation
    def reorder_portfolio(self, folio_image, index):
        """
        Atomically sets a folio_image object to be at a new zero-based index,
        updating the position (order_num field) on all the other images in the
        portfolio. If the value of index is below 0 or more than the length of
        the image list, it will be adjusted to the nearest valid value.
        Returns the updated folio_image object with the new (possibly corrected)
        'order_num' attribute.
        """
        db_session = self._db.Session()
        commited = False
        try:
            db_folio_image = self.get_object(FolioImage, folio_image.id, _db_session=db_session)
            # Get ordered image list
            db_image_list = db_folio_image.portfolio.images
            # Limit index value to 0 --> list length
            insert_index = max(min(index, len(db_image_list)), 0)
            # Make a copy of the image list minus the folio_image that we'll re-insert
            image_list = [
                (fimg.id, fimg.order_num) for fimg in db_image_list
                if fimg.id != db_folio_image.id
            ]
            # Generate a list of new order numbers for the images
            change_list = []
            order_num_offset = 0
            for idx, img_tuple in enumerate(image_list):
                if idx == insert_index:
                    order_num_offset = 1  # Leave a hole to re-insert the folio_image
                new_order_num = idx + order_num_offset
                if img_tuple[1] != new_order_num:
                    change_list.append({'_id': img_tuple[0], 'order_num': new_order_num})
            # Finally apply the new index to our folio_image
            # If it's moving to the end of the list then insert_index is now 1
            # too high and we need to reduce it to be len(image_list)
            insert_index = min(insert_index, len(image_list))
            if db_folio_image.order_num != insert_index:
                change_list.append({'_id': db_folio_image.id, 'order_num': insert_index})
            # Then use bulk update
            if change_list:
                self.bulk_update(
                    'folioimages',
                    'id',
                    '_id',
                    change_list,
                    _db_session=db_session,
                    _commit=True
                )
            commited = True
            db_session.refresh(db_folio_image)
            return db_folio_image
        finally:
            try:
                if not commited:
                    db_session.rollback()
            finally:
                db_session.close()

    @db_operation
    def increment_property(self, key, _db_session=None, _commit=True):
        """
        Increments a system property, which must support casting to a number,
        and returns the new value (as text). Returns None if there was no
        property matching the given key.
        """
        db_session = _db_session or self._db.Session()
        try:
            res = db_session.execute(
                'UPDATE properties SET value=CAST((CAST(value AS INT) + 1) as text) ' +
                'WHERE key=:key RETURNING value', {'key': key}
            )
            rval = res.first()
            res.close()
            if _commit:
                db_session.commit()
            return rval[0] if rval is not None else None
        finally:
            if not _db_session:
                db_session.close()

    def set_image_src(self, image, src):
        """
        Helper function to set the src property on an image. This performs a
        normalization of src, and clears any cached items that were based on
        the old value of src.

        This function does not save the changes to image. The caller should
        also first update the folder property on image if the new value for
        src refers to a different folder.

        Raises a DBDataError if the path component of the new src property
        does not match the image's folder property.
        """
        # Data integrity check - ensure new src matches folder
        folder_path = filepath_parent(src)
        if self._normalize_folder_path(folder_path) != image.folder.path:
            raise errors.DBDataError(
                'New image src \'%s\' does not match its folder path \'%s\'. ' +
                'Update the folder property first if moving to a new folder.'
                % (src, image.folder.path)
            )
        # Remove the cached image ID
        cache_key = self._get_id_cache_key(image.src)
        self._cache.raw_delete(cache_key)
        # Set the new src
        src = self._normalize_image_path(src)
        image.src = src

    @db_operation
    def set_folder_path(self, folder, new_path, history_user=None,
                        history_info=None, _db_session=None, _commit=True):
        """
        Helper function to change the path of a folder in the database - to
        move or rename it. Also updated are the paths of all its sub-folders,
        and the paths of all images within.
        If the new path infers a different parent folder, the parent folder
        property is also updated (and the parent folder record created,
        if necessary).

        An image history user and/or description can optionally be supplied,
        in which case image history will be added to all affected images.

        This method does not check the validity of the supplied folder path.
        The caller must also ensure that any existing (deleted) folder or image
        records containing the new folder path are first purged in order to
        prevent duplicate path errors from occurring.

        Raises a DBDataError if the src or path property of an image or folder
        is not already correct for its containing folder.
        """
        db_session = _db_session or self._db.Session()
        try:
            folder = db_session.merge(folder)

            # Get/create the new parent folder
            new_parent_path = filepath_parent(new_path)
            if new_parent_path is None:
                raise ValueError('Cannot change the path of the root folder')
            # Note: on create, this commits!
            db_new_parent = self.get_or_create_folder(
                new_parent_path,
                on_create=None,
                _db_session=db_session
            )
            if db_new_parent is None:
                raise errors.DBError(
                    'Failed to read folder for path: ' + new_parent_path
                )

            # Get old and new content paths
            folder_match_path = add_sep(self._normalize_folder_path(folder.path))
            folder_replace_path = add_sep(self._normalize_folder_path(new_path))
            image_match_path = add_sep(self._normalize_image_path(folder.path))
            image_replace_path = add_sep(self._normalize_image_path(new_path))

            # Update paths of all content for the folder and all its descendants
            folder_tree = self._flatten_folder_tree(folder)
            for f in folder_tree:
                # Update folder path first, flush changes, then update image paths.
                # set_image_src() requires this order for its path integrity check.

                update_folder_name = (f.name == f.path)
                if f == folder:
                    # Base folder to move/rename - replace the parent and path
                    f.parent = db_new_parent
                    f.path = self._normalize_folder_path(new_path)
                    if update_folder_name:
                        f.name = f.path
                else:
                    # Sub-folder - just update the path
                    if f.path.startswith(folder_match_path):
                        f.path = folder_replace_path + f.path[len(folder_match_path):]
                        if update_folder_name:
                            f.name = f.path
                    else:
                        raise errors.DBDataError(
                            'Cannot move folder ID %d with path \'%s\'. ' +
                            'It should have a path beginning \'%s\'.'
                            % (f.id, f.path, folder_match_path)
                        )
                db_session.flush()

                images = self.list_images(folder=f, _db_session=db_session)
                for image in images:
                    if image.src.startswith(image_match_path):
                        # Update image path (this takes other actions too)
                        new_src = image_replace_path + image.src[len(image_match_path):]
                        self.set_image_src(image, new_src)
                        # Add history
                        if (history_user or history_info):
                            self.add_image_history(
                                image,
                                history_user,
                                ImageHistory.ACTION_MOVED,
                                history_info,
                                _db_session=db_session,
                                _commit=False
                            )
                    else:
                        raise errors.DBDataError(
                            'Cannot move image ID %d with src \'%s\'. ' +
                            'It should have a src beginning \'%s\'.'
                            % (image.id, image.src, image_match_path)
                        )
                db_session.flush()

            if _commit:
                db_session.commit()
        except SQLAlchemyError:
            if _commit:
                db_session.rollback()
            raise
        finally:
            if not _db_session:
                db_session.close()

    def attr_is_loaded(self, obj, attr_name):
        """
        Utility to return whether an attribute of a database model object is
        loaded. Use this to determine whether a lazy-loaded relationship has
        been loaded (or would be when accessed).
        """
        return attr_name in obj.__dict__

    def _get_id_cache_key(self, src):
        """
        Returns the cache key to use for storing/retrieving a cached image ID.
        """
        if len(src) < 220:
            # src is unique so use if possible
            hsh = src
        else:
            # Use a good hash (+ checksum to hopefully prevent collisions)
            hsh = str(hash(src)) + '_' + str(zlib.crc32(src))
        return 'DB:IMG_ID:' + hsh

    def _normalize_folder_path(self, folder_path):
        """
        Converts a folder path into a standard format for storage or retrieval
        and returns the modified path.
        """
        # Store folder paths with a leading slash but without a trailing slash
        return add_sep(filepath_normalize(folder_path), True)

    def _normalize_image_path(self, src):
        """
        Converts an image path into a standard format for storage or retrieval
        and returns the modified path.
        """
        # Store image paths without a leading slash
        return strip_sep(filepath_normalize(src), True)

    def _flatten_folder_tree(self, folder, _fset=None):
        """
        Returns an unordered set of the supplied folder and all its descendant
        child folders. The folder should be attached to a database session so
        that lazy loading of the children attribute can take place.
        """
        if _fset is None:
            _fset = set()
        _fset.add(folder)
        for child in folder.children:
            self._flatten_folder_tree(child, _fset=_fset)
        return _fset

    @staticmethod
    def _validate_user(mapper, connection, target):
        """
        Asserts that a user's password field is not empty.
        This can only occur if the user admin API allows it (which is a bug), or
        if the web request.g.user has found its way into the database session
        (which has happened in development, and is also a bug).
        """
        assert target.password, 'User password cannot be empty. ' + \
                                'Maybe a web request user object is being saved?'

    def _is_duplicate_key(self, exception):
        """
        Returns whether an IntegrityError is a duplicate key error.
        """
        return u'duplicate' in unicode(exception)

    def _enable_sql_time_logging(self):
        """
        For testing purposes only, instructs the engine to log the execution
        time of every SQL statement.
        """
        @event.listens_for(Engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement,
                                  parameters, context, executemany):
            context._query_start_time = time.time()

        @event.listens_for(Engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement,
                                 parameters, context, executemany):
            total = time.time() - context._query_start_time
            self._logger.debug("SQL query time: %.3f msec" % (total * 1000))

    def _add_sql_listener(self, listener_fn):
        """
        For testing purposes only, registers a callback to be notified
        when SQL is executed. The listener should be defined as function(sql).
        """
        @event.listens_for(Engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement,
                                  parameters, context, executemany):
            listener_fn(statement)

    def _drop_db(self):
        """
        For testing purposes only, drops the database schema.
        """
        Base.metadata.drop_all(self._db)
        self._logger.info('Management database dropped')

    def _init_db(self):
        """
        Checks the database schema,
        and creates the schema and default data if it does not yet exist.
        """
        # Add database event listeners
        event.listen(User, 'before_insert', DataManager._validate_user)
        event.listen(User, 'before_update', DataManager._validate_user)

        # The next section must only be attempted by one process at a time on server startup
        if self._cache:
            self._cache.get_global_lock()
            try:
                create_default_users = False
                create_default_groups = False
                create_default_folders = False
                create_default_templates = False
                create_properties = False

                # Create the database schema
                if not Group.__table__.exists(self._db):
                    Group.__table__.create(self._db)
                    create_default_groups = True

                if not User.__table__.exists(self._db):
                    User.__table__.create(self._db)
                    create_default_users = True

                if not UserGroup.__table__.exists(self._db):
                    UserGroup.__table__.create(self._db)

                if not SystemPermissions.__table__.exists(self._db):
                    SystemPermissions.__table__.create(self._db)

                if not Folder.__table__.exists(self._db):
                    Folder.__table__.create(self._db)
                    create_default_folders = True

                if not FolderPermission.__table__.exists(self._db):
                    FolderPermission.__table__.create(self._db)

                if not Image.__table__.exists(self._db):
                    Image.__table__.create(self._db)

                if not ImageTemplate.__table__.exists(self._db):
                    ImageTemplate.__table__.create(self._db)
                    create_default_templates = True

                if not ImageHistory.__table__.exists(self._db):
                    ImageHistory.__table__.create(self._db)

                if not ImageStats.__table__.exists(self._db):
                    ImageStats.__table__.create(self._db)

                if not SystemStats.__table__.exists(self._db):
                    SystemStats.__table__.create(self._db)

                if not Task.__table__.exists(self._db):
                    Task.__table__.create(self._db)

                if not Property.__table__.exists(self._db):
                    Property.__table__.create(self._db)
                    create_properties = True

                if not Folio.__table__.exists(self._db):
                    Folio.__table__.create(self._db)

                if not FolioImage.__table__.exists(self._db):
                    FolioImage.__table__.create(self._db)

                if not FolioPermission.__table__.exists(self._db):
                    FolioPermission.__table__.create(self._db)

                if not FolioHistory.__table__.exists(self._db):
                    FolioHistory.__table__.create(self._db)

                if not FolioExport.__table__.exists(self._db):
                    FolioExport.__table__.create(self._db)

                # Create system data (needs all tables in place first)
                if create_default_groups:
                    # Create fixed system groups
                    self.create_group(Group(
                        'Public',
                        'Provides the access rights for unknown users',
                        Group.GROUP_TYPE_SYSTEM
                    ))
                    self._logger.info('Created Public group')
                    self.create_group(Group(
                        'Normal users',
                        'Provides the default access rights for known users',
                        Group.GROUP_TYPE_SYSTEM
                    ))
                    self._logger.info('Created Normal users group')
                    admin_group = Group(
                        'Administrators',
                        'Provides full administration access',
                        Group.GROUP_TYPE_SYSTEM
                    )
                    admin_group.permissions = SystemPermissions(
                        admin_group,
                        True, True, True, True, True, True, True
                    )
                    self.create_group(admin_group)
                    self._logger.info('Created Administrators group')

                if create_default_users:
                    # Create admin user
                    default_pwd = generate_password()
                    default_user = User(
                        'Administrator', '', '', 'admin', default_pwd,
                        User.AUTH_TYPE_PASSWORD, False, User.STATUS_ACTIVE
                    )
                    # Make admin an administrator
                    default_user.groups.append(self.get_group(group_id=3))
                    self.create_user(default_user)
                    self._logger.info('Created default admin user with password ' + default_pwd)

                if create_default_folders:
                    root_folder = Folder('', '', None, Folder.STATUS_ACTIVE)
                    self.create_folder(root_folder)
                    self._logger.info('Created root folder')
                    # Create default folder permissions for public
                    self.save_object(FolderPermission(
                        root_folder,
                        self.get_group(Group.ID_PUBLIC),
                        FolderPermission.ACCESS_VIEW
                    ))
                    # Create default folder permissions for normal users
                    self.save_object(FolderPermission(
                        root_folder,
                        self.get_group(Group.ID_EVERYONE),
                        FolderPermission.ACCESS_VIEW
                    ))
                    self._logger.info('Created default folder permissions')

                if create_default_templates:
                    # Create system default image template
                    self.save_object(ImageTemplate(
                        'Default',
                        'Defines the system defaults for image generation if the '
                        'image does not specify a template or specific parameter value', {
                            'quality': {'value': 80},
                            'strip': {'value': True},
                            'colorspace': {'value': 'rgb'},
                            'record_stats': {'value': True},
                            'expiry_secs': {'value': 60 * 60 * 24 * 7}
                        }
                    ))
                    # Create sample SmallJpeg template
                    self.save_object(ImageTemplate(
                        'SmallJpeg',
                        'Defines a 200x200 JPG image that would be suitable for '
                        'use as a thumbnail image on a web site.', {
                            'format': {'value': 'jpg'},
                            'quality': {'value': 80},
                            'width': {'value': 200},
                            'height': {'value': 200},
                            'strip': {'value': True},
                            'colorspace': {'value': 'rgb'},
                            'record_stats': {'value': True},
                            'expiry_secs': {'value': 60 * 60 * 24 * 7}
                        }
                    ))
                    # Create sample Precache template
                    self.save_object(ImageTemplate(
                        'Precache',
                        'Resizes an image to 800x600 (or the closest match to it) '
                        'while leaving other attributes unchanged. Useful alongside '
                        'the pre-cache utility to warm the cache with smaller versions '
                        'of images so that e.g. thumbnails are faster to produce from then '
                        'on.', {
                            'width': {'value': 800},
                            'height': {'value': 600},
                            'size_fit': {'value': True},
                            'record_stats': {'value': False}
                        }
                    ))
                    self.save_object(Property(Property.IMAGE_TEMPLATES_VERSION, '1'))
                    self._logger.info('Created default image templates')

                if create_properties:
                    self.save_object(Property(Property.FOLDER_PERMISSION_VERSION, '1'))
                    self.save_object(Property(Property.FOLIO_PERMISSION_VERSION, '1'))
                    self.save_object(Property(Property.IMAGE_TEMPLATES_VERSION, '1'))
                    self.save_object(Property(Property.DEFAULT_TEMPLATE, 'default'))

            finally:
                self._cache.free_global_lock()

        # Show a startup message on success
        self._logger.info('Management + stats database opened')

    def _upgrade_db(self):
        """
        Applies any database migrations required (other than create actions
        that _init_db already does) to bring the database schema up to date.
        """
        # Bump this up whenever you add a new migration
        FINAL_MIGRATION_VERSION = 1

        db_session = self._db.Session()
        done = False
        try:
            # Get the database starting internal version
            db_ver = db_session.query(Property).get(Property.DATABASE_MIGRATION_VERSION)
            ver = int(db_ver.value) if db_ver else 0

            if ver < FINAL_MIGRATION_VERSION:
                # Run migrations
                self._migrations(ver, db_session)
                # Set the database new internal version
                db_session.merge(Property(
                    Property.DATABASE_MIGRATION_VERSION,
                    str(FINAL_MIGRATION_VERSION)
                ))
            done = True
        except Exception as e:
            self._logger.error('Error upgrading database: ' + str(e))
        finally:
            if done:
                db_session.commit()
            else:
                db_session.rollback()
            db_session.close()

    def _migrations(self, current_number, db_session):
        """
        Back end to _upgrade_db, performs the actual database migrations.
        """
        if current_number < 1:
            # v2.7 migration number 1 adds portfolios
            self._logger.info('Applying database migration number 1')
            db_session.merge(Property(Property.FOLIO_PERMISSION_VERSION, '1'))
