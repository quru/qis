#
# Quru Image Server
#
# Document:      cache_manager.py
# Date started:  27 Apr 2011
# By:            Matt Fozard
# Purpose:       Image caching engine (SQLAlchemy version)
# Requires:      python-memcached, SQLAlchemy
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
# 08Aug2011  Matt  Moved CacheEntry class into new models.py module, renamed from
#                  cache_manager_alchemy.py to plain old cache_manager.py
# 19Aug2011  Matt  Pass in settings to remove any dependency on imageserver package
# 06Oct2011  Matt  Support lists of ORed parameter values in cache search
# 17Jan2012  Matt  Added support for Couchbase Membase Server (different stats)
# 21Feb2012  Matt  Prevented unnecessary 'select count' when starting up, sped up
#                  count, add random part to get_global_lock to reduce lock
#                  contention when multiple processes are starting up
# 14Mar2013  Matt  Revise delete() to remove an SQL call, perform less work when
#                  there is cache miss in get(). Remove an SQL call from put()
#                  when adding a new key (adding a key is 50% faster, but
#                  replacing a key is now slower).
# 18Mar2013  Matt  Prevent UnicodeEncodeError with unicode keys
# 31May2013  Matt  Disable slow key checking in python-memcached
#                  (requires python-memcached v1.51)
# 11May2015  Matt  Changed to use the pylibmc client, hopefully fixes very occasional
#                  corruption seen with python-memcached, and is about 30% faster
#

# Old Membase notes:
#
# * If Membase is being used exclusively, override memcache.SERVER_MAX_VALUE_LENGTH
#   to reflect the 20MB bucket limit (memcache default is a meager 1MB).
# * Check curr_items, mem_used, ep_max_data_size stats on Membase do the right thing.
#   A bit confusing as to whether they give memory, disk or memory+disk stats.
#   https://github.com/membase/ep-engine/blob/master/docs/stats.org
# * Redis might be better, using hash or list of cached images per src/db id.

# pylibmc notes:
#
# * On OS X, compile libmemcached from source, manually fix the configure script,
#   fix memflush.cc files (if false --> if NULL) then pip install pylibmc
# * On RHEL 6, install the IUS repo, sudo yum install libmemcached10-devel then
#   pip install pylibmc. See http://stackoverflow.com/a/30170280/1671320
# * On other, sudo apt-get install libmemcached-dev then pip install pylibmc
# * For pylibmc on Fedora (build container only!) require
#   python-pip gcc python-devel libmemcached-devel zlib-devel
#   At runtime only require libmemcached and the lib folder
#

import cPickle
import random
import time
import threading

import pylibmc
import sqlalchemy
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import mapper, sessionmaker
from sqlalchemy.schema import MetaData

import errors
from models import CacheEntry
from util import unicode_to_ascii


MAX_OBJECT_SLOTS = 32
SLOT_HEADER_SIZE = 4
INTEGRITY_HEADER = '$IC'

SERVER_MAX_KEY_LENGTH = 250
SERVER_MAX_VALUE_LENGTH = 1024*1024
# https://bugs.launchpad.net/python-memcached/+bug/745633
MAX_SLOT_SIZE = (
    SERVER_MAX_VALUE_LENGTH - (
        SERVER_MAX_KEY_LENGTH + 80 + SLOT_HEADER_SIZE
    )
)

GLOBAL_LOCK_KEY = 'CACHEMANAGER_UNIVERSAL_LOCK'
GLOBAL_LOCK_TIMEOUT = 60


class CacheManager(object):
    """
    Provides object storage in a back-end Memcached key/value store.

    The get/put function family make use of a cache control database to allow
    querying of the cache and storage of objects greater than MAX_SLOT_SIZE
    in length.

    The raw_get/raw_put function family provide direct access to Memcached,
    bypassing the cache control database.
    """
    def __init__(self, logger, server_list, db_uri, db_pool_size):
        try:
            self._server_list = server_list
            self._db_uri = db_uri
            self._db_pool_size = db_pool_size
            self._capacity = 0L

            self._db = None
            self._db_metadata = None

            self._logger = logger
            self._locals = threading.local()
            self._init_cache()
            self._open_db()
            self._init_db()
        except OperationalError as e:
            raise errors.StartupError(
                'Cannot start cache manager. Database connection error: ' + unicode(e)
            )
        except BaseException as e:
            raise errors.StartupError(
                'Cannot start cache manager: ' + type(e).__name__ + ' ' + unicode(e)
            )

    def client(self):
        """
        Returns a cache client local to the current thread.
        Added for pylibmc, where the client is not thread safe.
        """
        c = getattr(self._locals, 'client', None)
        if c is None:
            self._locals.client = self._open_cache()
            c = self._locals.client
        return c

    def _reset_pool(self):
        """
        Drops and resets all cache server connections.
        """
        self.client().disconnect_all()
        self._db.pool.dispose()
        self._db.pool.recreate()

    def close(self):
        """
        Closes connections and releases resources held by this object.
        """
        self._capacity = 0L
        self.client().disconnect_all()
        self._db.dispose()

    def connected(self):
        """
        Returns whether the cache manager is currently connected to the
        underlying cache engine. This is determined simply by reading a dummy
        key from the cache and checking for a connection error.
        """
        try:
            self.client().get('_ping_test_key')
            connected = True
        except pylibmc.Error:
            connected = False
        if not connected:
            self._capacity = 0L
        return connected

    def search(self, order=None, max_rows=1000, **searchfields):
        """
        Searches for managed cache entries using the searchfieldN values,
        as provided through the search_info parameter on the put() function.

        The function supports django model-style keyword parameters for
        searchfield1 to searchfield5.
        E.g.
            searchfield1__eq=1000  would require searchfield1 to equal 1000
            searchfield2__lt=1000  would require searchfield2 to be less than 1000
            searchfield3__gte=1000 would require searchfield3 to be greater than
                                   or equal to 1000
            searchfield5__eq=None  would require searchfield5 to be null

        At least 1 searchfield must be provided, and the terms are ANDed together.
        It is recommended that searchfield1 always be provided and be as unique as
        possible, since the database searching index is defined as:
        (searchfield1, searchfield2).

        In addition, if a parameter value is a list, the list values will be ORed
        together for that component of the search. This only has meaning for eq.
        E.g.
            searchfield1__eq=[1000, 2000] would require searchfield1 to equal
            either 1000 or 2000

        The return value is a list of dictionaries (with maximum length max_rows)
        containing match information of the form:
        { 'key': k, 'valuesize': bytes, 'searchfield1': sfv1, ...
          'searchfield5': sfv5, 'metadata': user_obj }
        i.e. the cache key plus the search_info that was originally supplied to put().

        The optional order parameter can be: "+size" to order results by object
        size ascending, or "-size" to order by object size descending.

        Note that the returned cache keys are not validated for existence in the
        cache - they may have timed out or been purged. To find out, you must call
        get() to try and load the object.
        """
        sql_operators = {'eq': '=', 'lt': '<', 'gt': '>', 'lte': '<=', 'gte': '>='}
        sql_field_ops = searchfields.keys()
        sql_field_ops.sort()
        # Create a blank query to build upon
        db_session = self._db.Session()
        try:
            db_query = db_session.query(CacheEntry)
            sql_params = {}
            # Apply criteria to query
            for sql_field_op in sql_field_ops:
                sql_field, sql_opcode = tuple(sql_field_op.split('__'))
                sql_value = searchfields[sql_field_op]
                # Check parameter type
                if sql_value is None:
                    # Add x IS NULL
                    db_query = db_query.filter(sql_field + ' is null')
                elif type(sql_value) == list:
                    # OR the list values
                    sql_operator = sql_operators[sql_opcode]
                    or_query = '('
                    for i in range(len(sql_value)):
                        if i > 0:
                            or_query += ' OR '
                        if sql_value[i] is None:
                            or_query += sql_field + ' is null'
                        else:
                            or_query += sql_field + sql_operator + ':' + sql_field + str(i)
                            sql_params[sql_field + str(i)] = sql_value[i]
                    or_query += ')'
                    db_query = db_query.filter(or_query)
                else:
                    # Add a single expression
                    sql_operator = sql_operators[sql_opcode]
                    db_query = db_query.filter(sql_field + sql_operator + ':' + sql_field)
                    sql_params[sql_field] = sql_value
            db_query = db_query.params(**sql_params)
            # Apply order and limits
            if order == '+size':
                db_query = db_query.order_by(CacheEntry.valuesize)
            if order == '-size':
                db_query = db_query.order_by(desc(CacheEntry.valuesize))
            db_query = db_query.limit(max_rows)
            # Run query, convert returned objects to dictionary format
            results = []
            for entry in db_query.all():
                results.append({
                    'key': entry.key,
                    'valuesize': entry.valuesize,
                    'searchfield1': entry.searchfield1,
                    'searchfield2': entry.searchfield2,
                    'searchfield3': entry.searchfield3,
                    'searchfield4': entry.searchfield4,
                    'searchfield5': entry.searchfield5,
                    'metadata': None if entry.metadata is None else cPickle.loads(entry.metadata)
                })
        finally:
            db_session.close()
        return results

    def get(self, key):
        """
        Retrieves a managed object from cache, transparently handling chunked
        object storage as necessary. None is returned if the requested object
        no longer exists in cache.
        """
        # Get first chunk from cache, and see if there are any others.
        # If there are we'll need to hit the cache a second time, but this method
        # avoids the need for any database lookups.
        chunk = self.raw_get(key+'_1')
        if chunk is not None:
            num_slots = self._get_slot_header_value(chunk[0:SLOT_HEADER_SIZE])
            if num_slots <= 0:
                # Looks like an unmanaged object (no header).
                return chunk
            elif num_slots == 1:
                # This is the one and only chunk. Return it sans header.
                return chunk[SLOT_HEADER_SIZE:]
            else:
                # Read the other chunks. Some or all may have been expired/purged.
                chunk_keys = [key+'_'+str(num) for num in range(2, num_slots + 1)]
                # Pre-process chunk_keys here so that the returned dictionary keys will match up
                chunk_keys = self._prepare_cache_keys(chunk_keys)
                chunks = self.raw_getn(chunk_keys)
                if len(chunks) == len(chunk_keys):
                    # Return correctly ordered, re-constituted object
                    chunk1 = chunk[SLOT_HEADER_SIZE:]
                    return chunk1 + ''.join(chunks[k] for k in chunk_keys)
        # If we get here it's a plain cache miss or one or more chunks are missing.
        # For the former, just ensure the control record (if any) is deleted too.
        # For the latter, also delete any orphaned chunks that may still exist.
        self.delete(key, _db_only=(chunk is None))
        return None

    def put(self, key, obj, expiry_secs=0, search_info=None):
        """
        Adds or replaces a managed object in cache, with an optional expiry time
        in seconds. The object can be of any size; if the object is too large to
        store in one cache slot, it will be transparently stored as multiple chunks.

        search_info, if provided, should be a dictionary of the form:
        { 'searchfield1': 1000, 'searchfield2': 2000, 'searchfield3': 3000,
          'searchfield4': None, 'searchfield5': None, 'metadata': some_object }
        and will be stored in the cache control database, allowing later
        searching of the cache via the search() function.
        All dictionary keys are mandatory but the values may be set to None.

        Returns a boolean indicating success.
        """
        # Split object into chunks
        chunks = {}
        num_slots = self._slots_for_size(len(obj))
        if num_slots > MAX_OBJECT_SLOTS:
            return False
        for slot in range(1, num_slots + 1):
            from_offset = (slot - 1) * MAX_SLOT_SIZE
            to_offset = len(obj) if slot == num_slots else (slot * MAX_SLOT_SIZE)
            slot_header = self._get_slot_header(num_slots) if slot == 1 else ''
            chunks[key+'_'+str(slot)] = slot_header + obj[from_offset:to_offset]
        # Add chunks to cache
        if self.raw_putn(chunks, expiry_secs):
            # Chunks added. Prepare control db entry.
            entry = CacheEntry(key, len(obj))
            if search_info is not None:
                entry.searchfield1 = search_info['searchfield1']
                entry.searchfield2 = search_info['searchfield2']
                entry.searchfield3 = search_info['searchfield3']
                entry.searchfield4 = search_info['searchfield4']
                entry.searchfield5 = search_info['searchfield5']
                if search_info['metadata'] is not None:
                    entry.metadata = cPickle.dumps(
                        search_info['metadata'],
                        protocol=cPickle.HIGHEST_PROTOCOL
                    )
            # Add/update entry in the control db
            db_session = self._db.Session()
            db_committed = False
            try:
                db_session.merge(entry)
                db_session.commit()
                db_committed = True
            except IntegrityError:
                # Rarely, 2 threads merging (adding) the same key causes a duplicate key error
                db_session.rollback()
                db_session.query(CacheEntry).filter(CacheEntry.key==entry.key).update({
                    'valuesize': entry.valuesize,
                    'searchfield1': entry.searchfield1,
                    'searchfield2': entry.searchfield2,
                    'searchfield3': entry.searchfield3,
                    'searchfield4': entry.searchfield4,
                    'searchfield5': entry.searchfield5,
                    'metadata': entry.metadata
                }, synchronize_session=False)
                db_session.commit()
                db_committed = True
            finally:
                try:
                    if not db_committed:
                        db_session.rollback()
                finally:
                    db_session.close()
            return True
        else:
            # Delete everything for key (if there was a previous object for this
            # key, we might now have a mix of chunk versions in the cache).
            self.delete(key)
            return False

    def delete(self, key, _db_only=False):
        """
        Removes a managed object from cache.
        """
        db_session = self._db.Session()
        db_commit = False
        try:
            if not _db_only:
                # Delete all possible chunks
                chunk_keys = [key+'_'+str(num) for num in range(1, MAX_OBJECT_SLOTS + 1)]
                self.raw_deleten(chunk_keys)
            # Delete from the control db
            db_session.query(CacheEntry).filter(CacheEntry.key==key).delete()
            db_commit = True
        finally:
            try:
                if db_commit:
                    db_session.commit()
                else:
                    db_session.rollback()
            finally:
                db_session.close()
        return True

    def count(self):
        """
        Returns the total number of objects currently in the cache,
        or -1 if the cache is unavailable.
        This count will be greater than the number of calls to put() if
        some objects have been stored in chunks due to their size.
        """
        try:
            cache_items = 0L
            for (_, stats_dict) in self.client().get_stats():
                cache_items += long(stats_dict['curr_items'])
            return cache_items
        except pylibmc.Error:
            return -1

    def size(self):
        """
        Returns the current size in bytes of all objects in the cache,
        or -1 if the cache is unavailable.
        """
        try:
            cache_size = 0L
            for (_, stats_dict) in self.client().get_stats():
                if 'mem_used' in stats_dict:
                    cache_size += long(stats_dict['mem_used'])  # Membase
                else:
                    cache_size += long(stats_dict['bytes'])     # Memcached
            return cache_size
        except pylibmc.Error:
            return -1

    def size_percent(self):
        """
        Returns the current percentage use of the cache as an integer,
        or -1 if the cache is unavailable.
        """
        cache_size = self.size()
        cache_limit = self.capacity()
        if cache_size != -1 and cache_limit > 0:
            return int((float(cache_size) / float(cache_limit)) * 100.0)
        elif cache_limit == 0:
            return 0
        else:
            return -1

    def capacity(self):
        """
        Returns the total capacity of the cache in bytes,
        or -1 if the cache is unavailable. Retains the last known value
        internally so that repeated calls incur little cost.
        """
        try:
            if self._capacity > 0L:
                return self._capacity

            self._capacity = 0L
            for (_, stats_dict) in self.client().get_stats():
                if 'ep_max_data_size' in stats_dict:
                    self._capacity += long(stats_dict['ep_max_data_size'])  # Membase
                else:
                    self._capacity += long(stats_dict['limit_maxbytes'])    # Memcached
            return self._capacity

        except pylibmc.Error:
            self._capacity = 0L
            return -1

    def clear(self):
        """
        Deletes all items from the cache.
        """
        db_session = self._db.Session()
        try:
            db_session.query(CacheEntry).delete()
            db_session.commit()
        finally:
            db_session.close()
        self.client().flush_all()
        return True

    def raw_get(self, key, integrity_check=False):
        """
        Returns the binary object with the given key from cache,
        or None if the key does not exist in the cache.
        The integrity_check flag must match that given at raw_put().
        This method bypasses the cache control database.
        """
        try:
            prepared_key = self._prepare_cache_key(key)
            obj = self.client().get(prepared_key)
        except pylibmc.Error as e:
            obj = None

        if integrity_check and obj is not None:
            expect_header = self._get_integrity_header(prepared_key)
            try:
                if not obj.startswith(expect_header):
                    if not obj.startswith(INTEGRITY_HEADER):
                        self._logger.error(
                            'Cache value integrity: No value header for key: ' + key
                        )
                    else:
                        header_end = max(min(obj.find('$', len(INTEGRITY_HEADER) + 1), 255), 5)
                        self._logger.error(
                            'Cache value integrity: Incorrect value header: ' +
                            obj[:header_end + 1] + ' for key: ' + key
                        )
                    self.raw_delete(key)  # Wipe the value, caller can reset it
                    return None
            except:
                self._logger.error(
                    'Cache value integrity: Expected a string value for key: ' + key
                )
                self.raw_delete(key)  # Wipe the value, caller can reset it
                return None

            # Header matches, now unpickle the value
            obj = cPickle.loads(obj[len(expect_header):])
        return obj

    def raw_getn(self, keys):
        """
        As for raw_get() but takes a list of keys, returning an unordered dictionary
        of the keys and values that were found in the cache. Keys that were not
        found are not returned.

        NOTE! Due to limitations of the underlying cache storage, keys will be
        returned as ascii strings, with spaces converted to underscores. This
        is handled transparently by all other functions, where keys are provided
        but not returned.

        This method bypasses the cache control database.
        """
        try:
            return self.client().get_multi(self._prepare_cache_keys(keys))
        except pylibmc.Error as e:
            return {}

    def raw_atomic_add(self, key, obj, expiry_secs=0):
        """
        Adds an object to cache, only if that object does not already exist.
        The object size cannot be greater than MAX_SLOT_SIZE.
        Returns a boolean indicating whether the object was added.
        This method bypasses the cache control database.
        """
        try:
            return self.client().add(self._prepare_cache_key(key), obj, expiry_secs)
        except pylibmc.Error:
            return False

    def raw_put(self, key, obj, expiry_secs=0, integrity_check=False):
        """
        Adds or replaces an object in cache, with an optional expiry time in
        seconds, and an optional self-integrity check that stores the key
        alongside the value, requiring the same flag at raw_get().
        The pickled object size cannot be greater than MAX_SLOT_SIZE,
        or (MAX_SLOT_SIZE - len(key) - 5) if the integrity check is enabled.
        Returns a boolean indicating success.
        This method bypasses the cache control database.
        """
        prepared_key = self._prepare_cache_key(key)
        prepared_obj = obj
        if integrity_check:
            # We have to get obj as a string to prepend the integrity header
            prepared_obj = (
                self._get_integrity_header(prepared_key) +
                cPickle.dumps(obj, protocol=cPickle.HIGHEST_PROTOCOL)
            )
        try:
            return self.client().set(prepared_key, prepared_obj, expiry_secs)
        except pylibmc.Error as e:
            return False

    def raw_putn(self, mapping, expiry_secs=0):
        """
        As for raw_put() but taking a dictionary of the format
        { 'key1':'value1', 'key2':'value2' }
        This method bypasses the cache control database.
        """
        mapping = dict((self._prepare_cache_key(k), v) for (k, v) in mapping.items())
        try:
            failed_keys = self.client().set_multi(mapping, expiry_secs)
            return (len(failed_keys) == 0)
        except pylibmc.Error as e:
            return False

    def raw_delete(self, key):
        """
        Deletes the object with the specified key from the cache.
        This method bypasses the cache control database.
        """
        try:
            self.client().delete(self._prepare_cache_key(key))
            return True
        except pylibmc.Error:
            return False

    def raw_deleten(self, keys):
        """
        As for raw_delete() but takes a list of keys.
        This method bypasses the cache control database.
        """
        try:
            self.client().delete_multi(self._prepare_cache_keys(keys))
            return True
        except pylibmc.Error:
            return False

    def get_global_lock(self):
        """
        Obtains a universal lock across all processes and threads, for
        performing operations that must not occur in parallel.
        Requires the cache engine to be operational (returns without action otherwise).
        This function will block indefinitely in order to obtain the lock.
        """
        loops = 0
        while True:
            lck = self.raw_get(GLOBAL_LOCK_KEY)
            if lck is None:
                if self.raw_atomic_add(GLOBAL_LOCK_KEY, 'lock', GLOBAL_LOCK_TIMEOUT):
                    # Success
                    return
                else:
                    if not self.connected():
                        self._logger.warn(
                            'Cache server appears to be down, unable to create global lock.'
                        )
                        return
            loops += 1
            if loops % 10 == 0:
                self._logger.warn('Waiting to obtain global lock')
            time.sleep(
                (0.1 * min(loops, 10)) +
                (0 if loops < 5 else random.random())
            )

    def free_global_lock(self):
        """
        Frees the universal lock.
        This function does not check ownership of the lock, therefore it must
        only be called by the thread that last returned from _get_global_lock().
        """
        self.raw_delete(GLOBAL_LOCK_KEY)

    def _prepare_cache_key(self, key):
        """
        Ensures a key is valid for memcached by converting to ascii if
        necessary and replacing spaces. Returns the modified key,
        or raises a ValueError if the key is empty or too long.
        """
        try:
            ascii_key = key if isinstance(key, str) else key.encode('ascii')
        except UnicodeEncodeError:
            ascii_key = unicode_to_ascii(key)
        ascii_key = ascii_key.replace(' ', '_')
        if not ascii_key:
            raise ValueError('Cache key is empty')
        if not ascii_key or len(ascii_key) > SERVER_MAX_KEY_LENGTH:
            raise ValueError('Cache key is too long: ' + ascii_key)
        return ascii_key

    def _prepare_cache_keys(self, keys):
        """
        Ensures a list of keys is valid for memcached by converting them to
        ascii if necessary and replacing spaces. Returns the modified list.
        """
        return [self._prepare_cache_key(k) for k in keys]

    def _get_slot_header_value(self, header):
        """
        Returns the number of slots specified by a string slot header, or 0 if
        the supplied string is not a valid slot header.
        """
        if len(header) == SLOT_HEADER_SIZE and header[0] == '$' and header[-1] == '$':
            return int(header[1:-1])
        else:
            return 0

    def _get_slot_header(self, num_slots):
        """
        Returns the string slot header for a given number of slots.
        """
        return "$%02d$" % num_slots

    def _slots_for_size(self, num_bytes):
        """
        Returns the number of cache slots required to store the given number of bytes.
        """
        slots = (num_bytes / MAX_SLOT_SIZE)
        if num_bytes % MAX_SLOT_SIZE > 0:
            slots += 1
        return max(1, slots)

    def _get_integrity_header(self, prepared_key):
        """
        Returns a string header for prepending to a string cache value.
        The header incorporates the cache key, so that the value can be verified
        against the same key upon retrieval.
        """
        return INTEGRITY_HEADER + '$' + prepared_key + '$'

    def _open_cache(self):
        """
        Returns a new client connection to the cache.
        Under pylibmc, this object is NOT thread safe.
        """
        return pylibmc.Client(
            self._server_list,
            behaviors={
                "distribution": "consistent",
                "connect_timeout": 3000,
                "send_timeout": 3000000,
                "receive_timeout": 3000000,
                "dead_timeout": 5,
                "verify_keys": False
            },
            binary=False
        )

    def _init_cache(self):
        """
        Sets the cache options, and creates the cache storage if required.
        """
        cache_count = self.count()
        cache_size = self.size()
        cache_limit = self.capacity()
        if cache_limit != -1:
            self._logger.info(
                'Cache usage currently ' + str(cache_size) + ' out of ' +
                str(cache_limit) + ' bytes (' + str(self.size_percent()) + '%)' +
                ', holding ' + str(cache_count) + ' objects (via pylibmc).'
            )
        else:
            self._logger.warn('Cache server appears to be down (via pylibmc).')

    def _open_db(self):
        """
        Returns a new database engine for the cache control database.
        """
        db_engine = sqlalchemy.create_engine(
            self._db_uri,
            echo=False,
            echo_pool=False,
            poolclass=sqlalchemy.pool.QueuePool,
            pool_size=self._db_pool_size
        )
        db_engine.Session = sessionmaker(
            autocommit=False,
            autoflush=True,
            expire_on_commit=False,
            bind=db_engine
        )
        self._db = db_engine

    def _drop_db(self):
        """
        For testing purposes only, drops the database schema.
        """
        self._db_metadata.drop_all()
        self._logger.info('Cache control database dropped')

    def _init_db(self):
        """
        Creates the database schema, or clears the database if the cache is empty.
        This method cannot be called while the database is in normal use.
        """
        metadata = MetaData(bind=self._db)
        self._db_metadata = metadata

        # Set the ORM mapping
        cache_table = CacheEntry.get_alchemy_mapping(metadata)
        mapper(CacheEntry, cache_table)

        # The next section must only be attempted by one process at a time on server startup
        self.get_global_lock()
        try:
            # Check the control database schema has been created
            if not cache_table.exists():
                self._create_db_schema(cache_table)
                self._logger.info('Cache control database created.')

            # See if the cache is empty
            if self.capacity() > 0:
                # -1 to uncount the global lock
                cache_count = self.count() - 1
                if cache_count <= 0:
                    # See if the control database is empty
                    db_session = self._db.Session()
                    db_count = db_session.query(CacheEntry.key).limit(1).count()
                    db_session.close()
                    if db_count > 0:
                        # Cache is empty, control database is not. Delete and re-create
                        # the database so we're not left with any fragmentation, etc.
                        self._logger.info('Cache is empty. Resetting cache control database.')
                        self._drop_db_schema(cache_table)
                        self._create_db_schema(cache_table)
            else:
                self._logger.warn('Cache is down, skipped cache control database check.')

            self._logger.info('Cache control database opened.')
        finally:
            self.free_global_lock()

    def _create_db_schema(self, cache_table):
        """
        Creates the database schema for the cache control database.
        """
        cache_table.create()

    def _drop_db_schema(self, cache_table):
        """
        Drops the database schema for the cache control database.
        """
        cache_table.drop()
