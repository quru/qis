#
# Quru Image Server
#
# Document:      image_wrapper.py
# Date started:  07 Mar 2011
# By:            Matt Fozard
# Purpose:       Wrapper for a returned image and its associated properties
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


class ImageWrapper(object):
    """
    Class to wrap binary image data along with some associated properties.
    """
    def __init__(self, image_data, image_attrs, from_cache=False,
                 last_modified=0, client_expiry_seconds=0,
                 attachment=False, record_stats=True):
        self._data = image_data
        self._attrs = image_attrs
        self._from_cache = from_cache
        self._last_modified_time = last_modified
        self._client_expiry_time = client_expiry_seconds
        self._attachment = attachment
        self._record_stats = record_stats

    def data(self):
        """
        Returns the binary image data for this image.
        """
        return self._data

    def attrs(self):
        """
        Returns the ImageAttrs object associated with this image.
        """
        return self._attrs

    def is_from_cache(self):
        """
        Returns whether the image data was returned from the image server's cache.
        If False, this image was generated on the fly. This informational flag
        can be used to help determine the e.g. the percentage of cache hits.
        """
        return self._from_cache

    def last_modified_time(self):
        """
        Returns the last modification time of this image,
        as number of seconds since the epoch in UTC.
        """
        return self._last_modified_time

    def client_expiry_time(self):
        """
        Returns the number of seconds that a client (web browser) should cache
        this image for before expiring and re-requesting it.
        A value of 0 means do not instruct the client how long to cache the image.
        A value of -1 means expire the image immediately on receipt.
        """
        return self._client_expiry_time

    def is_attachment(self):
        """
        Returns whether this image should be returned to the client as an HTTP
        attachment with filename, rather than inline (the default).
        """
        return self._attachment

    def record_stats(self):
        """
        Returns whether this image should be counted in the system statistics
        (the default), or excluded.
        """
        return self._record_stats
