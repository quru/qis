#
# Quru Image Server
#
# Document:      views.py
# Date started:  12 Sep 2011
# By:            Matt Fozard
# Purpose:       Reporting data access URLs and views
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

from calendar import timegm
from datetime import datetime, timedelta

from flask import request

from imageserver.flask_app import app, data_engine, logger
from imageserver.flask_util import make_json_response
from imageserver.models import ImageStats, SystemStats
from imageserver.reports import blueprint
from imageserver.stats_util import add_zero_stats
from imageserver.util import parse_int, parse_long, parse_iso_datetime
from imageserver.views_util import log_security_error


# System statistics data feed
@blueprint.route('/datafeed/system', methods=['GET'])
def datafeed_system():
    try:
        # Get parameters
        dt_time_from = parse_iso_datetime(request.args.get('from'))
        dt_time_to = parse_iso_datetime(request.args.get('to'))
        data_type = parse_int(request.args.get('data_type', ''))

        require_full_period = (data_type < 8)
        if require_full_period:
            # Stop at 'now' minus the stats gap so we don't return incomplete stats
            dt_time_limit = datetime.utcnow() - timedelta(minutes=app.config['STATS_FREQUENCY'])
            if dt_time_to > dt_time_limit:
                dt_time_to = dt_time_limit

        # Get stats and convert to chart data
        results = data_engine.search_system_stats(dt_time_from, dt_time_to)
        results = add_zero_stats(
            dt_time_from, dt_time_to,
            app.config['STATS_FREQUENCY'], results, SystemStats
        )
        data = _db_results_to_flot_data(results, data_type)

        return make_json_response(
            200,
            data=data,
            first=0 if len(data) == 0 else data[0][0],
            last=0 if len(data) == 0 else data[-1][0]
        )

    except Exception as e:
        if not log_security_error(e, request):
            logger.error('Error reading system stats: ' + str(e))
        if app.config['DEBUG']:
            raise
        return make_json_response(
            200,
            data=[],
            first=0,
            last=0
        )


# Image statistics data feed
@blueprint.route('/datafeed/image', methods=['GET'])
def datafeed_image():
    try:
        # Get parameters
        image_id = parse_long(request.args.get('id', ''))
        dt_time_from = parse_iso_datetime(request.args.get('from'))
        dt_time_to = parse_iso_datetime(request.args.get('to'))
        data_type = parse_int(request.args.get('data_type', ''))

        require_full_period = (data_type < 8)
        if require_full_period:
            # Stop at 'now' minus the stats gap so we don't return incomplete stats
            dt_time_limit = datetime.utcnow() - timedelta(minutes=app.config['STATS_FREQUENCY'])
            if dt_time_to > dt_time_limit:
                dt_time_to = dt_time_limit

        # Get stats and convert to chart data
        results = data_engine.search_image_stats(dt_time_from, dt_time_to, image_id)
        results = add_zero_stats(
            dt_time_from, dt_time_to,
            app.config['STATS_FREQUENCY'], results, ImageStats
        )
        data = _db_results_to_flot_data(results, data_type)

        return make_json_response(
            200,
            data=data,
            first=0 if len(data) == 0 else data[0][0],
            last=0 if len(data) == 0 else data[-1][0]
        )

    except Exception as e:
        if not log_security_error(e, request):
            logger.error('Error reading image stats: ' + str(e))
        if app.config['DEBUG']:
            raise
        return make_json_response(
            200,
            data=[],
            first=0,
            last=0
        )


def _db_results_to_flot_data(results, data_type):
    """
    Converts a list of database objects (SystemStats or ImageStats) into a
    list of time series data tuples as expected by the Javascript Flot library.
    E.g. [(t1, value1), (t2, value2), ...]
    Where time values are returned as UTC milliseconds since the epoch.

    The data type code can be:
    1=requests, 2=views, 3=cached views, 4=cache pct, 5=downloads, 6=bytes,
    7=total request seconds, 8=max request seconds

    and for SystemStats only:
    100=average CPU %, 101=average RAM %, 102=image cache %
    """
    data = []
    for stat in results:
        stat_time_msec = (timegm(stat.to_time.timetuple()) * 1000)

        if data_type == 1:
            stat_val = stat.requests
        elif data_type == 2:
            stat_val = stat.views
        elif data_type == 3:
            stat_val = stat.cached_views
        elif data_type == 4:
            stat_val = 0 if stat.views == 0 else (
                (stat.cached_views * 100.0) // stat.views
            )
        elif data_type == 5:
            stat_val = stat.downloads
        elif data_type == 6:
            stat_val = stat.total_bytes
        elif data_type == 7:
            stat_val = stat.request_seconds
        elif data_type == 8:
            stat_val = stat.max_request_seconds
        # SystemStats only
        elif data_type == 100:
            stat_val = stat.cpu_pc
        elif data_type == 101:
            stat_val = stat.memory_pc
        elif data_type == 102:
            stat_val = stat.cache_pc
        else:
            raise ValueError('Invalid data_type %d' % data_type)

        data.append((stat_time_msec, stat_val))

    return data
