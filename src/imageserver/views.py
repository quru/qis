#
# Quru Image Server
#
# Document:      views.py
# Date started:  04 Apr 2011
# By:            Matt Fozard
# Purpose:       Raw image handling URLs and views
# Requires:      Flask
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
# 25 Nov 14  Matt  v1.17 Fix ETags and implement HTTP 304
# 04 Feb 15  Matt  Raise HTTP 415 for invalid images instead of HTTP 500
# 25 Mar 15  Matt  v1.27 Raise HTTP 503 for unresponsive image requests
#

import time

import flask
from flask import make_response, request
import werkzeug.exceptions as httpexc

from errors import DBError, DoesNotExistError, ImageError, SecurityError, ServerTooBusyError
from filesystem_manager import path_exists
from filesystem_sync import on_image_db_create_anon_history
from flask_app import app
from flask_app import logger
from flask_app import data_engine, image_engine, permissions_engine, stats_engine
from image_attrs import ImageAttrs
from models import FolderPermission
from session_manager import get_session_user, logged_in
from util import filepath_parent, invoke_http_async, validate_string
from util import parse_boolean, parse_colour, parse_float, parse_int, parse_tile_spec
from util import unicode_to_utf8, etag
from views_util import log_security_error


# eRez compatibility URLs for raw image serving
@app.route('/erez/erez', methods=['GET'])
def erez_compat(): return image()
@app.route('/erez1/erez', methods=['GET'])
def erez1_compat(): return image()
@app.route('/erez2/erez', methods=['GET'])
def erez2_compat(): return image()
@app.route('/erez3/erez', methods=['GET'])
def erez3_compat(): return image()
@app.route('/erez4/erez', methods=['GET'])
def erez4_compat(): return image()
@app.route('/erez5/erez', methods=['GET'])
def erez5_compat(): return image()


# Raw image serving
@app.route('/image', methods=['GET'])
def image():
    logger.debug(request.method + ' ' + request.url)
    try:
        args = request.args
        # Get URL parameters for the image
        src         = args.get('src', '')
        page        = args.get('page', None)
        iformat     = args.get('format', None)
        template    = args.get('tmp', None)
        width       = args.get('width', None)
        height      = args.get('height', None)
        halign      = args.get('halign', None)
        valign      = args.get('valign', None)
        autosizefit = args.get('autosizefit', None)
        rotation    = args.get('angle', None)
        flip        = args.get('flip', None)
        top         = args.get('top', None)
        left        = args.get('left', None)
        bottom      = args.get('bottom', None)
        right       = args.get('right', None)
        autocropfit = args.get('autocropfit', None)
        fill        = args.get('fill', None)
        quality     = args.get('quality', None)
        sharpen     = args.get('sharpen', None)
        ov_src      = args.get('overlay', None)
        ov_size     = args.get('ovsize', None)
        ov_opacity  = args.get('ovopacity', None)
        ov_pos      = args.get('ovpos', None)
        icc_profile = args.get('icc', None)
        icc_intent  = args.get('intent', None)
        icc_bpc     = args.get('bpc', None)
        colorspace  = args.get('colorspace', None)
        strip       = args.get('strip', None)
        dpi         = args.get('dpi', None)
        tile        = args.get('tile', None)
        # Get URL parameters for handling options
        attach      = args.get('attach', None)
        xref        = args.get('xref', None)
        stats       = args.get('stats', None)
        cache       = args.get('cache', '1')    # Admin/internal use
        recache     = args.get('recache', None) # Admin/internal use

        # eRez compatibility mode
        src = erez_params_compat(src)

        # Tweak strings as necessary and convert non-string parameters
        # to the correct data types
        try:
            # Image options
            if page is not None:
                page = parse_int(page)
            if iformat is not None:
                iformat = iformat.lower()
            if template is not None:
                template = template.lower()
            if width is not None:
                width = parse_int(width)
            if height is not None:
                height = parse_int(height)
            if halign is not None:
                halign = halign.lower()
            if valign is not None:
                valign = valign.lower()
            if autosizefit is not None:
                autosizefit = parse_boolean(autosizefit)
            if rotation is not None:
                rotation = parse_float(rotation)
            if flip is not None:
                flip = flip.lower()
            if top is not None:
                top = parse_float(top)
            if left is not None:
                left = parse_float(left)
            if bottom is not None:
                bottom = parse_float(bottom)
            if right is not None:
                right = parse_float(right)
            if autocropfit is not None:
                autocropfit = parse_boolean(autocropfit)
            if fill is not None:
                fill = parse_colour(fill)
            if quality is not None:
                quality = parse_int(quality)
            if sharpen is not None:
                sharpen = parse_int(sharpen)
            if ov_size is not None:
                ov_size = parse_float(ov_size)
            if ov_pos is not None:
                ov_pos = ov_pos.lower()
            if ov_opacity is not None:
                ov_opacity = parse_float(ov_opacity)
            if icc_profile is not None:
                icc_profile = icc_profile.lower()
            if icc_intent is not None:
                icc_intent = icc_intent.lower()
            if icc_bpc is not None:
                icc_bpc = parse_boolean(icc_bpc)
            if colorspace is not None:
                colorspace = colorspace.lower()
            if strip is not None:
                strip = parse_boolean(strip)
            if dpi is not None:
                dpi = parse_int(dpi)
            if tile is not None:
                tile = parse_tile_spec(tile)
            # Handling options
            if attach is not None:
                attach = parse_boolean(attach)
            if xref is not None:
                validate_string(xref, 0, 1024)
            if cache is not None:
                cache = parse_boolean(cache)
            if recache is not None:
                recache = parse_boolean(recache)
            if stats is not None:
                stats = parse_boolean(stats)
        except (ValueError, TypeError) as e:
            raise httpexc.BadRequest(unicode(e))

        # Package and validate the parameters
        try:
            # #2694 Enforce public image limits - perform easy parameter checks
            if not logged_in():
                width, height, autosizefit = _public_image_limits_pre_image_checks(
                    width, height, autosizefit, tile, template
                )
            # Store and normalise all the parameters
            image_attrs = ImageAttrs(src, -1, page, iformat, template,
                                     width, height, halign, valign,
                                     rotation, flip,
                                     top, left, bottom, right, autocropfit,
                                     autosizefit, fill, quality, sharpen,
                                     ov_src, ov_size, ov_pos, ov_opacity,
                                     icc_profile, icc_intent, icc_bpc,
                                     colorspace, strip, dpi, tile)
            image_engine.finalise_image_attrs(image_attrs)
        except ValueError as e:
            raise httpexc.BadRequest(unicode(e))

        # Get/create the database ID (from cache, validating path on create)
        image_id = data_engine.get_or_create_image_id(
            image_attrs.filename(),
            return_deleted=False,
            on_create=on_image_db_create_anon_history
        )
        if (image_id == 0):
            raise DoesNotExistError()  # Deleted
        elif (image_id < 0):
            raise DBError('Failed to add image to database')
        image_attrs.set_database_id(image_id)

        # Require view permission or file admin
        permissions_engine.ensure_folder_permitted(
            image_attrs.folder_path(),
            FolderPermission.ACCESS_VIEW,
            get_session_user()
        )
        # Ditto for overlays
        if ov_src:
            permissions_engine.ensure_folder_permitted(
                filepath_parent(ov_src),
                FolderPermission.ACCESS_VIEW,
                get_session_user()
            )

        # v1.17 If this is a conditional request with an ETag, see if we can just return a 304
        if 'If-None-Match' in request.headers and not recache:
            etag_valid, modified_time = _etag_is_valid(
                image_attrs,
                request.headers['If-None-Match'],
                False
            )
            if etag_valid:
                # Success HTTP 304
                return make_304_response(image_attrs, False, modified_time)

        # Get the requested image data
        image_wrapper = image_engine.get_image(
            image_attrs,
            'refresh' if recache else cache
        )
        if (image_wrapper is None):
            raise DoesNotExistError()

        # #2694 Enforce public image limits - check the dimensions
        #       of images that passed the initial parameter checks
        if not logged_in():
            try:
                _public_image_limits_post_image_checks(
                    image_attrs.width(),
                    image_attrs.height(),
                    image_attrs.template(),
                    image_wrapper.data()
                )
            except ValueError as e:
                raise httpexc.BadRequest(unicode(e))  # As for the pre-check

        # Success HTTP 200
        return make_image_response(image_wrapper, False, stats, attach, xref)
    except httpexc.HTTPException:
        # Pass through HTTP 4xx and 5xx
        raise
    except ServerTooBusyError:
        logger.warn(u'503 Too busy for ' + request.url)
        raise httpexc.ServiceUnavailable()
    except ImageError as e:
        logger.warn(u'415 Invalid image file \'' + src + '\' : ' + unicode(e))
        raise httpexc.UnsupportedMediaType(unicode(e))
    except SecurityError as e:
        if app.config['DEBUG']:
            raise
        log_security_error(e, request)
        raise httpexc.Forbidden()
    except DoesNotExistError as e:
        # First time around the ID will be set. Next time around it
        # won't but we should check whether the disk file now exists.
        if image_attrs.database_id() > 0 or path_exists(image_attrs.filename(), require_file=True):
            image_engine.reset_image(image_attrs)
        logger.warn(u'404 Not found: ' + unicode(e))
        raise httpexc.NotFound(unicode(e))
    except Exception as e:
        if app.config['DEBUG']:
            raise
        logger.error(u'500 Error for ' + request.url + '\n' + unicode(e))
        raise httpexc.InternalServerError(unicode(e))


# Raw image serving - return the original unaltered image
@app.route('/original', methods=['GET'])
def original():
    logger.debug('GET ' + request.url)
    try:
        # Get URL parameters for the image
        src = request.args.get('src', '')
        # Get URL parameters for handling options
        attach  = request.args.get('attach', None)
        xref    = request.args.get('xref', None)
        stats   = request.args.get('stats', None)

        # Validate the parameters
        try:
            if attach is not None:
                attach = parse_boolean(attach)
            if xref is not None:
                validate_string(xref, 0, 1024)
            if stats is not None:
                stats = parse_boolean(stats)

            image_attrs = ImageAttrs(src)
            image_attrs.validate()
        except ValueError as e:
            raise httpexc.BadRequest(unicode(e))

        # Get/create the database ID (from cache, validating path on create)
        image_id = data_engine.get_or_create_image_id(
            image_attrs.filename(),
            return_deleted=False,
            on_create=on_image_db_create_anon_history
        )
        if (image_id == 0):
            raise DoesNotExistError()  # Deleted
        elif (image_id < 0):
            raise DBError('Failed to add image to database')
        image_attrs.set_database_id(image_id)

        # Require download permission or file admin
        permissions_engine.ensure_folder_permitted(
            image_attrs.folder_path(),
            FolderPermission.ACCESS_DOWNLOAD,
            get_session_user()
        )

        # v1.17 If this is a conditional request with an ETag, see if we can just return a 304
        if 'If-None-Match' in request.headers:
            etag_valid, modified_time = _etag_is_valid(
                image_attrs,
                request.headers['If-None-Match'],
                True
            )
            if etag_valid:
                # Success HTTP 304
                return make_304_response(image_attrs, True, modified_time)

        # Read the image file
        image_wrapper = image_engine.get_image_original(
            image_attrs
        )
        if (image_wrapper is None):
            raise DoesNotExistError()

        # Success HTTP 200
        return make_image_response(image_wrapper, True, stats, attach, xref)
    except httpexc.HTTPException:
        # Pass through HTTP 4xx and 5xx
        raise
    except ServerTooBusyError:
        logger.warn(u'503 Too busy for ' + request.url)
        raise httpexc.ServiceUnavailable()
    except ImageError as e:
        logger.warn(u'415 Invalid image file \'' + src + '\' : ' + unicode(e))
        raise httpexc.UnsupportedMediaType(unicode(e))
    except SecurityError as e:
        if app.config['DEBUG']:
            raise
        log_security_error(e, request)
        raise httpexc.Forbidden()
    except DoesNotExistError as e:
        # First time around the ID will be set. Next time around it
        # won't but we should check whether the disk file now exists.
        if image_attrs.database_id() > 0 or path_exists(image_attrs.filename(), require_file=True):
            image_engine.reset_image(image_attrs)
        logger.warn(u'404 Not found: ' + src)
        raise httpexc.NotFound(src)
    except Exception as e:
        if app.config['DEBUG']:
            raise
        logger.error(u'500 Error for ' + request.url + '\n' + unicode(e))
        raise httpexc.InternalServerError(unicode(e))


def erez_params_compat(src):
    """
    Performs adjustments to URL parameters to provide compatibility with eRez
    """
    if src.endswith('.tif') and src[-10:-4].rfind('.') != -1:
        src = src[0:-4]
    elif src.endswith('.tiff') and src[-11:-5].rfind('.') != -1:
        src = src[0:-5]
    return src


def handle_image_xref(xref):
    """
    Invokes the configured 3rd party URL (if any) for the given tracking reference.
    """
    xurl = app.config['XREF_TRACKING_URL']
    if xref and xurl:
        if xurl.startswith('http'):
            invoke_http_async(
                xurl + xref,
                log_success_fn=logger.debug if app.config['DEBUG'] else None,
                log_fail_fn=logger.error
            )
        else:
            logger.warn('XREF_TRACKING_URL must begin with http or https')


def make_image_response(image_wrapper, is_original, stats=None, as_attachment=None, xref=None):
    """
    Returns a Flask response object for the given image and response options,
    handles the tracking ID if there is one, and writes view statistics for the
    image.

    image_wrapper - An ImageWrapper containing the image data to return.
    is_original - Whether to count this response as a "download original" function.
                  If True, logs download statistics instead of a view.
    stats - Optional override for whether to enable or disable image statistics.
            Uses the setting in image_wrapper when None.
    as_attachment - Optional override for whether to provide the
                    Content-Disposition HTTP header (with filename).
                    Uses the setting in image_wrapper when None.
    xref - Optional external URL to call.
    """
    image_attrs = image_wrapper.attrs()

    # Process xref if there is one
    if xref:
        handle_image_xref(xref)

    # Create the HTTP response
    response = make_response(image_wrapper.data())
    response.mimetype = image_attrs.mime_type()

    # Set the browser caching headers
    _add_http_caching_headers(
        response,
        image_attrs,
        image_wrapper.last_modified_time(),
        image_wrapper.client_expiry_time()
    )

    # Set custom cache info header
    response.headers['X-From-Cache'] = str(image_wrapper.is_from_cache())

    # URL attachment param overrides what the returned object wants
    attach = as_attachment if (as_attachment is not None) else \
             image_wrapper.is_attachment()
    if is_original or attach:
        fname = image_attrs.filename(with_path=False, replace_format=True)
        fname = unicode_to_utf8(fname)
        cd_type = 'attachment' if attach else 'inline'
        response.headers['Content-Disposition'] = cd_type + '; filename="' + fname + '"'

    if app.config['DEBUG']:
        logger.debug(
            'Sending ' + str(len(image_wrapper.data())) + ' bytes for ' + str(image_attrs)
        )

    _log_stats(
        image_attrs.database_id(),
        len(image_wrapper.data()),
        is_original,
        image_wrapper.is_from_cache(),
        image_wrapper.record_stats() if stats is None else stats
    )
    return response


def make_304_response(image_attrs, is_original, last_modified_time):
    """
    Returns a HTTP 304 "Not Modified" Flask response object for the given image.

    image_attrs - An ImageAttrs containing the image specification.
    is_original - Whether to count this response as a "download original" function.
                  If True, logs download statistics instead of a view.
    last_modified_time - The image's last modification time as number of
                         seconds since the epoch.
    """
    # Create a blank response with no content
    response = flask.Response(status=304)

    # We have to set the same caching headers again
    # http://stackoverflow.com/a/4393499/1671320
    _add_http_caching_headers(
        response,
        image_attrs,
        last_modified_time,
        image_engine._get_expiry_secs(image_attrs)
    )

    if app.config['DEBUG']:
        logger.debug(
            'Sending 304 Not Modified for ' + str(image_attrs)
        )

    _log_stats(image_attrs.database_id(), 0, is_original, False)
    return response


def _add_http_caching_headers(response, image_attrs, last_modified_time, expiry_seconds):
    """
    Sets the standard client-side cache control headers expected for an HTTP
    200 or 304 response. The last modified time should be given as number of
    seconds since the epoch. The expiry time is as described for ImageWrapper.
    """
    # This (and others below) auto-converted to correct format by Werkzeug
    response.date = time.time()

    if expiry_seconds != 0:
        if expiry_seconds > 0:
            response.cache_control.public = True
            response.cache_control.max_age = expiry_seconds
            response.expires = int(time.time() + expiry_seconds)
        else:
            response.cache_control.public = True
            response.cache_control.no_cache = True
            response.expires = 0

    if expiry_seconds >= 0:
        response.headers['ETag'] = etag(
            str(last_modified_time),
            image_attrs.get_cache_key()
        )


def _etag_is_valid(image_attrs, check_etag, is_original):
    """
    Returns a tuple of (True, last_modified_time) if the current ETag for the
    image described by image_attrs matches the given ETag.
    Returns (False, new_modified_time) if the current ETag value is different.
    """
    modified_time = image_engine.get_image_original_modified_time(image_attrs) \
                    if is_original else \
                    image_engine.get_image_modified_time(image_attrs)

    if modified_time == 0:
        # Return False to re-generate the image and re-store the modified time
        return (False, 0)

    current_etag = etag(
        str(modified_time),
        image_attrs.get_cache_key()
    )
    return ((current_etag == check_etag), modified_time)


def _public_image_limits_pre_image_checks(req_width, req_height, req_autosizefit,
                                          req_tile, req_template):
    """
    To be called when no one is logged in, enforces the image dimension limits
    defined by the PUBLIC_MAX_IMAGE_WIDTH and PUBLIC_MAX_IMAGE_HEIGHT settings.
    If a template is specified, the template dimensions take precedence.
    Or if no dimensions were requested, returns default value(s) for them.

    Returns a tuple of replacement (width, height, autosizefit) values that
    should be used for the rest of the image request.

    Raises a ValueError if the requested image dimensions would exceed the
    defined limits.
    """
    limit_w = app.config['PUBLIC_MAX_IMAGE_WIDTH'] or 0
    limit_h = app.config['PUBLIC_MAX_IMAGE_HEIGHT'] or 0
    if (limit_w or limit_h) and req_tile is None:
        logger.debug(
            'Public image limits, checking parameters vs %d x %d limit' % (limit_w, limit_h)
        )

        # For v1 only, v2 will get these from a default template
        default_w = limit_w
        default_h = limit_h

        # If we're using a template, get the template dimensions
        template_w = 0
        template_h = 0
        if req_template:
            try:
                templ = image_engine.get_template(req_template)
                template_w = templ.image_attrs.width() or 0
                template_h = templ.image_attrs.height() or 0
            except KeyError:
                # Validation (yet to come) will reject the bad template name
                pass

        # v1.32.1 - if template contradicts the limit, template takes precedence
        if limit_w and template_w and template_w > limit_w:
            limit_w = template_w
        if limit_h and template_h and template_h > limit_h:
            limit_h = template_h

        # Check the requested size vs the limits
        if req_width and limit_w and req_width > limit_w:
            raise ValueError('width: exceeds public image limit')
        if req_height and limit_h and req_height > limit_h:
            raise ValueError('height: exceeds public image limit')

        # Check if we need to size-limit an otherwise unlimited image request
        # Note: In v2 this will be done with new default values in ImageAttrs
        if not req_width and not req_height and not template_w and not template_h:
            req_width = default_w if default_w else 0
            req_height = default_h if default_h else 0
            # Unless explicitly set otherwise, prevent padding
            if req_width and req_height and req_autosizefit is None:
                req_autosizefit = True
            logger.debug(
                'Public image limits, unsized image set as %d x %d' % (req_width, req_height)
            )

    return req_width, req_height, req_autosizefit


def _public_image_limits_post_image_checks(req_width, req_height, req_template, image_data):
    """
    To be called when no one is logged in, checks that the image actually
    generated conforms to the limits defined by the PUBLIC_MAX_IMAGE_WIDTH
    and PUBLIC_MAX_IMAGE_HEIGHT settings.

    As an optimisation, this function only has any effect for the conditions
    that would not have been caught by the "pre-image" checks.
    Specifically, this is when either:

    * only PUBLIC_MAX_IMAGE_WIDTH is set, but only an image height was given
    or
    * only PUBLIC_MAX_IMAGE_HEIGHT is set, but only an image width was given

    Raises a ValueError if the generated image dimensions have exceeded the
    defined limits.
    """
    if not req_template:
        limit_w = app.config['PUBLIC_MAX_IMAGE_WIDTH'] or 0
        limit_h = app.config['PUBLIC_MAX_IMAGE_HEIGHT'] or 0
        # We have to inspect the image, so only do this for the 2 conditions
        # that the pre-image checks couldn't do
        if (limit_w and not limit_h and req_height and not req_width) or \
           (limit_h and not limit_w and req_width and not req_height):
            logger.debug('Public image limits, checking generated image dimensions')
            image_w, image_h = image_engine.get_image_data_dimensions(image_data)
            logger.debug('Public image limits, generated image is %d x %d' % (image_w, image_h))
            if image_w and image_h:
                if limit_w and image_w > limit_w:
                    raise ValueError('width: exceeds public image limit')
                if limit_h and image_h > limit_h:
                    raise ValueError('height: exceeds public image limit')


def _log_stats(image_id, data_len, is_original, from_cache, write_image_stats=True):
    """
    Logs statistics about an image request/response with the stats manager.
    Specify an image ID of 0 to update only the system statistics.
    Specify a data length of 0 for 'Not Modified' responses.
    The write_image_stats flag is passed straight through to the stats manager.
    """
    duration_secs = 0
    if 'request_started' in flask.g:
        duration_secs = time.time() - flask.g.request_started

    if data_len > 0:
        if is_original:
            stats_engine.log_download(
                image_id,
                data_len,
                duration_secs,
                write_image_stats
            )
        else:
            stats_engine.log_view(
                image_id,
                data_len,
                from_cache,
                duration_secs,
                write_image_stats
            )
    else:
        stats_engine.log_request(
            image_id,
            duration_secs,
            write_image_stats
        )
