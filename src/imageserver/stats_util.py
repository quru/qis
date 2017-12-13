#
# Quru Image Server
#
# Document:      stats_util.py
# Date started:  20 Sep 2011
# By:            Matt Fozard
# Purpose:       Statistics manipulation and utility functions
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

from .models import ImageStats, SystemStats


def add_zero_stats(dt_list_from, dt_list_to, frequency_mins, stats_list, stats_model):
    """
    Takes a list of stats objects, assumed to be ordered by time, and adds
    additional zeroed objects at positions where areas of no data begin and end.
    This ensures that stats graphing clients draw areas with no data as a zero
    line, rather than incorrectly extrapolating by joining up intermittent values.

    The from and to times should be UTC datetime objects, and are required so that
    the method can determine if data is missing at the start or end of the given
    stats list. If the to time is in the future, zeroed objects will not be added
    beyond the current time.

    The stats model (as a class) can be either ImageStats or SystemStats, and is
    used as the object type to pad the stats list with.

    Returns the (possibly altered) stats list.

    Note that this function will be either too eager or too lazy if the value
    of STATS_FREQUENCY is changed and legacy stats data is then provided.
    """
    if stats_model is ImageStats:
        zero_obj = lambda t_from, t_to: ImageStats(0, 0, 0, 0, 0, 0, 0, 0,
                                                   t_from, t_to)
    elif stats_model is SystemStats:
        zero_obj = lambda t_from, t_to: SystemStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                                    t_from, t_to)
    else:
        raise ValueError('Unsupported stats type ' + str(stats_model))

    # The normal time between data records is STATS_FREQUENCY plus a bit
    # (the bit == time taken to flush the stats to the db)
    normal_gap = timedelta(minutes=frequency_mins)
    max_gap = normal_gap + (normal_gap / 2)

    # Convert 'from' stats times to 'to' stats times
    dt_list_from += normal_gap
    dt_list_to += normal_gap

    # Loop on all known data points
    time_now = datetime.utcnow()
    idx = 0
    while idx < len(stats_list):
        # Handle         D D _ D --> D D Z D
        #                _ _ _ D --> Z _ Z D
        #                _ _ _ _ --> Z _ _ Z
        #            D _ D _ _ D --> D Z D Z Z D
        #        D _ D _ _ _ _ D --> D Z D Z _ _ Z D
        #        _ _ _ D _ _ _ _ --> Z _ Z D Z _ _ Z
        #
        # Which boils down to looking either side of every data point
        # along with the leading/trailing handling after the loop.
        #
        # Also, zero records should not be added beyond the current time
        # (those data points are undefined, zero cannot be assumed)

        kdata = stats_list[idx]
        is_first = (idx == 0)
        is_last  = (idx == len(stats_list) - 1)
        prev_to = dt_list_from if is_first else stats_list[idx - 1].to_time
        next_to = dt_list_to if is_last else stats_list[idx + 1].to_time
        # Look left
        if (kdata.to_time - prev_to) > max_gap:
            # Insert a Z record to the left
            stats_list.insert(idx, zero_obj(kdata.to_time - normal_gap, kdata.to_time))
            idx += 1  # Move idx back to kdata
        # Look right
        if (((next_to - kdata.to_time) > max_gap) and
            (not is_last or (kdata.to_time + normal_gap < time_now))):
            # Insert a Z record to the right
            stats_list.insert(idx + 1, zero_obj(kdata.to_time, kdata.to_time + normal_gap))
            idx += 1  # Move idx to the new Z record
        # Go to next kdata
        idx += 1

    # Handle leading and trailing records, and the "no data" set
    no_data = (len(stats_list) == 0)
    if no_data or ((stats_list[0].to_time - dt_list_from) > max_gap):
        # Add a Z record at dt_list_from
        stats_list.insert(0, zero_obj(dt_list_from - normal_gap, dt_list_from))
    if no_data:
        # Add a Z record at dt_list_to
        stats_list.append(zero_obj(dt_list_to - normal_gap, dt_list_to))
    else:
        stat_last = stats_list[len(stats_list) - 1]
        if ((time_now - stat_last.to_time > max_gap) and
            (dt_list_to - stat_last.to_time > max_gap)):
            # Add a Z record at min(dt_list_to, time_now)
            term_time_to = min(time_now, dt_list_to)
            stats_list.append(zero_obj(term_time_to - normal_gap, term_time_to))

    return stats_list
