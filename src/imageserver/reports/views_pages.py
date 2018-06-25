#
# Quru Image Server
#
# Document:      views_pages.py
# Date started:  08 Sep 2011
# By:            Matt Fozard
# Purpose:       Reports web page URLs and views
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
#

from datetime import datetime, timedelta

from flask import request, render_template
from werkzeug.exceptions import InternalServerError

from imageserver.flask_app import app, data_engine
from imageserver.reports import blueprint
from imageserver.util import get_timezone_code, get_timezone_offset, to_iso_datetime
from imageserver.util import parse_boolean, parse_int, parse_iso_datetime, parse_long
from imageserver.views_util import log_security_error


# The reports index page
@blueprint.route('/')
def index():
    return render_template(
        'reports_index.html'
    )


# The system stats graphing page
@blueprint.route('/systemstats/')
def system_stats():
    # Get parameters
    time_from = request.args.get('from', '')
    time_to = request.args.get('to', '')
    data_type = request.args.get('data_type', '1')
    embed = request.args.get('embed', '')
    try:
        # Validate params, get iso and datetime versions
        (iso_time_from, iso_time_to) = process_time_parameters(time_from, time_to)
        dt_time_from = parse_iso_datetime(iso_time_from)
        dt_time_to = parse_iso_datetime(iso_time_to)
        embed = parse_boolean(embed)

        return render_template(
            'reports_system_stats.html',
            timezone=get_timezone_code(),
            timezone_seconds=get_timezone_offset(),
            time_from=dt_time_from,
            time_to=dt_time_to,
            data_type=data_type,
            embed=embed
        )
    except Exception as e:
        log_security_error(e, request)
        if app.config['DEBUG']:
            raise
        raise InternalServerError(str(e))


# The image stats graphing page
@blueprint.route('/imagestats/')
def image_stats():
    # Get parameters
    image_id = request.args.get('id', '')
    time_from = request.args.get('from', '')
    time_to = request.args.get('to', '')
    data_type = request.args.get('data_type', '1')
    embed = request.args.get('embed', '')
    try:
        # Validate params, get iso and datetime versions
        if image_id == '':
            raise ValueError('No image was specified.')
        image_id = parse_long(image_id)
        (iso_time_from, iso_time_to) = process_time_parameters(time_from, time_to)
        dt_time_from = parse_iso_datetime(iso_time_from)
        dt_time_to = parse_iso_datetime(iso_time_to)
        embed = parse_boolean(embed)

        return render_template(
            'reports_image_stats.html',
            timezone=get_timezone_code(),
            timezone_seconds=get_timezone_offset(),
            time_from=dt_time_from,
            time_to=dt_time_to,
            data_type=data_type,
            db_image=data_engine.get_image(image_id=image_id),
            embed=embed
        )
    except Exception as e:
        log_security_error(e, request)
        if app.config['DEBUG']:
            raise
        raise InternalServerError(str(e))


# Top 10 image details
@blueprint.route('/top10/')
def topten():
    # Get parameters
    days = request.args.get('days', '1')
    limit = request.args.get('number', '10')
    data_type = request.args.get('data_type', '2')
    try:
        results = []
        db_session = data_engine.db_get_session()
        try:
            # Convert params to ints
            days = parse_int(days)
            limit = parse_int(limit)
            data_type = parse_int(data_type)

            # Set options
            if days < 1:
                days = 1
            if days > 30:
                days = 30
            if limit < 10:
                limit = 10
            if limit > 100:
                limit = 100

            if data_type == 1:
                order = '-total_requests'
            elif data_type == 2:
                order = '-total_views'
            elif data_type == 3:
                order = '-total_cached_views'
            elif data_type == 4:
                order = '-total_downloads'
            elif data_type == 5:
                order = '-total_bytes'
            elif data_type == 6:
                order = '-total_seconds'
            elif data_type == 7:
                order = '-max_seconds'
            else:
                raise ValueError('Invalid data_type %d' % data_type)

            # Get initial stats
            top_stats = data_engine.summarise_image_stats(
                datetime.utcnow() - timedelta(days=days),
                datetime.utcnow(),
                limit=limit,
                order_by=order,
                _db_session=db_session
            )

            # Convert stats list to an image list
            for result in top_stats:
                db_image = data_engine.get_image(image_id=result[0], _db_session=db_session)
                if db_image:
                    results.append({
                        'id': db_image.id,
                        'src': db_image.src,
                        'requests': result[1],
                        'views': result[2],
                        'cached_views': result[3],
                        'downloads': result[4],
                        'bytes': result[5],
                        'seconds': result[6],
                        'max_seconds': result[7]
                    })
        finally:
            db_session.close()

        return render_template(
            'reports_topten.html',
            days=days,
            data_type=data_type,
            number=limit,
            results=results
        )
    except Exception as e:
        log_security_error(e, request)
        if app.config['DEBUG']:
            raise
        raise InternalServerError(str(e))


def process_time_parameters(from_str, to_str):
    """
    Validates or sets default values for 2 timestamps, expected to be either
    empty strings or in "yyyy-mm-ddThh:mm:ss" format as UTC times.
    If the 'to' value is empty, it is defaulted to the current UTC time.
    If the 'from' value is empty, it is defaulted to UTC midnight at the
    beginning of the same day as the 'to' value.
    Returns a tuple of (from_str, to_str), or raises a ValueError if either
    of the supplies values is not in the correct format.
    """
    if to_str:
        # Just validate it
        dt_time_to = parse_iso_datetime(to_str)
    else:
        # Set as now
        dt_time_to = datetime.utcnow()
        to_str = to_iso_datetime(dt_time_to)

    if from_str:
        # Just validate it
        dt_time_from = parse_iso_datetime(from_str)
        if dt_time_from >= dt_time_to:
            dt_time_from = dt_time_to - timedelta(minutes=1)
            from_str = to_iso_datetime(dt_time_from)
    else:
        # Set as midnight on day of time_to
        dt_time_from = dt_time_to - timedelta(
            hours=dt_time_to.hour, minutes=dt_time_to.minute,
            seconds=dt_time_to.second, microseconds=dt_time_to.microsecond
        )
        from_str = to_iso_datetime(dt_time_from)

    return (from_str, to_str)
