#
# Quru Image Server
#
# Document:      precache.py
# Date started:  09 May 2011
# By:            Matt Fozard
# Purpose:       Pre-caches templated images by walking a directory tree
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
# 26 Jan 15  Matt  Stop when cache is 80% full, memcache never reaches 100%
#                  due to pre-sized pre-allocated cache slots
#
# Notes:
#
# Quru Image Server pre-cache utility.
#
# Walks a directory tree and generates cached images as defined by one or more
# image templates. The starting directory must be the same as, or within,
# the IMAGES_BASE_DIR directory.
#
# Images that are already cached are not re-generated.
#
# Usage: su <qis user>
#        (optional) export QIS_SETTINGS=<path to your settings.py>
#        python precache.py [-silent] start_dir file_spec(s) template_name(s)
#

import fnmatch
import os
import site
import signal
import sys

RETURN_OK = 0
RETURN_MISSING_PARAMS = 1
RETURN_BAD_PARAMS = 2
RETURN_CACHE_ERROR = 3

silent = False


class CacheFullException(Exception):
    """
    Raised when the image server cache is full.
    """
    pass


class PreCacheStats():
    """
    Pre-caching statistics handler.
    """
    def __init__(self):
        self.total_dir_count = 0
        self.total_file_count = 0
        self.dir_skipped_count = 0
        self.images_created_count = 0
        self.images_error_count = 0
        self.images_already_cached_count = 0

    def inc_total_dir_count(self):
        self.total_dir_count = self.total_dir_count + 1

    def inc_total_file_count(self):
        self.total_file_count = self.total_file_count + 1

    def inc_dir_skipped_count(self):
        self.dir_skipped_count = self.dir_skipped_count + 1

    def inc_images_created_count(self):
        self.images_created_count = self.images_created_count + 1

    def inc_images_error_count(self):
        self.images_error_count = self.images_error_count + 1

    def inc_images_already_cached_count(self):
        self.images_already_cached_count = self.images_already_cached_count + 1


def precache_images(start_dir, file_specs, templates):
    """
    Performs the main pre-caching function as described by the file header.
    """
    from imageserver.flask_app import app
    from imageserver.filesystem_sync import auto_sync_existing_file
    from imageserver.image_attrs import ImageAttrs
    from imageserver.util import add_sep

    # Disable logging to prevent app startup and image errors going to main log
    # app.log.set_enabled(False)

    # Validate params
    rc = validate_params(start_dir, file_specs, templates)
    if (rc != RETURN_OK):
        return rc

    # Get base path with trailing /
    images_base_dir = add_sep(os.path.abspath(app.config['IMAGES_BASE_DIR']))

    # Init stats and stop conditions
    stats = PreCacheStats()
    last_cache_pct = 0
    cache_full = False
    keyboard_interrupt = False

    # Get directory walking errors
    def walk_err(os_error):
        stats.inc_dir_skipped_count()

    # Walk directory tree
    try:
        for cur_dir, sub_dirs, files in os.walk(
            start_dir, onerror=walk_err, followlinks=True
        ):
            log(cur_dir)
            stats.inc_total_dir_count()
            # Remove files and directories beginning with '.'
            for d in sub_dirs:
                if d.startswith('.'):
                    sub_dirs.remove(d)
            for f in files:
                if f.startswith('.'):
                    files.remove(f)
            # Get relative path from IMAGES_BASE_DIR/
            if not cur_dir.startswith(images_base_dir):
                log('ERROR: Cannot calculate relative image path from ' + str(cur_dir))
                stats.inc_dir_skipped_count()
            else:
                relative_dir = cur_dir[len(images_base_dir):]
                # Apply file specs
                for file_spec in file_specs:
                    file_matches = fnmatch.filter(files, file_spec)
                    for file_name in file_matches:
                        # Check whether the cache is full (or now self-emptying) once in a while
                        if stats.total_file_count % 10 == 0:
                            cache_pct = app.cache_engine.size_percent()
                            log('\tCache level %d%%' % cache_pct)
                            if (cache_pct < last_cache_pct) or (cache_pct >= 80):
                                raise CacheFullException()
                            else:
                                last_cache_pct = cache_pct
                        # Process matched file
                        stats.inc_total_file_count()
                        for template in templates:
                            try:
                                log('\tProcessing %s with template %s' % (file_name, template))
                                image_path = os.path.join(relative_dir, file_name)
                                db_image = auto_sync_existing_file(
                                    image_path, app.data_engine, app.task_engine
                                )
                                image_attrs = ImageAttrs(
                                    db_image.src, db_image.id, template=template
                                )
                                app.image_engine.finalise_image_attrs(image_attrs)
                                gen_image = app.image_engine.get_image(image_attrs)
                                if gen_image.is_from_cache():
                                    log('\tImage already in cache')
                                    stats.inc_images_already_cached_count()
                                else:
                                    log('\tGenerated %s image, %d bytes' % (
                                        gen_image.attrs().format(), len(gen_image.data())
                                    ))
                                    stats.inc_images_created_count()
                            except KeyboardInterrupt as kbe:
                                raise kbe
                            except Exception as e:
                                log('ERROR: ' + str(e))
                                stats.inc_images_error_count()
    except CacheFullException:
        cache_full = True
    except KeyboardInterrupt:
        keyboard_interrupt = True

    # Show stop reason and stats
    if keyboard_interrupt:
        log('---\nInterrupted by user.\n---')
    elif cache_full:
        log('---\nCache is full.\n---')
    else:
        log('---\nNo more files.\n---')

    log('%d matching file(s) found in %d directories.' % (
        stats.total_file_count, stats.total_dir_count
    ))
    log('%d image(s) were generated and cached.' % stats.images_created_count)
    log('%d image(s) were already in cache.' % stats.images_already_cached_count)
    log('%d image(s) skipped due to error.' % stats.images_error_count)
    log('%d directories skipped due to error.' % stats.dir_skipped_count)
    log('Cache is now %d%% full.' % app.cache_engine.size_percent())
    return RETURN_OK


def validate_params(start_dir, file_specs, templates):
    """
    Validates the command line parameters, returning 0 on success or a code
    number that can be used as the application return value on error.
    """
    from imageserver.flask_app import app

    # Validate start_dir
    start_dir_abs = os.path.abspath(start_dir)
    images_dir_abs = os.path.abspath(app.config['IMAGES_BASE_DIR'])
    if not os.path.exists(start_dir_abs):
        error('Start directory does not exist: ' + start_dir_abs)
        return RETURN_BAD_PARAMS
    if not start_dir_abs.startswith(images_dir_abs):
        error(
            'Start directory \'%s\' must lie within the image server\'s repository at \'%s\''
            % (start_dir_abs, images_dir_abs)
        )
        return RETURN_BAD_PARAMS

    # Validate template names
    available_templates = app.image_engine.get_template_names(lowercase=True)
    for t in templates:
        if t not in available_templates:
            error(
                'Template does not exist: %s. Available templates: %s'
                % (t, ', '.join(available_templates))
            )
            return RETURN_BAD_PARAMS

    # Make sure the cache is connected
    if not app.cache_engine.connected():
        error('Cache server is not connected')
        return RETURN_CACHE_ERROR

    return RETURN_OK


def log(astr):
    """
    Outputs an informational message if silent mode is disabled.
    """
    if not silent:
        print(astr)


def error(astr):
    """
    Outputs an error message.
    """
    print('ERROR: ' + astr)


def show_usage():
    """
    Outputs usage information.
    """
    print('\nRecursively searches a directory tree for images to pre-process and store')
    print('in the image server\'s cache. Multiple file types and template names can be')
    print('specified by separating each with a comma (without spaces). Target images that')
    print('are already in the cache are not re-generated. Any file or directory beginning')
    print('with a \'.\' is ignored. Note that by its nature, this utility will cause high')
    print('CPU usage for as long as it is running. The utility will stop either when there')
    print('are no more files to process, or when the cache is 80% full.')
    print('\nUsage: su <qis user>')
    print('       python precache.py [-silent] start_dir file_spec(s) template(s)')
    print('Where:')
    print('       -silent   (optional) suppresses output to the console.')
    print('       start_dir is the directory to search recursively.')
    print('       file_spec is one or more image file names to match.')
    print('       template  is one or more template names defined in the image server that')
    print('                 describe how the images found are to be processed.')
    print('\nExample: python precache.py /home/images/ *.jpg,*.tif MediumJpeg,SmallJpeg')
    print('\nWhen specifying multiple templates to generate different sizes of image,')
    print('as in the example, order the templates with the largest image size first')
    print('to speed up processing (the second template can use the output from the first).')


def get_parameters():
    """
    Returns a tuple of 3 items for the parameters provided on the command line.
    These are: the start directory as a string, the file specs as a list, and
    the template names as a list. Either a value of None or an empty list is
    returned if the command line parameter was missing.
    """
    start_dir = None
    file_specs = []
    templates = []
    for arg in sys.argv:
        if arg == __file__:
            pass
        elif arg == '-silent':
            global silent
            silent = True
        elif start_dir is None:
            start_dir = arg
        elif len(file_specs) == 0:
            file_specs = arg.split(',')
        else:
            templates = arg.lower().split(',')

    return start_dir, file_specs, templates


if __name__ == '__main__':
    try:
        pver = sys.version_info
        # Pythonpath - escape sub-folder and add custom libs
        site.addsitedir('../..')
        site.addsitedir('../../../lib/python%d.%d/site-packages' % (pver.major, pver.minor))
        # Get params
        start_dir, file_specs, templates = get_parameters()
        if not start_dir or not file_specs or not templates:
            show_usage()
            exit(RETURN_MISSING_PARAMS)
        else:
            rc = precache_images(start_dir, file_specs, templates)
            exit(rc)

    except Exception as e:
        print('Utility exited with error:\n' + str(e))
        print('Ensure you are using the correct user account, ' \
              'and (optionally) set the QIS_SETTINGS environment variable.\n')
        raise
    finally:
        # Also stop any background processes we started
        signal.signal(signal.SIGTERM, lambda a, b: None)
        os.killpg(os.getpgid(0), signal.SIGTERM)
