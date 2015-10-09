#
# Quru Image Server
#
# Document:      image_manager.py
# Date started:  07 Mar 2011
# By:            Matt Fozard
# Purpose:       Image management engine and primary class
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
# 25 Nov 14  Matt  v1.17 Standardise ImageAttrs pre-processing and validation
# 27 Feb 15  Matt  #532 Auto-reload templates
#

# TODO Can we make base image detection more intelligent to work with cropped images?
#      Currently auto-pyramid for cropped images has no effect.

import copy
import ConfigParser
import glob
import os
import threading
import time

import exif

from errors import DBDataError, DoesNotExistError, ImageError, ServerTooBusyError
from filesystem_manager import get_upload_directory, path_exists
from filesystem_manager import get_file_data, put_file_data
from filesystem_manager import get_file_info
from filesystem_sync import auto_sync_file, set_image_properties
from image_attrs import ImageAttrs
from image_wrapper import ImageWrapper
from imagemagick import imagemagick_init
from imagemagick import imagemagick_adjust_image, imagemagick_get_image_profile_data
from imagemagick import imagemagick_get_image_dimensions, imagemagick_get_version_info
from models import FolderPermission, Image, ImageHistory, Task
from template_attrs import TemplateAttrs
from util import default_value, get_file_extension, parse_colour
from util import filepath_filename, validate_filename


class ImageManager(object):
    """
    Provides image management and image retrieval functions backed by a cache
    """
    IMAGE_ERROR_HEADER = '*ERROR*'
    TEMPLATE_CHECK_SECONDS = 60 * 5

    def __init__(self, data_manager, cache_manager, task_manager,
                 permissions_manager, settings, logger):
        self._data = data_manager
        self._cache = cache_manager
        self._tasks = task_manager
        self._permissions = permissions_manager
        self._settings = settings
        self._logger = logger
        self.__icc_profiles = None
        self._icc_load_lock = threading.Lock()
        self.__templates = None
        self.__templates_mtime = 0
        self.__templates_ctime = 0
        self._templates_load_lock = threading.Lock()
        # Load C back-end
        imagemagick_init(
            settings['GHOSTSCRIPT_PATH'],
            settings['TEMP_DIR'],
            settings['PDF_BURST_DPI']
        )
        logger.info('Loaded imaging library: ' + imagemagick_get_version_info())

    def finalise_image_attrs(self, image_attrs):
        """
        For the given image attributes object, applies template values
        (if a template is defined), applies default image attributes,
        normalises the resulting object, and validates it to ensure it is
        ready for use.

        This function should usually be called before requesting an image
        so that global settings and standard parameter behaviours are enforced.

        Raises a ValueError if the finalised image attributes fail validation.
        """
        # Validate first so we can validate the template value before using it
        image_attrs.validate()
        # Apply template values if required, using override False
        # so that web params take precedence over template.
        if image_attrs.template():
            self._poll_reload_templates()  # #532 Auto-reload image templates
            self._apply_template(image_attrs.template(), image_attrs, False)
        # Apply system default values for anything still not set
        self._apply_defaults(image_attrs)
        # Lastly wipe any redundant values so we get more consistent cache keys
        image_attrs.normalise_values()

    def get_template_names(self):
        """
        Returns a list of available template names - those names that
        are valid for use in the 'template' attribute of an ImageAttrs object.
        """
        return self._templates.keys()

    def get_template(self, template_name):
        """
        Returns the TemplateAttrs object for the template name,
        or raises a KeyError if the template name does not exist.
        """
        return self._templates[template_name]

    def get_icc_profile_names(self, colorspace=None):
        """
        Returns a list of available ICC profile names - those names that
        are valid for use in the 'icc' attribute of an ImageAttrs object -
        optionally filtered by a colorspace (e.g. "RGB").
        """
        if colorspace is not None:
            return [
                k for k, v in self._icc_profiles.iteritems() if v[0] == colorspace
            ]
        else:
            return self._icc_profiles.keys()

    def get_icc_profile_colorspaces(self):
        """
        Returns a list of the unique colorspace types of the available ICC
        profiles, e.g. ["RGB", "CMYK", "GRAY"]
        """
        return list(set(v[0] for v in self._icc_profiles.itervalues()))

    def get_image_formats(self):
        """
        Returns a list of supported image formats (as file extensions)
        e.g. ['jpg','png'].
        """
        return self._settings['IMAGE_FORMATS'].keys()

    def put_image(self, current_user, file_wrapper, file_name,
                  upload_path_idx=-1, upload_path=None, overwrite=False):
        """
        Stores an image file on the server and returns its new
        ImageAttrs object and detached database image object.

        The file_wrapper must be a Werkzeug FileStorage object for the uploaded
        file, and file_name is the name (without path) to save as.

        The destination path can be supplied either as an index into the
        IMAGE_UPLOAD_DIRS list, or as a user-supplied path relative to IMAGES_BASE_DIR.
        It is mandatory to provide either a path index or a manual path, and the path
        must not contain the filename. If a manual path is provided, it must already
        exist on the server (user supplied paths are untrusted). If a path index is
        provided and the resulting entry from IMAGE_UPLOAD_DIRS does not exist, it
        will be created.

        If a file of the same name already exists in the destination path, the
        existing file will be replaced if overwrite is True, otherwise an exception
        will be raised.

        On error storing the file, any of the following exceptions may be raised:

        - ValueError - if a parameter is missing or has an invalid value
        - IOError - if the file could not be created
        - AlreadyExistsError - if a file with the same name already exists and overwrite is False
        - DoesNotExistError - if the user-supplied upload path does not exist
        - ImageError - if the image is an unsupported format (determined from the filename)
        - SecurityError - if the current user does not have permission to upload to the target
                          path or if the target path is outside IMAGES_BASE_DIR
        """
        # Check mandatory params
        if file_wrapper is None:
            raise ValueError('No image file was provided')
        if upload_path_idx < 0 and upload_path is None:
            raise ValueError('No image destination was provided')
        file_name = file_name.strip() if file_name is not None else None
        if not file_name:
            raise ValueError('No image file name was provided')

        # File name must be "a.ext"
        validate_filename(file_name)
        # and the extension must be supported
        file_name_extension = get_file_extension(file_name)
        if file_name_extension not in self.get_image_formats():
            raise ImageError('The file is not a supported image format. ' +
                             'Supported types are: ' + ', '.join(self.get_image_formats()) + '.')

        # Load the destination path if it's a pre-defined one
        allow_path_creation = False
        if upload_path_idx >= 0:
            _, upload_path = get_upload_directory(upload_path_idx)
            allow_path_creation = True

        # Strip any leading path char from the path
        if upload_path[0:1] == '/' or upload_path[0:1] == '\\':
            upload_path = upload_path[1:]

        # Do not allow people to upload into IMAGES_BASE_DIR root
        upload_path = upload_path.strip()
        if not upload_path:
            raise ValueError('No destination path was provided')

        # Check for upload folder existence ahead of permission check
        if not path_exists(upload_path, require_directory=True) and not allow_path_creation:
            raise DoesNotExistError('Path \'' + upload_path + '\' does not exist')

        # Require upload permission or file admin
        self._permissions.ensure_folder_permitted(
            upload_path,
            FolderPermission.ACCESS_UPLOAD,
            current_user,
            folder_must_exist=False
        )

        # See if the image already exists
        final_path = os.path.join(upload_path, file_name)
        file_existed = path_exists(final_path, require_file=True)

        # Store the new file
        # Relies on put_file_data() to perform further path checks
        self._logger.debug(
            ('Replacing existing' if file_existed else 'Storing uploaded') +
            ' file \'' + file_name + '\' at \'' + upload_path +
            '\', allow path create ' + str(allow_path_creation)
        )
        put_file_data(file_wrapper, upload_path, file_name, allow_path_creation, overwrite)

        # Success - create/replace the image database record
        # and clear out the old version if it previously existed
        stored_attrs = ImageAttrs(final_path)
        self.reset_image(stored_attrs, auto_history=False)  # Sets database_id()
        if stored_attrs.database_id() < 1:
            raise DBDataError('No database ID for uploaded image ' + final_path)

        # Add audit history
        db_session = self._data.db_get_session()
        try:
            db_image = self._data.get_image(
                stored_attrs.database_id(),
                _db_session=db_session
            )
            self._data.add_image_history(
                db_image,
                current_user,
                ImageHistory.ACTION_REPLACED if file_existed else ImageHistory.ACTION_CREATED,
                'File uploaded by user',
                _db_session=db_session,
                _commit=True
            )
        finally:
            db_session.close()

        # Return the new image attributes
        self._logger.debug('Stored uploaded file, returning image ' + str(stored_attrs))
        return stored_attrs, db_image

    def get_image_original(self, image_attrs):
        """
        Returns an ImageWrapper object containing an original unchanged image
        (attributes in image_attrs other than the filename are ignored),
        or None if the image could not be found or could not be read.

        Raises a SecurityError if the file path requested attempts to read outside
        of the images directory, or an ImageError if the requested image is in
        an invalid or unsupported file format.
        """
        self._logger.debug('Reading original image for ' + image_attrs.filename())

        # Check the filename first
        file_name_extension = get_file_extension(image_attrs.filename())
        if file_name_extension not in self.get_image_formats():
            raise ImageError('The file is not a supported image format')

        file_data = get_file_data(image_attrs.filename())
        if file_data is None:
            return None
        # Return the requested image
        return ImageWrapper(
            file_data,
            ImageAttrs(image_attrs.filename(), image_attrs.database_id()),
            False,
            self.get_image_original_modified_time(image_attrs),
            self._get_expiry_secs(image_attrs)
        )

    def get_image(self, image_attrs, cache_result=True):
        """
        Returns an ImageWrapper object for the image with the specified attributes,
        or None if the image's filename could not be found or could not be read.
        If no attributes are specified, the original image is returned unchanged.

        Unless you require special behaviour, the image_attrs object should
        have first been passed through finalise_image_attrs() to normalise
        and validate it.

        This method returns the image from cache wherever possible.
        When cache_result is True (the default), non-cached images are added to
        cache for faster retrieval by subsequent calls. When cache_result is
        'refresh', any existing cache entries are first removed.

        Raises a SecurityError if the file path requested attempts to read outside
        of the images directory, an ImageError if the requested image is invalid
        or is an unsupported file format, a ServerTooBusyError if a timeout occurs
        waiting for an image to be generated.
        """
        # Init a few things
        debug_mode = self._settings['DEBUG']
        ret_from_cache = False
        cache_key = image_attrs.get_cache_key()
        wait_timeout = min(max(self._settings['IMAGE_GENERATION_WAIT_TIMEOUT'], 10), 120)

        # See if caller wants to refresh the cache.
        # We must in fact clear all cache entries for the same file+format to
        # prevent an old version being used as a base image for this one again.
        # v1.12 Re-read the disk file too (to detect changed image dimensions).
        # v1.14 Do not repeat the PDF bursting (only because it's too easy to trigger this way).
        if cache_result == 'refresh':
            self._logger.debug('Cleaning cache entries for ' + image_attrs.filename())
            self.reset_image(image_attrs, re_burst_pdf=False)
            cache_result = True

        # See if the exact same custom image is already in cache
        if debug_mode:
            self._logger.debug('Checking cache for requested image ' + str(image_attrs))
        ret_image_data = self._cache.get(cache_key)

        if ret_image_data is None and self._is_image_lock(cache_key):
            # The requested image + attrs is not yet in cache but someone else
            # is currently generating it. Wait for it to complete or time out.
            if debug_mode:
                self._logger.debug('Waiting while another client generates ' + str(image_attrs))
            wait_until = time.time() + wait_timeout
            while self._is_image_lock(cache_key) and time.time() < wait_until:
                time.sleep(1)
            # Try again
            ret_image_data = self._cache.get(cache_key)
            if ret_image_data is None:
                self._logger.warn('Timed out waiting for ' + str(image_attrs))
                if (
                    self._settings['IMAGE_GENERATION_RAISE_TOO_BUSY'] and
                    not self._settings['BENCHMARKING']
                ):
                    # We might have 10 (100!) requests queued up waiting, so an
                    # error now is preferable to letting them all go through
                    raise ServerTooBusyError()

        if ret_image_data is None:
            # We'll need to generate the image.
            self._logger.debug('No exact match, trying to find a cached base image')
            try:
                if cache_result:
                    # Notify other clients what we'll put in the cache
                    # #2293 Don't overwrite the lock if there's one already
                    if not self._is_image_lock(cache_key):
                        self._set_image_lock(cache_key, wait_timeout)

                # See if there is a version already cached that we can use as a base
                base_image = self._get_base_image(image_attrs)

                if image_attrs.tile_spec() is not None:
                    # Performance special case - always generate the non-tiled version
                    # of a tile request, otherwise calls for all the other tiles have
                    # to start from scratch too
                    if (base_image is None or
                        base_image.attrs().width() != image_attrs.width() or
                        base_image.attrs().height() != image_attrs.height()
                    ):
                        self._logger.debug('Creating new base image for requested tile')
                        base_image = self._get_tile_base_image(image_attrs)

                if base_image is None:
                    if debug_mode:
                        self._logger.debug('No base image found, reading original disk file')
                    file_data = get_file_data(image_attrs.filename())
                    if file_data is None:
                        # Disk file read failed
                        return None
                    # See whether to auto-pyramid the original image for the future
                    self._auto_pyramid_image(file_data, image_attrs)
                    # Set the original image from disk as the base image
                    file_attrs = ImageAttrs(image_attrs.filename(), image_attrs.database_id())
                    base_image = ImageWrapper(file_data, file_attrs)
                else:
                    if debug_mode:
                        self._logger.debug('Base image found: ' + str(base_image.attrs()))
                    # If the base image found is the full size,
                    # see whether to auto-pyramid the original image for the future
                    if not base_image.attrs().width() and not base_image.attrs().height():
                        self._auto_pyramid_image(base_image.data(), image_attrs)

                # Generate a new custom image
                try:
                    ret_image_data = self._adjust_image(
                        base_image.data(),
                        base_image.attrs(),
                        image_attrs
                    )
                except ImageError as e:
                    # Image generation failed. Carry on and cache the fact that it's
                    # broken so that other clients don't repeatedly try to re-generate.
                    ret_image_data = ImageManager.IMAGE_ERROR_HEADER + unicode(e)

                # Add it to cache for next time
                if cache_result:
                    if self._cache_image(ret_image_data, image_attrs):
                        if debug_mode:
                            self._logger.debug('Added new image to cache: ' + str(image_attrs))
                    else:
                        self._logger.warn('Failed to add image to cache: ' + str(image_attrs))
            finally:
                if cache_result:
                    # Tell anyone waiting they can now grab the cached image
                    self._clear_image_lock(cache_key)
        else:
            # We found the requested image in cache
            ret_from_cache = True
            if debug_mode:
                self._logger.debug('Retrieved exact match from cache for ' + str(image_attrs))

        # If there was an imaging error (just now or previously cached),
        # raise the exception now
        if ret_image_data.startswith(ImageManager.IMAGE_ERROR_HEADER):
            msg = ret_image_data[len(ImageManager.IMAGE_ERROR_HEADER):]
            raise ImageError(msg)

        # v1.17 Get/set the image's last modification time
        modified_time = self.get_image_modified_time(image_attrs)
        if modified_time == 0:
            modified_time = time.time()
            self._cache_image_metadata(image_attrs, modified_time)

        # Return the requested image
        expiry_secs = self._get_expiry_secs(image_attrs)
        attachment = self._get_attachment_setting(image_attrs)
        do_stats = self._get_stats_setting(image_attrs)
        return ImageWrapper(
            ret_image_data,
            image_attrs,
            ret_from_cache,
            modified_time,
            expiry_secs,
            attachment,
            do_stats
        )

    def get_image_modified_time(self, image_attrs):
        """
        Returns the last known time the image (as described by image_attrs)
        was modified or created, as UTC seconds since the epoch.

        Or returns 0 if this information is not in cache, because the image
        has not been generated, or because the cache entry for it has expired.

        Note that even if the last modification time is known, the associated
        image itself may not still be in cache (or may never have been cached).
        """
        image_metadata = self._cache.raw_get(
            image_attrs.get_metadata_cache_key(),
            integrity_check=True
        )
        return image_metadata['modified'] if image_metadata else 0

    def get_image_original_modified_time(self, image_attrs):
        """
        Returns the disk file modification time for an image
        (attributes in image_attrs other than the filename are ignored),
        or 0 if the disk file could not be found or could not be read.

        Raises a SecurityError if the file path requested attempts to read
        outside of the images directory.
        """
        file_stat = get_file_info(image_attrs.filename())
        return file_stat['modified'] if file_stat else 0

    def get_image_properties(self, filepath, return_unknown=True):
        """
        Reads the image dimensions and embedded image profile properties (EXIF,
        IPTC, TIFF, etc) from an image file. The original image file is always
        used, so that the value of the IMAGE_STRIP_DEFAULT setting does not affect
        this function.

        On success, a dictionary is returned containing the image width and height,
        and entries for the embedded data profile names, each containing a list of
        property names and values. For example:
        { 'width': 3000, 'height': 2000,
          'TIFF': [ ('Maker': 'Canon'), ('Model': '300D') ],
          'EXIF': [ ('Flash': 'Off'), ('ExposureMode': 'Auto') ] }
        where both the profile names and the properties will vary from image to image.

        By default, unrecognised properties are returned with their values in a raw
        format (e.g. code numbers rather than readable text). If return_unknown is
        False, unrecognised property names will not be returned at all.

        An empty dictionary is returned if the file could not be read or there
        was an error reading the image.

        Raises a SecurityError if the file path requested attempts to read outside
        of the images directory.
        """
        # Get original file
        file_data = get_file_data(filepath)
        if file_data is None:
            return {}
        # Get image info
        try:
            (width, height) = imagemagick_get_image_dimensions(file_data)
            file_properties = imagemagick_get_image_profile_data(file_data)
        except Exception as e:
            self._logger.error('Error reading image properties for %s: %s' % (filepath, str(e)))
            return {}
        # Convert to the promised return structure
        props = {'width': width, 'height': height}
        props.update(exif.raw_list_to_dict(file_properties, False, return_unknown))
        return props

    @staticmethod
    def get_image_dimensions(filepath):
        """
        Reads the image dimensions from an image file, without decoding the
        image if possible. The original image file is always used.

        Returns a tuple containing the image width and height,
        or (0, 0) if the image is unsupported or could not be read.

        Raises a SecurityError if the file path requested attempts to read
        outside of the images directory.
        """
        file_data = get_file_data(filepath)
        return (0, 0) if file_data is None else \
            ImageManager.get_image_data_dimensions(file_data)

    @staticmethod
    def get_image_data_dimensions(image_data):
        """
        Reads the image dimensions from raw image data, without decoding the
        image if possible. Returns a tuple containing the image width and height,
        or (0, 0) if the image type is unsupported or could not be read.
        """
        try:
            return imagemagick_get_image_dimensions(image_data)
        except:
            return (0, 0)

    def reset_image(self, image_attrs, auto_history=True, re_burst_pdf=True):
        """
        This method should be called when an image file changes on disk.
        The disk file is re-checked for existence, and (regardless of whether
        it still exists or not), all cached variations of the image are deleted,
        and the database image properties are reset. If the disk file no longer
        exists, additional operations may occur in the background, such as
        checking for and handling the deletion of the file's folder.

        By default, if the file still exists and is a PDF, the PDF is split
        into images again as a background task. This can be disabled by setting
        re_burst_pdf to False.

        If the database ID is not already set in image_attrs, this method
        attempts to set it. Note the ID will remain unset if both the image
        file does not exist on disk, and there is no database record
        (active or historical) for its path.

        If auto_history is True, image history will be written if the file is
        detected as existing or as being deleted for the first time.
        Set to False if image history is to be written separately.
        """
        db_session = self._data.db_get_session()
        db_commit = False
        try:
            # Sync database with file
            db_image = auto_sync_file(
                image_attrs.filename(),
                self._data,
                self._tasks,
                anon_history=auto_history,
                burst_pdf=re_burst_pdf,
                _db_session=db_session
            )
            # Auto-set the ID in image_attrs, needed for put_image and _uncache_image
            if image_attrs.database_id() == -1 and db_image:
                image_attrs.set_database_id(db_image.id)
            # Delete cache entries
            if image_attrs.database_id() > 0:
                self._uncache_image(image_attrs)
            # Update db image properties (if file exists)
            if db_image and db_image.status == Image.STATUS_ACTIVE:
                set_image_properties(db_image)
            db_commit = True
        finally:
            try:
                if db_commit:
                    db_session.commit()
                else:
                    db_session.rollback()
            finally:
                db_session.close()

    def _is_image_lock(self, image_key):
        """
        Returns whether there is an image lock currently in place for the given key.
        """
        lock = self._cache.raw_get('LOCK_' + image_key)
        return lock is not None

    def _set_image_lock(self, image_key, timeout_secs):
        """
        Sets an image lock with a timeout (in seconds) for a given unique key.
        Returns whether the lock was created (and did not already exist).
        """
        return self._cache.raw_atomic_add('LOCK_' + image_key, 'LOCK', timeout_secs)

    def _clear_image_lock(self, image_key):
        """
        Clears the image lock with the given unique key.
        There is no effect if the key does not exist.
        """
        self._cache.raw_delete('LOCK_' + image_key)

    def _get_attrs_hash(self, iformat=None, fill=None, tile_spec=None):
        """
        Returns a numeric hash representing the combination of the supplied
        image attributes. Hash collisions are very unlikely, but possible.
        """
        return hash(
            'F' + str(iformat) + ',I' + str(fill) + ',E' + str(tile_spec)
        )

    def _get_base_image(self, target_attrs):
        """
        Returns an ImageWrapper containing an existing image that may be used
        as the base image for a pending call to _adjust_image(). The
        target_attrs parameter specifies the final image required, and
        is used to search the image cache for suitable base image candidates.
        If no suitable base image can be found, None is returned.
        """
        image_id = target_attrs.database_id()
        assert image_id > 0, 'Image database ID must be set to search base images'
        # Find candidate images in cache already derived from the same file.
        # For a tile, we can consider either non-tiles or the exact same tile.
        # For non-tiles, we want to exclude all tiles.
        # Order to get the smallest base image first when multiple candidates.
        if target_attrs.tile_spec() is not None:
            format_hash = [
                self._get_attrs_hash(target_attrs.format(), target_attrs.fill(), None),
                self._get_attrs_hash(target_attrs.format(), target_attrs.fill(), target_attrs.tile_spec())
            ]
        else:
            format_hash = self._get_attrs_hash(target_attrs.format(), target_attrs.fill(), None)
        # Search the cache
        base_candidates = self._cache.search(
            order='+size',
            max_rows=100,
            searchfield1__eq=image_id,
            searchfield2__eq=format_hash,
            searchfield3__gte=[target_attrs.width(), None],
            searchfield4__gte=[target_attrs.height(), None]
        )
        # Loop through the results and see if any would work for us
        for result in base_candidates:
            result_key = result['key']
            result_attrs = result['metadata']
            base_err = result_attrs.suitable_for_base(target_attrs)
            if base_err == 0:
                # See if this one is still in the cache
                base_data = self._cache.get(result_key)
                if base_data is not None:
                    # Success
                    return ImageWrapper(base_data, result_attrs, True)
            elif self._settings['DEBUG']:
                self._logger.debug(
                    'Base image candidate ' + str(result_attrs) +
                    ' rejected for reason code ' + str(base_err)
                )
        return None

    def _cache_image_metadata(self, image_attrs, modified_time):
        """
        As a partner to _cache_image(), adds additional image metadata to cache.
        Currently the only metadata field is last modification time.
        """
        ok = self._cache.raw_put(
            image_attrs.get_metadata_cache_key(), {
                'modified': modified_time
            },
            integrity_check=True
        )
        if not ok:
            self._logger.warn(
                'Failed to cache modification time for: ' +
                image_attrs.get_metadata_cache_key()
            )
        elif self._settings['DEBUG']:
            self._logger.debug(
                'Cached new modification time for: ' +
                image_attrs.get_metadata_cache_key()
            )
        return ok

    def _cache_image(self, image_data, image_attrs):
        """
        Adds image data and its associated attributes and search keys to cache.
        Returns a boolean indicating success.
        """
        image_id = image_attrs.database_id()
        assert image_id > 0, 'Image database ID must be set to cache images'
        format_hash = self._get_attrs_hash(
            image_attrs.format(),
            image_attrs.fill(),
            image_attrs.tile_spec()
        )
        search_info = {
            'searchfield1': image_id,
            'searchfield2': format_hash,
            'searchfield3': image_attrs.width(),
            'searchfield4': image_attrs.height(),
            'searchfield5': None,
            'metadata': image_attrs
        }
        return self._cache.put(
            image_attrs.get_cache_key(),
            image_data,
            search_info=search_info
        )

    def _uncache_image(self, image_attrs, uncache_variants=True):
        """
        Deletes cache entries associated with an image,
        optionally including all variants of the image in any file format.
        """
        image_id = image_attrs.database_id()
        assert image_id > 0, 'Database ID must be set to uncache an image'
        # #2589 Always uncache the exact image, as sometimes the _cache.search()
        #       in _uncache_image_id() doesn't seem to bring it back
        self._cache.delete(image_attrs.get_cache_key())
        self._cache.raw_delete(image_attrs.get_metadata_cache_key())
        # End #2589
        if uncache_variants:
            self._uncache_image_id(image_id)

    def _uncache_image_id(self, image_id):
        """
        Deletes cache entries associated with an image ID,
        including all variants of the image in any file format.
        """
        matches = self._cache.search(searchfield1__eq=image_id)
        for match in matches:
            match_image_key = match['key']
            match_attrs = match['metadata']
            # Delete the cached image and its search keys
            self._cache.delete(match_image_key)
            # v1.17 Also delete any cached metadata
            self._cache.raw_delete(match_attrs.get_metadata_cache_key())
            # Delete any associated lock flags, etc
            self._cache.raw_delete('LOCK_' + match_image_key)
            self._cache.raw_delete('TILE_BASE_' + match_image_key)
            pyr_key = 'PYRAMID_IMG:' + str(image_id)
            if match_attrs.format():
                pyr_key += ',F' + match_attrs.format()
            self._cache.raw_delete(pyr_key)

    def _get_tile_base_image(self, image_attrs):
        """
        Generates and caches the base image required for an image tile.
        This is the same set of image attributes requested, minus the tile spec.

        See the internal comments, but this function is designed to handle
        multiple threads wanting the same base image (i.e. several tiles
        requested at once) the first time around. After that, it will return
        None, because the cached base image should then be available and this
        function should not be needed again.

        Returns an ImageWrapper containing the new base image, or None if the
        image could not be generated or has been generated previously.
        """
        assert image_attrs.tile_spec() is not None, 'Tile base requested for non-tile image'
        # Requires the cache (the whole base image mechanism requires it)
        if not self._cache.connected():
            self._logger.warn('Cache is not connected, not generating tile base')
            return None
        # As a defensive measure we will prevent repeated calls for the same
        # thing, though apart from the first time around, this shouldn't happen
        # very often (and then only for cache ejections).
        # Don't use an atomic flag here, as until the base image generation is
        # complete we actually want to allow duplicate requests. The first one
        # will generate the base image and the others will stack up waiting for it
        # (see the image lock in get_image). So all threads get their base image
        # but only 1 thread will have generated it = less load, more speed.
        base_image_attrs = copy.copy(image_attrs)
        base_image_attrs._tile = None
        gen_flag = 'TILE_BASE_' + base_image_attrs.get_cache_key()
        if self._cache.raw_get(gen_flag) is not None:
            # Warn as this indicates faulty base image detection
            self._logger.warn(
                'Tile base generation already performed for ' + str(image_attrs)
            )
            return None
        # Generate the base image
        try:
            self._logger.debug('Performing tile base generation for ' + str(image_attrs))
            base_img_wrapper = self.get_image(base_image_attrs, cache_result=True)
            self._logger.debug('Tile base generation completed for ' + str(image_attrs))
            return base_img_wrapper
        except ImageError as e:
            self._logger.error(
                'Error generating tile base for %s: %s' % (str(image_attrs), str(e))
            )
            return None
        finally:
            # Now flag the generation as complete. Auto-expire after a while
            # though - as noted above this is really only a defensive measure.
            self._cache.raw_put(gen_flag, 'DONE', expiry_secs=600)

    def _auto_pyramid_image(self, original_data, image_attrs):
        """
        Checks the supplied image, and if it exceeds a certain size, meets
        certain criteria, and if the operation has not already been performed,
        generates and caches one or more reduced size copies of the image.
        This can greatly speed up future requests for small versions of the image.

        Pyramid generation, if required, takes place asynchronously. An internal
        lock is used to prevent any other thread or process from performing the
        same process on the same image.
        """
        if (self._settings["AUTO_PYRAMID_THRESHOLD"] < 1000000):
            return
        # Only continue for images that will be tiled, otherwise we might end up
        # kicking off large resize operations for e.g. someone running their mouse
        # over the thumbnail previews on the file browsing page. Maybe this can be
        # more intelligent in the future...
        if image_attrs.tile_spec() is None:
            self._logger.debug(
                'No tile spec, will not pyramid image %s' % image_attrs.filename()
            )
            return
        # Do not pyramid for overlays, they can rarely be re-used
        if image_attrs.overlay_src() is not None:
            self._logger.debug(
                'Image contains an overlay, will not pyramid image %s' % image_attrs.filename()
            )
            return
        # Is image large enough to meet the threshold?
        (w, h) = imagemagick_get_image_dimensions(original_data)
        if (w * h) < self._settings["AUTO_PYRAMID_THRESHOLD"]:
            self._logger.debug(
                'Image below threshold, will not pyramid image %s' % image_attrs.filename()
            )
            return
        # Requires the cache
        if not self._cache.connected():
            self._logger.warn(
                'Cache is not connected, cannot pyramid image %s' % image_attrs.filename()
            )
            return
        # Attempt to ensure we don't force useful stuff out of small caches
        if float(len(original_data)) / float(self._cache.capacity()) > 0.05:
            self._logger.warn(
                'Image is >5%% of free cache, will not pyramid image %s' % image_attrs.filename()
            )
            return
        # See if anyone else has done a pyramid for this image+format
        assert image_attrs.database_id() > 0, \
            'Image database ID must be set to pyramid an image'
        lock_flag = 'PYRAMID_IMG:' + str(image_attrs.database_id())
        if image_attrs.format():
            lock_flag += ',F' + image_attrs.format()
        # atomic_add side effect in the "if" ... sorry!
        if (self._cache.raw_get(lock_flag) is not None or
            not self._cache.raw_atomic_add(lock_flag, 'DONE')
        ):
            self._logger.debug('Pyramid generation already done for %s' % image_attrs.filename())
            return
        # All criteria met
        self._logger.debug('Pyramid criteria met for image %s' % image_attrs.filename())
        # If this has been done before but the lock flag was purged from cache,
        # then the pyramid generation routine will run again. However if the
        # previously generated images are still in cache, they will not be
        # re-generated (and the new lock flag will hopefully hang around).
        self._tasks.add_task(
            None,
            'Pyramid ' + image_attrs.filename(with_path=False),
            'create_image_pyramid',
            {
                'image_id': image_attrs.database_id(),
                'image_src': image_attrs.filename(),
                'page': image_attrs.page(),
                'format': image_attrs.format(),
                'colorspace': image_attrs.colorspace(),
                'start_width': w,
                'start_height': h,
                'target_pixels': self._settings["AUTO_PYRAMID_THRESHOLD"]
            },
            Task.PRIORITY_NORMAL,
            'debug',
            'warn',
            600
        )

    def _adjust_image(self, base_image_data, base_image_attrs, new_image_attrs):
        """
        Returns raw image data - the supplied raw image and attributes transformed
        to apply the specified new attributes. If no attributes are specified, the
        supplied image data is returned unchanged. On error creating the new
        image, an ImageError is raised.
        """
        # See if we have been requested to alter any image attributes.
        if new_image_attrs.attributes_change_image():

            # Set the final image attributes
            iformat = new_image_attrs.format()
            page = default_value(new_image_attrs.page(), 1)
            width = default_value(new_image_attrs.width(), 0)
            height = default_value(new_image_attrs.height(), 0)
            align_h = new_image_attrs.align_h()
            align_v = new_image_attrs.align_v()
            rotation = default_value(new_image_attrs.rotation(), 0.0)
            flip = new_image_attrs.flip()
            top = default_value(new_image_attrs.top(), 0.0)
            left = default_value(new_image_attrs.left(), 0.0)
            bottom = default_value(new_image_attrs.bottom(), 1.0)
            right = default_value(new_image_attrs.right(), 1.0)
            autocropfit = default_value(new_image_attrs.crop_fit(), False)
            autosizefit = default_value(new_image_attrs.size_fit(), False)
            fill = default_value(new_image_attrs.fill(), '#ffffff')
            sharpen = default_value(new_image_attrs.sharpen(), 0)
            rquality = self._settings['IMAGE_RESIZE_QUALITY']
            overlay_src = new_image_attrs.overlay_src()
            overlay_size = default_value(new_image_attrs.overlay_size(), 1.0)
            overlay_pos = new_image_attrs.overlay_pos()
            overlay_opacity = default_value(new_image_attrs.overlay_opacity(), 1.0)
            icc_profile_name = new_image_attrs.icc_profile()
            icc_profile_intent = new_image_attrs.icc_intent()
            icc_profile_bpc = new_image_attrs.icc_bpc()
            colorspace = new_image_attrs.colorspace()
            dpi = default_value(new_image_attrs.dpi(), 0)
            strip_info = default_value(new_image_attrs.strip_info(), False)
            tile_spec = default_value(new_image_attrs.tile_spec(), (0, 0))
            # Setting the default image quality here
            # (AFTER checking whether attributes_change_image)
            # is a special case. Also see _apply_defaults().
            cquality = default_value(
                new_image_attrs.quality(),
                self._settings['IMAGE_QUALITY_DEFAULT']
            )

            # Now, if the base image is already rotated, cropped, sharpened etc,
            # do not re-apply the same adjustment. These checks rely heavily on
            # the behaviour of ImageAttrs.suitable_for_base()
            if base_image_attrs.page() is not None and \
               base_image_attrs.page() == page:
                page = 1
            if base_image_attrs.rotation() is not None and \
               base_image_attrs.rotation() == rotation:
                rotation = 0
            if base_image_attrs.flip() is not None and \
               base_image_attrs.flip() == flip:
                flip = None
            if base_image_attrs.top() is not None and \
               base_image_attrs.top() == top:
                top = 0.0
            if base_image_attrs.left() is not None and \
               base_image_attrs.left() == left:
                left = 0.0
            if base_image_attrs.bottom() is not None and \
               base_image_attrs.bottom() == bottom:
                bottom = 1.0
            if base_image_attrs.right() is not None and \
               base_image_attrs.right() == right:
                right = 1.0
            if base_image_attrs.crop_fit() and autocropfit:
                autocropfit = False
            if base_image_attrs.sharpen() is not None and \
               base_image_attrs.sharpen() == sharpen:
                sharpen = 0
            if base_image_attrs.overlay_src() is not None and \
               base_image_attrs.overlay_src() == overlay_src:
                overlay_src = None
                overlay_size = 0.0
            if base_image_attrs.icc_profile() is not None and \
               base_image_attrs.icc_profile() == icc_profile_name and \
               base_image_attrs.icc_intent() == icc_profile_intent and \
               default_value(base_image_attrs.icc_bpc(), False) == icc_profile_bpc:
                icc_profile_name = None
                icc_profile_intent = None
                icc_profile_bpc = None
            if base_image_attrs.tile_spec() is not None and \
               base_image_attrs.tile_spec() == tile_spec:
                tile_spec = (0, 0)
                rotation = 0
                top = left = 0.0
                bottom = right = 1.0

            # Get the overlay image data, if required
            overlay_image_data = None
            if overlay_src:
                overlay_image_data = get_file_data(overlay_src)
                if overlay_image_data is None:
                    raise DoesNotExistError('Overlay file \'' + overlay_src + '\' was not found')

            # Get ICC profile data, if required
            icc_profile_data = self._icc_profiles[icc_profile_name][1] if icc_profile_name else None

            try:
                return imagemagick_adjust_image(
                    base_image_data,
                    page, iformat,
                    width, height, autosizefit,
                    align_h, align_v, rotation, flip,
                    top, left, bottom, right, autocropfit,
                    fill, rquality, cquality, sharpen,
                    dpi, strip_info,
                    overlay_image_data, overlay_size, overlay_pos, overlay_opacity,
                    icc_profile_data, icc_profile_intent, icc_profile_bpc,
                    colorspace, tile_spec
                )
            except Exception as e:
                raise ImageError(str(e))
        else:
            # There are no attributes to change
            return base_image_data

    def _get_expiry_secs(self, image_attrs):
        """
        Returns the HTTP expiry / cache control time in seconds for an image.
        This value is determined by the image template if there is one and the
        expiry value is set, else by the image server global setting.
        """
        if image_attrs.template():
            template = self.get_template(image_attrs.template())
            template_expiry = template.expiry_secs()
            if template_expiry is not None:
                return template_expiry
        return self._settings['IMAGE_EXPIRY_TIME_DEFAULT']

    def _get_attachment_setting(self, image_attrs):
        """
        Returns True if the image attributes specify a template with the
        attachment setting enabled, otherwise False.
        """
        if image_attrs.template():
            template = self.get_template(image_attrs.template())
            if template.attachment():
                return True
        return False

    def _get_stats_setting(self, image_attrs):
        """
        Returns True unless the image attributes specify a template with the
        stats setting disabled.
        """
        if image_attrs.template():
            template = self.get_template(image_attrs.template())
            if template.record_stats() is not None:
                return template.record_stats()
        return True

    def _apply_template(self, template_name, dest_image_attrs, override_existing):
        """
        Applies the image attributes defined by a given template into an
        existing set of image attributes. If override_existing is True, the
        template attributes will be applied over any existing attributes.
        If override_existing is False, existing attributes will not be changed.
        """
        template = self.get_template(template_name)
        src_attrs = template.image_attrs
        dest_image_attrs.apply_template_values(
            override_existing,
            src_attrs.page(),
            src_attrs.format_raw(),
            src_attrs.width(),
            src_attrs.height(),
            src_attrs.align_h(),
            src_attrs.align_v(),
            src_attrs.rotation(),
            src_attrs.flip(),
            src_attrs.top(),
            src_attrs.left(),
            src_attrs.bottom(),
            src_attrs.right(),
            src_attrs.crop_fit(),
            src_attrs.size_fit(),
            src_attrs.fill(),
            src_attrs.quality(),
            src_attrs.sharpen(),
            src_attrs.overlay_src(),
            src_attrs.overlay_size(),
            src_attrs.overlay_pos(),
            src_attrs.overlay_opacity(),
            src_attrs.icc_profile(),
            src_attrs.icc_intent(),
            src_attrs.icc_bpc(),
            src_attrs.colorspace(),
            src_attrs.strip_info(),
            src_attrs.dpi()
        )

    def _apply_defaults(self, image_attrs):
        """
        Applies default image attributes, only where a default
        value is defined and the attribute is not yet set.
        """
        # Image format
        default_format = self._settings['IMAGE_FORMAT_DEFAULT'].lower()
        # Image quality
        # Handled in _adjust_image() as a special case, as we must not associate
        # a quality value with an image unless this attribute has been explicitly
        # set. If we did so, then requested an original image without any changes,
        # it would be converted to the default quality rather than being left alone.
        # Image colorspace
        default_colorspace = self._settings['IMAGE_COLORSPACE_DEFAULT'].lower()
        # Image DPI
        default_dpi = self._settings['PDF_BURST_DPI'] \
            if image_attrs.src_is_pdf() else \
            self._settings['IMAGE_DPI_DEFAULT']
        # Strip info
        default_strip = self._settings['IMAGE_STRIP_DEFAULT']
        # Apply
        image_attrs.apply_default_values(
            default_format, default_colorspace, default_strip, default_dpi
        )

    def _get_icc_colorspace(self, icc_data):
        """
        Returns the colorspace header field of an ICC profile
        E.g. "RGB", "CMYK", "GRAY", "XYZ", "LAB", "YCbr",
             or None if the ICC data is invalid.
        """
        if icc_data is not None and len(icc_data) > 128:
            # The colorspace flag is 4 bytes from position 16 in the 128 byte header
            # See http://www.color.org/specification/ICC1v43_2010-12.pdf
            return icc_data[16:20].strip()
        return None

    @property
    def _templates(self):
        """
        A lazy-loaded cache of the image templates, as a dictionary of form:
        { 'template_name': TemplateAttrs }
        """
        if self.__templates is None:
            with self._templates_load_lock:
                if self.__templates is None:
                    self.__templates = self._load_templates()
                    self.__templates_mtime = self._get_templates_mtime()
                    self.__templates_ctime = time.time()
        return self.__templates

    def _poll_reload_templates(self):
        """
        Checks for whether to reload the image templates,
        at most once every ImageManager.TEMPLATE_CHECK_SECONDS seconds.
        """
        if self.__templates is not None and self.__templates_ctime < (
            time.time() - ImageManager.TEMPLATE_CHECK_SECONDS
        ):
            if self._get_templates_mtime() != self.__templates_mtime:
                self._logger.info('Detected image template changes')
                self._reload_templates()
            self.__templates_ctime = time.time()

    def _reload_templates(self):
        """
        Clears the internal image template cache.
        """
        with self._templates_load_lock:
            self.__templates = None
            self.__templates_mtime = 0
            self.__templates_ctime = 0

    def _load_templates(self):
        """
        Finds and returns the configured image templates by searching for files
        named *.cfg in the image templates directory. Returns a dictionary
        of TemplateAttr objects mapped to filename (lower case, without file
        extension).
        Any invalid template configurations are logged but otherwise ignored.
        """
        templates = {}

        # Utility to allow no value for a config file option
        def _config_get(cp, get_fn, section, option, lower_case=False):
            if cp.has_option(section, option):
                val = get_fn(section, option)
                return val.lower() if lower_case else val
            else:
                return None

        # Find *.cfg
        cfg_files = glob.glob(unicode(os.path.join(self._settings['TEMPLATES_BASE_DIR'], '*.cfg')))
        for cfg_file_path in cfg_files:
            (template_name, _) = os.path.splitext(filepath_filename(cfg_file_path))
            template_name = template_name.lower()
            try:
                # Read config file
                cp = ConfigParser.RawConfigParser()
                cp.read(cfg_file_path)

                # Get image values and put them in an ImageAttrs object
                section = 'ImageAttributes'
                t_image_attrs = ImageAttrs(
                    template_name,
                    -1,
                    _config_get(cp, cp.getint, section, 'page'),
                    _config_get(cp, cp.get, section, 'format', True),
                    None,
                    _config_get(cp, cp.getint, section, 'width'),
                    _config_get(cp, cp.getint, section, 'height'),
                    _config_get(cp, cp.get, section, 'halign', True),
                    _config_get(cp, cp.get, section, 'valign', True),
                    _config_get(cp, cp.getfloat, section, 'angle'),
                    _config_get(cp, cp.get, section, 'flip'),
                    _config_get(cp, cp.getfloat, section, 'top'),
                    _config_get(cp, cp.getfloat, section, 'left'),
                    _config_get(cp, cp.getfloat, section, 'bottom'),
                    _config_get(cp, cp.getfloat, section, 'right'),
                    _config_get(cp, cp.getboolean, section, 'autocropfit'),
                    _config_get(cp, cp.getboolean, section, 'autosizefit'),
                    parse_colour(_config_get(cp, cp.get, section, 'fill')),
                    _config_get(cp, cp.getint, section, 'quality'),
                    _config_get(cp, cp.getint, section, 'sharpen'),
                    _config_get(cp, cp.get, section, 'overlay', False),
                    _config_get(cp, cp.getfloat, section, 'ovsize'),
                    _config_get(cp, cp.get, section, 'ovpos', True),
                    _config_get(cp, cp.getfloat, section, 'ovopacity'),
                    _config_get(cp, cp.get, section, 'icc', True),
                    _config_get(cp, cp.get, section, 'intent', True),
                    _config_get(cp, cp.getboolean, section, 'bpc'),
                    _config_get(cp, cp.get, section, 'colorspace', True),
                    _config_get(cp, cp.getboolean, section, 'strip'),
                    _config_get(cp, cp.getint, section, 'dpi'),
                    None
                )
                t_image_attrs.normalise_values()

                # Get misc options
                section = 'Miscellaneous'
                t_stats = _config_get(cp, cp.getboolean, section, 'stats')

                # Get handling options and create the TemplateAttrs object
                section = 'BrowserOptions'
                template_attrs = TemplateAttrs(
                    t_image_attrs,
                    _config_get(cp, cp.getint, section, 'expiry'),
                    _config_get(cp, cp.getboolean, section, 'attach'),
                    t_stats
                )

                # Validate and store
                template_attrs.validate()
                templates[template_name] = template_attrs

            except Exception as e:
                self._logger.error(
                    'Unable to load \'%s\' template configuration: %s' % (template_name, str(e))
                )

        self._logger.info('Loaded templates: ' + ', '.join(templates.keys()))
        return templates

    def _get_templates_mtime(self):
        """
        Returns the most recent modification time of the template files,
        or 0 if there are no files or if they cannot be queried.
        """
        mtime = 0
        try:
            cfg_files = glob.glob(unicode(os.path.join(self._settings['TEMPLATES_BASE_DIR'], '*.cfg')))
            for cfg_file_path in cfg_files:
                stinfo = os.stat(cfg_file_path)
                if stinfo.st_mtime > mtime:
                    mtime = stinfo.st_mtime
        except:
            pass
        return mtime

    @property
    def _icc_profiles(self):
        """
        A lazy-loaded cache of the ICC profiles, as a dictionary of form:
        { 'profile_name': ('CMYK', binary_data) }
        """
        if self.__icc_profiles is None:
            with self._icc_load_lock:
                if self.__icc_profiles is None:
                    self.__icc_profiles = self._load_icc_profiles()
        return self.__icc_profiles

    def _reload_icc_profiles(self):
        """
        Clears the internal ICC profiles cache.
        """
        with self._icc_load_lock:
            self.__icc_profiles = None

    def _load_icc_profiles(self):
        """
        Finds and returns the configured ICC profiles by searching for files
        in the ICC profiles directory. Returns a dictionary with keys of
        filename (lower case, without file extension) mapped to a tuple of
        (icc_colorspace, icc_data).
        """
        profiles = {}

        # Find *.icc and *.icm
        icc_files = glob.glob(unicode(os.path.join(self._settings['ICC_BASE_DIR'], '*.ic*')))
        for icc_file_path in icc_files:
            (icc_name, _) = os.path.splitext(filepath_filename(icc_file_path))
            icc_name = icc_name.lower()
            try:
                # Read ICC file
                with open(icc_file_path, 'rb') as f:
                    icc_data = f.read()
                    icc_colorspace = self._get_icc_colorspace(icc_data)
                    if icc_colorspace is None:
                        raise ValueError('No ICC file header found')
                    profiles[icc_name] = (icc_colorspace, icc_data)
            except Exception as e:
                self._logger.error('Unable to load \'%s\' ICC profile: %s' % (icc_name, str(e)))

        self._logger.info('Loaded ICC profiles: ' + ', '.join(profiles.keys()))
        return profiles
