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
# 27 Feb 15  Matt  #532 Auto-reload template files
# 22 Sep 15  Matt  v2 Templates are now loaded from the database
# 25 Aug 16  Matt  v2.2 Replace fall-back image parameters with a default template
# 26 Apr 18  Matt  v2.7.1/v3.0.1 Improve file uploads
#

# TODO Can we make base image detection more intelligent to work with cropped images?
#      Currently auto-pyramid for cropped images has no effect.

import copy
import glob
import os
import threading
import time

from . import exif

from .errors import DBDataError, DoesNotExistError, ImageError, ServerTooBusyError
from .filesystem_manager import (
    get_deduped_path, get_file_data, get_file_info,
    make_dirs, path_exists, put_file_data
)
from .filesystem_sync import auto_sync_file, set_image_properties
from .image_attrs import ImageAttrs
from .image_wrapper import ImageWrapper
from .imaging import (
    imaging_init, imaging_adjust_image, imaging_get_image_profile_data,
    imaging_get_image_dimensions, imaging_get_version_info
)
from .models import FolderPermission, Image, ImageHistory, Task
from .template_manager import ImageTemplateManager
from .util import default_value, get_file_extension
from .util import filepath_filename, validate_filename


class ImageManager(object):
    """
    Provides image management and image retrieval functions backed by a cache
    """
    IMAGE_ERROR_HEADER = '*ERROR*'
    DEFAULT_EXPIRY_SECS = 60 * 60 * 24 * 7
    DEFAULT_QUALITY_JPG = 80  # Err on the high quality side
    DEFAULT_QUALITY_PNG = 79  # 79 for complex images / 31 for simple images

    def __init__(self, data_manager, cache_manager, task_manager,
                 permissions_manager, settings, logger):
        self._data = data_manager
        self._cache = cache_manager
        self._tasks = task_manager
        self._permissions = permissions_manager
        self._settings = settings
        self._logger = logger
        self._templates = ImageTemplateManager(data_manager, logger)
        self.__icc_profiles = None
        self._icc_load_lock = threading.Lock()
        # Load imaging library
        imaging_init(
            settings['IMAGE_BACKEND'],
            settings['GHOSTSCRIPT_PATH'],
            settings['TEMP_DIR'],
            settings['PDF_BURST_DPI']
        )
        logger.info('Loaded imaging library: ' + imaging_get_version_info())

    def finalise_image_attrs(self, image_attrs):
        """
        For the given image attributes object, applies template values
        (or the default template), normalises the resulting object,
        and validates it to ensure it is ready for use.

        This function should usually be called before requesting an image
        so that global settings and standard parameter behaviours are enforced.

        Returns image_attrs, or raises a ValueError if the finalised image
        attributes fail validation.
        """
        original_quality = image_attrs.quality()
        # Validate first so that we check the template value before using it
        image_attrs.validate()
        # Apply template values, using override False so that web params take
        # precedence over template values. Not validating here saves a bit of time
        # but assumes that the template values are already valid. This should be
        # true as templates are validated elsewhere on load and before save.
        template_attrs = self.get_image_template(image_attrs)
        image_attrs.apply_dict(
            template_attrs.get_values_dict(), False, False, False
        )
        # Clear any redundant values so that we get consistent cache keys
        image_attrs.normalise_values()
        # v2.2 QIS v1 had a bit of logic that said "if you request an image with no
        # pixel changes and no explicit quality parameter, do not re-encode the unchanged
        # image with the default quality setting, just return the original image file."
        # The following few lines implement this in v2.
        # Just delete this bit if the old behaviour is unwanted (and fix the unit tests).
        if not original_quality and not image_attrs.template():
            prev_quality = image_attrs._quality        # Note: not the same as original_quality
            image_attrs._quality = None                # Wipe the quality setting, then
            if image_attrs.attributes_change_image():  # if sans-quality the image still changes,
                image_attrs._quality = prev_quality    # restore the quality setting
        return image_attrs

    def get_template_list(self):
        """
        Returns a list of available template information as
        {id, name, description, is_default} dictionaries.
        """
        return self._templates.get_template_list()

    def get_template_names(self, lowercase=False):
        """
        Returns a list of available template names - those names that are valid
        for calling get_template() or in the 'template' attribute of an ImageAttrs object.
        """
        return self._templates.get_template_names(lowercase)

    def get_template(self, template_name):
        """
        Returns the TemplateAttrs object for the template name (case insensitive),
        or raises a ValueError if the template name does not exist.
        """
        ta = self._templates.get_template(template_name)
        if ta is None:
            raise ValueError('Invalid template name: ' + template_name)
        return ta

    def get_default_template(self):
        """
        Returns the TemplateAttrs object that will provide default image processing
        settings if no other template is specified.
        """
        return self._templates.get_default_template()

    def get_icc_profile_names(self, colorspace=None):
        """
        Returns a lower case list of available ICC profile names - those names
        that are valid for use in the 'icc' attribute of an ImageAttrs object -
        optionally filtered by a colorspace (e.g. "RGB").
        """
        if colorspace is not None:
            return [
                k for k, v in self._icc_profiles.items() if v[0] == colorspace
            ]
        else:
            return list(self._icc_profiles.keys())

    def get_icc_profile_colorspaces(self):
        """
        Returns a list of the unique colorspace types of the available ICC
        profiles, e.g. ["RGB", "CMYK", "GRAY"]
        """
        return list(set(v[0] for v in self._icc_profiles.values()))

    def get_image_formats(self):
        """
        Returns a lower case list of supported image formats
        (as file extensions) e.g. ['jpg','png']
        """
        return list(self._settings['IMAGE_FORMATS'].keys())

    def put_image(self, current_user, file_wrapper,
                  dest_folder_path, dest_filename, overwrite_flag):
        """
        Stores an image file on the server and returns a tuple of its new
        ImageAttrs object and its new database object (detached).

        The file_wrapper must be a Werkzeug FileStorage object for the uploaded
        file, dest_folder_path is the folder path (relative to IMAGES_BASE_DIR)
        to store the file into, and dest_filename is the file name (without path)
        to save as. If dest_folder_path does not exist it will be created.

        If a file of the same name already exists at the destination path, the
        existing file will be replaced if overwrite_flag is True, an exception
        will be raised if overwrite_flag is False, or the value of dest_filename
        will be changed to a unique value if overwrite_flag is set to "rename".
        Always check the returned filename in the latter case to see whether
        the file was renamed.

        Any of the following exceptions may be raised:

        ValueError if a parameter is missing or has an invalid value.
        IOError if the file could not be created or written to.
        AlreadyExistsError if the destination file already exists and overwrite_flag is False.
        ImageError if the image is an unsupported format (determined from its filename).
        SecurityError if the current user does not have permission to upload to the destination
        path or if the destination path is outside IMAGES_BASE_DIR.
        """
        _overwrite_options = [True, False, "rename"]
        # Check mandatory params
        if file_wrapper is None:
            raise ValueError('No image file was provided')
        dest_folder_path = dest_folder_path.strip()
        dest_filename = dest_filename.strip()
        if not dest_filename:
            raise ValueError('No image file name was provided')
        if overwrite_flag not in _overwrite_options:
            raise ValueError('overwrite_flag must be one of ' + str(_overwrite_options))
        # File name must be "a.ext"
        validate_filename(dest_filename)
        # and the extension must be supported
        file_name_extension = get_file_extension(dest_filename)
        if file_name_extension not in self.get_image_formats():
            raise ImageError('The file is not a supported image format. ' +
                             'Supported types are: ' + ', '.join(self.get_image_formats()) + '.')

        # Require upload permission or file admin
        self._permissions.ensure_folder_permitted(
            dest_folder_path,
            FolderPermission.ACCESS_UPLOAD,
            current_user,
            folder_must_exist=False
        )

        # Now that we know permission is OK, create the destination folder if we need to
        if not path_exists(dest_folder_path, require_directory=True):
            self._logger.debug('Creating new folder \'' + dest_folder_path + '\'')
            make_dirs(dest_folder_path)

        # See if the image already exists
        final_path = os.path.join(dest_folder_path, dest_filename)
        file_exists = path_exists(final_path)

        # v2.7.1 If the image exists and overwrite_flag is "rename",
        # generate a new unique name for the image.
        if file_exists and overwrite_flag == "rename":
            final_path = get_deduped_path(final_path)
            overwrite_flag = False

        # Store the new file
        self._logger.debug(
            ('Replacing existing' if file_exists else 'Storing new') + ' file ' + final_path
        )
        put_file_data(file_wrapper, final_path, overwrite_flag)

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
                ImageHistory.ACTION_REPLACED if file_exists else ImageHistory.ACTION_CREATED,
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

        # Hmm, what client caching time for the original image?
        # Let's assume that the original is valid for as long as the default derivations of it
        expiry_secs = default_value(
            self._templates.get_default_template().expiry_secs(),
            ImageManager.DEFAULT_EXPIRY_SECS
        )

        # Return the requested image
        return ImageWrapper(
            file_data,
            ImageAttrs(image_attrs.filename(), image_attrs.database_id()),
            from_cache=False,
            last_modified=self.get_image_original_modified_time(image_attrs),
            client_expiry_seconds=expiry_secs
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
                time.sleep(0.1)
            # Try again
            ret_image_data = self._cache.get(cache_key)
            if ret_image_data is None:
                self._logger.warning('Timed out waiting for ' + str(image_attrs))
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
                    self._auto_pyramid_image(
                        file_data, get_file_extension(image_attrs.filename()), image_attrs
                    )
                    # Set the original image from disk as the base image
                    file_attrs = ImageAttrs(image_attrs.filename(), image_attrs.database_id())
                    base_image = ImageWrapper(file_data, file_attrs)
                else:
                    if debug_mode:
                        self._logger.debug('Base image found: ' + str(base_image.attrs()))
                    # If the base image found is the full size,
                    # see whether to auto-pyramid the original image for the future
                    if not base_image.attrs().width() and not base_image.attrs().height():
                        self._auto_pyramid_image(
                            base_image.data(), base_image.attrs().format(), image_attrs
                        )

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
                    ret_image_data = ImageManager.IMAGE_ERROR_HEADER + str(e)

                # Add it to cache for next time
                if cache_result:
                    if self._cache_image(ret_image_data, image_attrs):
                        if debug_mode:
                            self._logger.debug('Added new image to cache: ' + str(image_attrs))
                    else:
                        self._logger.warning('Failed to add image to cache: ' + str(image_attrs))
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
        if (isinstance(ret_image_data, str) and
            ret_image_data.startswith(ImageManager.IMAGE_ERROR_HEADER)
        ):
            msg = ret_image_data[len(ImageManager.IMAGE_ERROR_HEADER):]
            raise ImageError(msg)

        # v1.17 Get/set the image's last modification time
        modified_time = self.get_image_modified_time(image_attrs)
        if modified_time == 0:
            modified_time = time.time()
            self._cache_image_metadata(image_attrs, modified_time)

        # Get default handling options from requested template or default template
        template_attrs = self.get_image_template(image_attrs)
        expiry_secs = default_value(template_attrs.expiry_secs(), ImageManager.DEFAULT_EXPIRY_SECS)
        attachment = default_value(template_attrs.attachment(), False)
        do_stats = default_value(template_attrs.record_stats(), True)

        # Return the requested image
        return ImageWrapper(
            ret_image_data,
            image_attrs,
            ret_from_cache,
            modified_time,
            expiry_secs,
            attachment,
            do_stats
        )

    def get_image_template(self, image_attrs):
        """
        Returns the template (as a TemplateAttrs object) that will be used to
        generate the image described by image_attrs. As of v2.2 this is the
        system default template if image_attrs does not specify a template.
        """
        ia_t_name = image_attrs.template()
        return (self._templates.get_template(ia_t_name) if ia_t_name else
                self._templates.get_default_template())

    def get_image_modified_time(self, image_attrs):
        """
        Returns the last known time the image (as described by image_attrs)
        was modified or created, as UTC seconds since the epoch.

        Or returns 0 if this information is not in cache, because the image
        has not been generated, or because the cache entry for it has expired.

        Note that even if the last modification time is known, the associated
        image itself may not still be in cache (or may never have been cached).
        """
        image_metadata = self._cache.raw_get(image_attrs.get_metadata_cache_key())
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
        Reads the image dimensions and embedded image profile properties
        (EXIF, IPTC, TIFF, etc) from an image file. The original image file is
        always read, because cached versions may have had their profiles stripped.

        See get_image_data_properties() for the return values.

        This function additionally raises a SecurityError if the file path
        requested attempts to read outside of the images directory.
        """
        file_type = get_file_extension(filepath)
        file_data = get_file_data(filepath)
        if file_data is None:
            return {}

        props = self.get_image_data_properties(file_data, file_type, return_unknown)
        if not props:
            self._logger.error('Failed to read image properties for %s' % filepath)
        return props

    def get_image_data_properties(self, image_data, image_format=None, return_unknown=True):
        """
        Reads the image dimensions and embedded image profile properties
        (EXIF, IPTC, TIFF, etc) from raw image data.

        On success, a dictionary is returned containing the image width and height,
        and entries for the embedded data profile names, each containing a list of
        property names and values. For example:
        { 'width': 3000,
          'height': 2000,
          'TIFF': [ ('Maker', 'Canon'), ('Model', '300D') ],
          'EXIF': [ ('Flash', 'Off'), ('ExposureMode', 'Auto') ]
        }
        where both the profile names and the properties will vary from image to image.

        By default, unrecognised properties are returned with their values in a raw
        format (e.g. code numbers rather than readable text). If return_unknown is
        False, unrecognised property names will not be returned at all.

        An empty dictionary is returned if the file could not be read or there
        was an error reading the image.
        """
        try:
            (width, height) = imaging_get_image_dimensions(image_data, image_format)
            file_properties = imaging_get_image_profile_data(image_data, image_format)
        except Exception as e:
            self._logger.error('Error reading image properties: %s' % str(e))
            return {}

        # Convert to the promised return structure
        props = exif.raw_list_to_dict(file_properties, False, return_unknown)
        props.update({'width': width, 'height': height})
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
        file_type = get_file_extension(filepath)
        file_data = get_file_data(filepath)
        return (
            (0, 0) if file_data is None else
            ImageManager.get_image_data_dimensions(file_data, file_type)
        )

    @staticmethod
    def get_image_data_dimensions(image_data, image_format=None):
        """
        Reads the image dimensions from raw image data, without decoding the
        image if possible. Returns a tuple containing the image width and height,
        or (0, 0) if the image type is unsupported or could not be read.
        """
        try:
            return imaging_get_image_dimensions(image_data, image_format)
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
            self._logger.debug('Resetting image ' + str(image_attrs))

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

    def reset_templates(self):
        """
        Instructs the template system to refresh its data from the database.
        """
        self._templates.reset()

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
            }
        )
        if not ok:
            self._logger.warning(
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
            self._logger.warning('Cache is not connected, not generating tile base')
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
            self._logger.warning(
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

    def _auto_pyramid_image(self, original_data, original_type, image_attrs):
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
        (w, h) = imaging_get_image_dimensions(
            original_data,
            original_type
        )
        if (w * h) < self._settings["AUTO_PYRAMID_THRESHOLD"]:
            self._logger.debug(
                'Image below threshold, will not pyramid image %s' % image_attrs.filename()
            )
            return
        # Requires the cache
        if not self._cache.connected():
            self._logger.warning(
                'Cache is not connected, cannot pyramid image %s' % image_attrs.filename()
            )
            return
        # Attempt to ensure we don't force useful stuff out of small caches
        if float(len(original_data)) / float(self._cache.capacity()) > 0.05:
            self._logger.warning(
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
        # See if the requested image attributes require altering the base image
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
            cquality = default_value(new_image_attrs.quality(), 0)
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

            # Mandatory image attributes: a couple of things must have a value,
            # so we need to set them here if they're not already set. These are
            # special cases - note that setting them here means that these values
            # do not go into the cache key! This is only OK for things that do
            # not change the actual image pixels.
            #
            # compression value must always be set to something
            if cquality == 0:
                cquality = (
                    ImageManager.DEFAULT_QUALITY_PNG if iformat == 'png'
                    else ImageManager.DEFAULT_QUALITY_JPG
                )
            # when converting from PDF we must set a DPI
            if dpi == 0 and base_image_attrs.src_is_pdf():
                dpi = self._settings['PDF_BURST_DPI']

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

            # Finally, generate a new image from base_image_data
            try:
                return imaging_adjust_image(
                    base_image_data,
                    base_image_attrs.format(),
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

    def _get_icc_colorspace(self, icc_data):
        """
        Returns the colorspace header field of an ICC profile
        E.g. "RGB", "CMYK", "GRAY", "XYZ", "LAB", "YCbr",
             or None if the ICC data is invalid.
        """
        if icc_data is not None and len(icc_data) > 128:
            # The colorspace flag is 4 bytes from position 16 in the 128 byte header
            # See http://www.color.org/specification/ICC1v43_2010-12.pdf
            cspace = icc_data[16:20].strip().decode('ascii')
            if cspace.lower() in ('rgb', 'cmyk', 'gray', 'xyz', 'lab'):
                cspace = cspace.upper()
            return cspace
        return None

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
        (icc_colorspace<string>, icc_data<bytes>).
        """
        profiles = {}

        # Find *.icc and *.icm
        icc_files = glob.glob(os.path.join(self._settings['ICC_BASE_DIR'], '*.ic*'))
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
