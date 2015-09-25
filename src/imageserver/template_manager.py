#
# Quru Image Server
#
# Document:      template_manager.py
# Date started:  22 Sep 2015
# By:            Matt Fozard
# Purpose:       Provides a managed interface to the image templates
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

from datetime import datetime, timedelta
import threading

from models import ImageTemplate, Property
from template_attrs import TemplateAttrs
from util import KeyValueCache


class ImageTemplateManager(object):
    """
    Provides access to image templates (used mostly by the image manager),
    in a variety of formats, backed by a cache for performance.

    The cache is invalidated and refreshed automatically.
    Rather than having to monitor object change times and search for added and
    deleted rows, we'll just use a simple counter for detecting database changes.
    This is the same mechanism as used for PermissionsManager.
    """
    TEMPLATE_CACHE_SYNC_INTERVAL = 60

    _TEMPLATE_LIST_KEY = '__template_info_list__'
    _TEMPLATE_NAMES_KEY = '__template_names__'
    _TEMPLATE_NAMES_LOWER_KEY = '__template_names_lower__'

    def __init__(self, data_manager, logger):
        self._db = data_manager
        self._logger = logger
        self._data_version = -1
        self._template_cache = KeyValueCache()
        self._update_lock = threading.Lock()
        self._last_check = datetime.min

    def get_template_list(self):
        """
        Returns a list of {id, name, description} dictionaries representing
        the available templates, sorted by name.
        """
        self._check_data_version()
        cached_list = self._template_cache.get(ImageTemplateManager._TEMPLATE_LIST_KEY)
        if cached_list is None:
            db_obj_list = [
                tdata['db_obj'] for tdata in self._template_cache.values()
                if isinstance(tdata, dict)
            ]
            cached_list = [
                {'id': dbo.id, 'name': dbo.name, 'description': dbo.description}
                for dbo in db_obj_list
            ]
            cached_list.sort(key=lambda o: o['name'])
            self._template_cache.set(ImageTemplateManager._TEMPLATE_LIST_KEY, cached_list)
        return cached_list

    def get_template_names(self, lowercase=False):
        """
        Returns a sorted list of available template names - those names that
        are valid for use with get_template() and when generating an image.
        """
        self._check_data_version()
        if lowercase:
            cached_list = self._template_cache.get(ImageTemplateManager._TEMPLATE_NAMES_LOWER_KEY)
            if cached_list is None:
                names_list = self._get_cached_names_list(True)
                cached_list = [name.lower() for name in names_list]
                self._template_cache.set(
                    ImageTemplateManager._TEMPLATE_NAMES_LOWER_KEY, cached_list
                )
            return cached_list
        else:
            cached_list = self._template_cache.get(ImageTemplateManager._TEMPLATE_NAMES_KEY)
            if cached_list is None:
                cached_list = self._get_cached_names_list(True)
                self._template_cache.set(
                    ImageTemplateManager._TEMPLATE_NAMES_KEY, cached_list
                )
            return cached_list

    def get_template(self, name):
        """
        Returns the TemplateAttrs object matching the given name (case insensitive),
        or None if no template matches the name.
        """
        self._check_data_version()
        tdata = self._template_cache.get(name.lower())
        return tdata['attr_obj'] if tdata is not None else None

    def get_template_db_obj(self, name):
        """
        Returns the ImageTemplate database object matching the given name
        (case insensitive), or None if no template matches the name.
        """
        self._check_data_version()
        tdata = self._template_cache.get(name.lower())
        return tdata['db_obj'] if tdata is not None else None

    def get_template_dict(self, name):
        """
        Returns a dictionary representing the TemplateAttrs object with the given
        name (case insensitive), or None if no template matches the name.
        """
        db_template = self.get_template_db_obj(name)
        return db_template.template if db_template else None

    def reset(self):
        """
        Invalidates the cached template data by incrementing the database data
        version number. This change will be detected on the next call to this
        object, and within the SYNC_INTERVAL by all other processes.
        """
        with self._update_lock:
            new_ver = self._db.increment_property(Property.IMAGE_TEMPLATES_VERSION)
        self._last_check = datetime.min
        self._logger.info('Image templates setting new version ' + new_ver)

    def _load_data(self):
        """
        Re-populates the internal caches with the latest template data from the database.
        The internal update lock must be held while this method is being called.
        """
        # Reset the caches
        self._template_cache.clear()
        db_ver = self._db.get_object(Property, Property.IMAGE_TEMPLATES_VERSION)
        self._data_version = int(db_ver.value)

        # Load the templates
        db_templates = self._db.list_objects(ImageTemplate)
        for db_template in db_templates:
            try:
                # Create a TemplateAttrs (this also validates the template values)
                template_attrs = TemplateAttrs.from_dict(
                    db_template.name,
                    db_template.template
                )
                # If here it's valid, so add to cache
                self._template_cache.set(
                    db_template.name.lower(),
                    {'db_obj': db_template, 'attr_obj': template_attrs}
                )
            except Exception as e:
                self._logger.error(
                    'Unable to load \'%s\' template configuration: %s' % (
                        db_template.name, str(e)
                    )
                )
        self._logger.info('Loaded templates: ' + ', '.join(self._template_cache.keys()))

    def _check_data_version(self, _force=False):
        """
        Periodically checks for changes in the template data, sets the
        internal data version number, and resets the caches if necessary.
        Uses an internal lock for thread safety.
        """
        check_secs = ImageTemplateManager.TEMPLATE_CACHE_SYNC_INTERVAL
        if _force or self._last_check < (datetime.utcnow() - timedelta(seconds=check_secs)):
            # Check for newer data version
            if self._update_lock.acquire(0):  # 0 = nonblocking
                try:
                    old_ver = self._data_version
                    db_ver = self._db.get_object(Property, Property.IMAGE_TEMPLATES_VERSION)
                    if int(db_ver.value) != old_ver:
                        action = 'initialising with' if old_ver == -1 else 'detected new'
                        self._logger.info('Image templates %s version %s' % (action, db_ver.value))
                        self._load_data()
                finally:
                    self._last_check = datetime.utcnow()
                    self._update_lock.release()

    def _get_cached_names_list(self, sort=False):
        """
        Returns a list of all the template names currently in the internal cache.
        """
        db_obj_list = [
            tdata['db_obj'] for tdata in self._template_cache.values()
            if isinstance(tdata, dict)
        ]
        names_list = [dbo.name for dbo in db_obj_list]
        if sort:
            names_list.sort()
        return names_list
