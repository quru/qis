#
# Quru Image Server
#
# Document:      util.py
# Date started:  29 Mar 2011
# By:            Matt Fozard
# Purpose:       Stand-alone utility functions
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
# 26Aug2011  Matt  Added AsyncHttpRequest and utility
# 12Sep2011  Matt  Added time zone utilities
#

from calendar import timegm
from datetime import datetime
from unicodedata import normalize
import difflib
import hashlib
import os.path
import random
import re
import unicodedata
import urllib.parse
import uuid
import socket
import string
import threading
import time

import requests
import collections


# These are borrowed from Werkzeug/utils.py for our version of secure_filename()
__sf_chars_strip = r'[^\w &@{}\[\],;$=!#()%+~.-]'  # more liberal than Werkzeug
_filename_ascii_strip_re = re.compile(__sf_chars_strip)
_filename_unicode_strip_re = re.compile(__sf_chars_strip, re.UNICODE)
_windows_device_files = ('CON', 'AUX', 'COM1', 'COM2', 'COM3', 'COM4', 'LPT1',
                         'LPT2', 'LPT3', 'PRN', 'NUL')


def etag(*vals):
    """
    Make an ETag from a number of strings (or byte buffers),
    obscuring the underlying content.
    """
    h = hashlib.sha1()
    for v in vals:
        h.update(v if isinstance(v, bytes) else v.encode('utf8'))
    return h.hexdigest()


def is_timezone_dst():
    """
    Returns whether daylight saving time is in effect for the current timezone.
    See also http://bugs.python.org/issue7229
    """
    return time.daylight and time.localtime().tm_isdst


def get_timezone_code():
    """
    Returns the timezone abbreviation of the current environment, including
    daylight saving. Note that some timezone codes are ambiguous, e.g. EST.
    """
    (tz, dst_tz) = time.tzname
    return dst_tz if is_timezone_dst() else tz


def get_timezone_offset():
    """
    Returns the offset in seconds that must be added to a local time, including
    daylight saving, in order to convert it to a UTC time.
    """
    return time.altzone if is_timezone_dst() else time.timezone


def invoke_http_async(url, data=None, method='GET', log_success_fn=None, log_fail_fn=None):
    """
    Launches a background thread to invoke a URL as a GET or POST request,
    with optional data as a dictionary. For GET requests, any supplied data will
    be appended to the URL.
    If logging functions are provided they will be invoked with a single
    string argument on success or on failure. Otherwise there is no way of
    determining the success or failure of the operation.
    """
    t = AsyncHttpRequest(url, data, method, log_success_fn, log_fail_fn)
    t.start()


def get_computer_hostname():
    """
    Returns the computer's networking host name.
    """
    # socket.getfqdn() can return strange things when IPv6 enabled
    return socket.gethostname()


def get_computer_id():
    """
    Returns a fairly unique identifier for this computer, based on a hash of
    its host name and one of its network interface MAC addresses. This means
    of course that the ID will change if the host name or network interfaces
    change. If you do require uniqueness, go elsewhere.
    """
    mac = uuid.getnode()
    # https://docs.python.org/2/library/uuid.html#uuid.getnode
    # If all attempts to obtain the hardware address fail, we choose a random
    # 48-bit number with its eighth bit set to 1 as recommended in RFC 4122
    if (mac >> 40) % 2:
        mac = 123456789012345  # We don't want a random number
    h = hashlib.sha1(bytes('cid', 'utf8'))
    h.update(bytes(repr(mac), 'utf8'))
    h.update(bytes(get_computer_hostname(), 'utf8'))
    return h.hexdigest()


def this_is_computer(net_name):
    """
    Returns whether a computer network name or IP address appears to be this
    (the current) computer. True is returned for 'localhost', the loopback
    network address, or any other host name or IP address that matches the
    current network configuration.
    """
    try_names = [
        'localhost',
        socket.getfqdn(),
        socket.gethostname()
    ]
    server_names = []
    server_addrs = []
    try:
        for name in try_names:
            (hostname, aliaslist, ipaddrlist) = socket.gethostbyname_ex(name)
            server_names.append(hostname)
            server_names.extend(aliaslist)
            server_addrs.extend(ipaddrlist)
        return (net_name in server_names) or (net_name in server_addrs)
    except socket.gaierror:
        # No DNS service is available
        return net_name in ['localhost', '127.0.0.1', '::1']


def generate_password(length=10):
    """
    Returns a random string suitable for use as a password.
    """
    return ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(length)])


def parse_int(strval):
    """
    Parses a string value as an integer, returning the int value or 0 if the
    string is None or has 0 length.
    Raises a ValueError if the value cannot be parsed as an integer.
    """
    return int(strval) if strval else 0


def parse_long(strval):
    """
    Parses a string value as a long, returning the long value or 0L if the
    string is None or has 0 length.
    Raises a ValueError if the value cannot be parsed as a long.
    """
    return int(strval) if strval else 0


def parse_float(strval):
    """
    Parses a string value as a float, returning the float value or 0.0 if the
    string is None or has 0 length.
    Raises a ValueError if the value cannot be parsed as a float.
    """
    return float(strval) if strval else 0.0


def parse_boolean(strval):
    """
    Parses a string value as a boolean, returning True for values 'true', 't',
    'yes', 'y', '1' (case insensitive), or False for any other value.
    """
    if strval:
        return strval.lower() in ['1', 't', 'y', 'true', 'yes']
    else:
        return False


def parse_colour(strval):
    """
    Parses a string value as a colour string, e.g. "ff0000" or "red".
    If the string appears to be a hex RGB value it is prepended with a hash
    symbol, otherwise the same string is returned as lower case with spaces removed.
    """
    if not strval:
        return None
    if len(strval) == 6:
        if re.match('[a-fA-F0-9]{6}$', strval):
            strval = '#' + strval
    return strval.lower().replace(" ", "")


def parse_tile_spec(strval):
    """
    Parses a string in format "1:9", returning the equivalent int tuple of (1,9).
    Returns None if the value is empty, and raises a ValueError if the value
    cannot be parsed.
    """
    if not strval:
        return None
    svals = strval.split(':')
    if len(svals) != 2:
        raise ValueError('invalid format for tile: ' + strval)
    return (int(svals[0]), int(svals[1]))


def parse_iso_datetime(strval):
    """
    Parses a string in ISO 8601 format "yyyy-mm-ddThh:mm:ssZ", returning a
    UTC datetime instance, or raising a ValueError if the string cannot be
    parsed. Milliseconds and timezone, if present, are ignored.
    """
    dot_idx = strval.find('.')
    if dot_idx != -1:
        strval = strval[0:dot_idx]
    if len(strval) > 19:
        strval = strval[0:19]
    return datetime.strptime(strval, '%Y-%m-%dT%H:%M:%S')


def parse_iso_date(strval):
    """
    Parses a string in ISO 8601 format "yyyy-mm-dd", returning a UTC datetime
    instance with 0 for the time parts, or raising a ValueError if the string
    cannot be parsed. A time part, if present, is ignored.
    """
    if len(strval) > 10:
        strval = strval[0:10]
    return datetime.strptime(strval, '%Y-%m-%d')


def to_iso_datetime(utc_val):
    """
    Converts either a UTC datetime instance or a time supplied as UTC seconds
    into a string with ISO 8601 format "yyyy-mm-ddThh:mm:ssZ".
    """
    secs = timegm(utc_val.timetuple()) if isinstance(utc_val, datetime) else utc_val
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(secs))


def validate_boolean(val):
    """
    Raises a ValueError if val is not a boolean, otherwise does nothing.
    """
    if not isinstance(val, bool):
        raise ValueError('Value is not a boolean')


def validate_number(val, min_val, max_val):
    """
    Raises a ValueError if val is not a number, or is below min_val
    or above max_val, otherwise does nothing.
    """
    if not isinstance(val, int) and not isinstance(val, float):
        raise ValueError('Value is not a number')
    if val < min_val or val > max_val:
        fmt = '%0.2f' if isinstance(val, float) else '%d'
        raise ValueError((fmt + ' is out of range') % val)


def validate_string(val, min_length, max_length):
    """
    Raises a ValueError if val is not a string, or is less than min_length
    or more than max_length in length, otherwise does nothing.
    """
    if val is None:
        if min_length > 0:
            raise ValueError('No value specified')
    else:
        if not isinstance(val, str):
            raise ValueError('Value is not a string')
        if len(val) < min_length:
            raise ValueError('Value is too short (min %d)' % min_length)
        if len(val) > max_length:
            raise ValueError('Value is too long (max %d)' % max_length)


def validate_string_in(val, values, case_sensitive=True):
    """
    Raises a ValueError if val is not in values, otherwise does nothing.
    """
    if case_sensitive:
        found = val in values
    else:
        found = val.lower() in [l.lower() for l in values]
    if not found:
        raise ValueError('Value is not one of: ' + ', '.join(values))


def validate_tile_spec(val, max_tiles):
    """
    Raises a ValueError if a tile spec tile number is invalid (below 1 or
    above the grid size) or if the tile spec grid size is invalid (below 1 or
    above max_tiles), otherwise does nothing.
    """
    if not isinstance(val, tuple) or len(val) != 2:
        raise ValueError('Tile is not a 2-tuple')
    if val[1] < 1 or val[1] > max_tiles:
        raise ValueError('Tile grid size is out of range')
    if val[0] < 1 or val[0] > val[1]:
        raise ValueError('Tile number is out of range')
    grid_len = 1
    grid_ok = False
    while ((grid_len * grid_len) <= max_tiles) and not grid_ok:
        if (grid_len * grid_len) == val[1]:
            grid_ok = True
        grid_len += 1
    if not grid_ok:
        raise ValueError('Tile grid size is not square')


def validate_filename(val):
    """
    Raises a ValueError if val is not between 5 and 255 characters
    or does not conform to the format "name.ext", otherwise does nothing.
    """
    try:
        # 5 == "a.ext"
        validate_string(val, 5, 255)
    except ValueError:
        raise ValueError('Filename must be in the format "name.ext" and less than 255 characters')
    val_ext = get_file_extension(val)
    if not val_ext:
        raise ValueError('Filename must have a file extension (e.g. ".jpg")')
    if ' ' in val_ext:
        raise ValueError('Invalid file extension: ' + val_ext)


def default_value(value, def_value):
    """
    Returns the value def_value if value is None, otherwise returns value.
    """
    return def_value if (value is None) else value


def get_file_extension(filename):
    """
    Returns the lower case file extension of a file name, without the dot.
    E.g. "jpg", or "" if there is no file extension. This function is 3x
    faster than using os.path.splitext.
    """
    dot_pos = filename.rfind('.')
    return filename[dot_pos + 1:].lower() if dot_pos != -1 else ''


def add_sep(filepath, leading=False):
    """
    Returns the supplied path with a trailing (or leading) os.path.sep appended,
    if it does not already have one.
    """
    if leading and not filepath.startswith(os.path.sep):
        return os.path.sep + filepath
    elif not leading and not filepath.endswith(os.path.sep):
        return filepath + os.path.sep
    else:
        return filepath


def strip_sep(filepath, leading=False):
    """
    Returns the supplied path without either a trailing (or leading) os.path.sep.
    Note: use filepath_normalize() to normalize paths rather than this function.
    """
    return filepath.lstrip(os.path.sep) if leading else filepath.rstrip(os.path.sep)


def strip_seps(filepath):
    """
    Returns the supplied path without both leading and trailing os.path.sep
    Note: use filepath_normalize() to normalize paths rather than this function.
    """
    return filepath.strip(os.path.sep)


def filepath_normalize(filepath):
    """
    Removes duplicate slashes and trailing slashes, and '/./' and '/../'
    entries where possible, from a file or directory path.
    One leading slash is preserved, if there was a leading slash.
    E.g. For '/a/b/' returns '/a/b'
         For '/a//b/c.jpg' returns '/a/b/c.jpg'
         For '/a/./b//c.jpg' returns '/a/b/c.jpg'
         For 'a//b/z/..//c.jpg' returns 'a/b/c.jpg'
         For './a' returns 'a'
         For '/' returns '/'
         For '' returns ''
    """
    fp = os.path.normpath(filepath)
    if fp.startswith(os.path.sep + os.path.sep):
        fp = fp[1:]
    if fp == os.path.curdir:
        fp = ''
    return fp


def filepath_filename(filepath):
    """
    Returns a file or directory's name, i.e. the final part of the path.
    E.g. For '/a/b/file.jpg' returns 'file.jpg'
         For '/a/b/c/' returns 'c'
         For 'a' returns 'a'
         For '/' returns ''
    """
    curpath = strip_sep(filepath)
    if curpath == '':
        return ''
    # This is about 1.5x faster than using os.path.split()
    sep_idx = curpath.rfind(os.path.sep)
    return curpath[sep_idx + 1:] if sep_idx != -1 else curpath


def filepath_parent(filepath):
    """
    Returns a file or directory's parent path,
    or None if filepath is blank or is the root directory.
    E.g. For '/a/b/file.jpg' returns '/a/b'
         For '/a/b/c/' returns '/a/b'
         For 'a' returns '/'
         For '' or '/' returns None
    """
    curpath = strip_sep(filepath)
    if curpath == '':
        return None
    # This is about 1.8x faster than using os.path.split()
    sep_idx = curpath.rfind(os.path.sep)
    return curpath[0:sep_idx] if sep_idx > 0 else os.path.sep


def filepath_components(filepath):
    """
    Splits a file path into a 3-tuple containing the filename, relative directory
    path, and the ordered list of single directory names that make up the
    directory path. Examples:
        "file" --> ('file', '', [''])
        "dir/" --> ('', 'dir', ['dir'])
        "/one/two/" --> ('', 'one/two', ['one', 'two'])
        "/one/image.jpg" --> ('image.jpg', 'one', ['one'])
        "/one/two/image.jpg" --> ('image.jpg', 'one/two', ['one', 'two'])
    """
    (fullpath, filename) = os.path.split(filepath)
    # Remove leading and trailing slashes from dir path so that we don't get
    # blank strings in path_list (unless there is no path component)
    fullpath = strip_seps(filepath_normalize(fullpath))
    # Get dir path entries
    path_list = fullpath.split(os.path.sep)
    return (filename, fullpath, path_list)


def adjust_query_string(qs, add_update_params=None, del_params=None):
    """
    Adjusts query string qs, updating or adding new parameters with the dictionary
    add_update_params, and removing parameters whose names are given by the list
    del_params. Returns a new query string reflecting the changes. Query strings
    with more than one value per parameter name are not supported. Use an ordered
    dictionary for add_update_params if you want to preserve the order of added
    parameters.
    """
    if add_update_params is None:
        add_update_params = {}
    if del_params is None:
        del_params = []

    qs_items = urllib.parse.parse_qsl(qs, True)
    # Update existing list entries (to preserve existing order)
    updated_keys = []
    for idx, (k, _) in enumerate(qs_items):
        if k in add_update_params.keys():
            qs_items[idx] = (k, add_update_params[k])
            updated_keys.append(k)
    # Add new list entries
    for newkey in add_update_params.keys():
        if newkey not in updated_keys:
            qs_items.append((newkey, add_update_params[newkey]))
    # Delete list entries
    qs_items = [(k, v) for (k, v) in qs_items if k not in del_params]
    # Return re-constituted query string
    return urllib.parse.urlencode(qs_items)


def get_string_changes(str1, str2, delimeter=' * ', char_limit=-1, return_words=True):
    """
    Returns a string with the parts of str2 that have been changed from str1.
    Different changes will be separated by the delimeter.
    If char_limit is specified and the differences exceed it, the returned
    string will be truncated at this limit and end with '...'.
    If return_words is True, an attempt will be made to return only whole
    words in the response.
    An empty string is returned if str1 and str2 are the same, or if str2
    is empty.
    """
    def get_block(val, from_idx, to_idx, whole_words):
        block_start = (
            index_of_word_break(val, from_idx, False) if whole_words else from_idx
        )
        block_end = (
            index_of_word_break(val, to_idx, True) if whole_words else (to_idx + 1)
        )
        return val[block_start:block_end]

    if char_limit != -1 and char_limit < 5:
        raise ValueError('char_limit must be 5 or more')

    diffchars = difflib.ndiff(str1, str2)
    retbuf = []
    retlen = 0
    index = -1
    change_start = -1
    change_end = -1
    clear_count = 0
    maxed = False
    for dc in diffchars:
        # Use only chars present in str2
        if dc[0] == ' ' or dc[0] == '+':
            index += 1
            # Track changed blocks
            if dc[0] == '+':
                if change_start == -1:
                    change_start = index
                change_end = index
                clear_count = 0
            else:
                clear_count += 1

            # Treat 20 chars without + as the end of a block
            if change_start != -1 and clear_count == 20:
                block_str = get_block(str2, change_start, change_end, return_words)
                if retlen > 0:
                    block_str = delimeter + block_str
                retbuf.append(block_str)
                retlen += len(block_str)
                change_start = change_end = -1
                # Check for return limit
                if char_limit != -1 and retlen > char_limit:
                    maxed = True
                    break

    # Check for unfinished trailing block
    if change_start != -1 and not maxed:
        block_str = get_block(str2, change_start, change_end, return_words)
        if retlen > 0:
            block_str = delimeter + block_str
        retbuf.append(block_str)
        retlen += len(block_str)

    ret_str = ''.join(retbuf)
    if char_limit != -1 and len(ret_str) > char_limit:
        ret_str = ret_str[0:char_limit - 3] + '...'
    return ret_str


def index_of_word_break(val, from_index, forwards=True):
    """
    Returns the character index, forwards or backwards from from_index, where
    a new word starts or ends.

    Searching forwards, the character position 1 past the end of the next
    word is returned, or the string length if this is reached first.

    Searching backwards, the character position of the first letter of the
    previous word is returned, or 0 if the beginning of the string is reached.
    """
    if val == '':
        return 0
    idx = from_index
    if idx < 0:
        idx = 0
    if idx > len(val) - 1:
        idx = len(val) - 1

    delta = 1 if forwards else -1
    while idx >= 0 and idx < len(val):
        test_idx = idx + delta
        if test_idx < 0 or test_idx > len(val) - 1:
            break
        if val[test_idx] in [' ', '.', ',', ';', '\r', '\n']:
            # Stop at this word break
            return test_idx if forwards else idx
        idx += delta
    # No word break found
    return len(val) if forwards else 0


def object_to_dict(obj, _r_stack=None):
    """
    Returns a dictionary of 'public' attributes and their values within an
    object. The function recurses for attribute values that consist of
    lists or user-defined objects.

    Detection of nested objects (to prevent infinite recursion) is handled by
    skipping the attribute if creation of an attribute value for the same object
    has already been started. This requires the objects in question to provide
    an __eq__ method.
    """
    if _r_stack is None:
        _r_stack = []
    if obj is None or isinstance(obj, dict):
        return obj
    obj_vars = vars(obj)
    attr_dict = dict(
        (k, v) for k, v in obj_vars.items()
        if not k.startswith('_') and not isinstance(v, collections.Callable) and v not in _r_stack
    )
    for k, v in attr_dict.items():
        if isinstance(v, list):
            attr_dict[k] = object_to_dict_list(v, _r_stack)
        elif hasattr(v, '__module__'):
            _r_stack.append(obj)
            attr_dict[k] = object_to_dict(v, _r_stack)
            _r_stack.pop()
    return attr_dict


def object_to_dict_list(obj, _r_stack=None):
    """
    Returns a list of dictionaries (created using object_to_dict)
    containing an entry for every item in the provided iterable.
    """
    ret_list = []
    for o in obj:
        ret_list.append(object_to_dict(o, _r_stack))
    return ret_list


def object_to_dict_dict(obj, _r_stack=None):
    """
    Returns a dictionary of dictionaries (created using object_to_dict)
    containing an entry for every item in the provided dictionary.
    """
    ret_dict = {}
    for o in obj:
        ret_dict[o] = object_to_dict(obj[o], _r_stack)
    return ret_dict


def unicode_to_ascii(ustr):
    """
    Returns an ascii string from a unicode string. Some characters will be
    converted to their nearest ascii equivalent, other characters may simply be
    discarded. Callers should be wary of this data loss and that note the same
    ascii string can be returned for very different unicode inputs.
    """
    # Make an effort to retain some useful characters that would otherwise be lost
    replace_dict = {
        0x2010: 0x2D, 0x2011: 0x2D, 0x2012: 0x2D,  # -
        0x2013: 0x2D, 0x2014: 0x2D, 0x2015: 0x2D,  # --
        0x2018: 0x27, 0x2019: 0x27,                # '
        0x201C: 0x22, 0x201D: 0x22,                # "
    }
    ustr_chars = []
    for c in ustr:
        try:
            ustr_chars.append(chr(replace_dict[ord(c)]))
        except KeyError:
            ustr_chars.append(c)
    ustr2 = ''.join(ustr_chars)
    # Convert to ascii, ignoring errors
    return unicodedata.normalize('NFKD', ustr2).encode('ascii', 'ignore').decode('ascii')


def unicode_to_utf8(ustr):
    """
    Returns a UTF8 string from a unicode string. Some characters will be
    converted to their nearest equivalent, other characters may simply be
    discarded. Callers should be wary of this data loss, though it only affects
    the more unusual characters.
    """
    # Convert to UTF8, ignoring errors
    return unicodedata.normalize('NFKD', ustr).encode('utf8', 'ignore').decode('utf8')


def secure_filename(filename, keep_unicode=False):
    r"""
    Pass a filename and this will return a secure version of it. This filename
    can then safely be stored on a regular file system and passed os.path.join.

    This function is based on werkzeug's secure_filename() but retains spaces
    in filenames, along with many other common naming characters such as
    ampersands and brackets. In addition, this version also allows the
    retention of unicode characters (which will be NFC normalized).

    On windows system the function makes sure that the file is not named after
    one of the special device files.

    >>> secure_filename('My cool movie.mov')
    'My cool movie.mov'
    >>> secure_filename('../../../etc/passwd')
    'etc_passwd'
    >>> secure_filename('.hidden?')
    'hidden'
    >>> secure_filename('///bits & bobs (misc folder #1)')
    'bits & bobs (misc folder #1)'
    >>> secure_filename('i contained a\x00null and\x09tab.txt')
    'i contained anull andtab.txt'
    >>> secure_filename(u'i contained cool \xfcml\xe4uts.txt')
    'i contained cool umlauts.txt'
    >>> secure_filename(u'i contain \x00\x09cool \xfcml\xe4uts.txt', True)
    u'i contain cool \xfcml\xe4uts.txt'

    Raises a ValueError if the function would return an empty filename.
    """
    if keep_unicode:
        # normalize to give a better chance of the strip stage doing the right thing
        filename = normalize('NFC', filename)
    else:
        # normalize to ascii
        filename = normalize('NFKD', filename).encode('ascii', 'ignore').decode('ascii')
    # replace path seps
    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, '_')
    # remove unsupported characters
    if keep_unicode:
        filename = _filename_unicode_strip_re.sub('', filename).strip('._').strip()
    else:
        filename = _filename_ascii_strip_re.sub('', filename).strip('._').strip()

    # on nt a couple of special files are present in each folder.  We
    # have to ensure that the target file is not such a filename.  In
    # this case we prepend an underline
    if os.name == 'nt' and filename and \
       filename.split('.')[0].upper() in _windows_device_files:
        filename = '_' + filename

    if not filename:
        raise ValueError('Filename contained no valid characters')
    return filename


def timefunc(f):
    """
    A function decorator that prints out how long the function took to execute.
    For debugging use only.
    """
    def f_timer(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        print(f.__name__, 'took', round((end - start) * 1000, 3), 'millis')
        return result
    return f_timer


class KeyValueCache(object):
    """
    Implements a simple key/value in-memory cache, with an internal lock to
    ensure thread safety. This object is for simple use cases within one Python
    process. Use something like Memcached for a scalable system-wide cache.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._cache = dict()

    def get(self, key):
        """
        Returns the cache entry for the given key,
        or None if there is no such key.
        """
        with self._lock:
            v = self._cache.get(key, None)
        return v

    def set(self, key, value):
        """
        Sets or replaces a cache entry.
        """
        with self._lock:
            self._cache[key] = value

    def set_many(self, kv_dict):
        """
        Sets or replaces cache entries from a key/value dictionary.
        """
        with self._lock:
            self._cache.update(kv_dict)

    def keys(self):
        """
        Returns the list of keys currently stored in this cache.
        In a multi-threaded environment this list may be immediately obsolete.
        """
        with self._lock:
            keys = list(self._cache.keys())
        return keys

    def values(self):
        """
        Returns the list of values currently stored in this cache.
        In a multi-threaded environment this list may be immediately obsolete.
        """
        with self._lock:
            values = list(self._cache.values())
        return values

    def clear(self):
        """
        Removes all entries from the cache.
        """
        with self._lock:
            self._cache.clear()


class AsyncHttpRequest(threading.Thread):
    """
    Implements a thread that send an HTTP GET or POST request then exits.
    """
    def __init__(self, url, data=None, method='GET', log_success_fn=None, log_fail_fn=None):
        """
        Creates a thread ready to invoke a URL as a GET or POST with optional
        data as a dictionary. For GET requests, any supplied data will be
        appended to the URL.
        If logging functions are provided they will be invoked with a single
        string argument on success or on failure.
        """
        threading.Thread.__init__(self)
        self.daemon = True  # Don't block parent process from exiting
        self.url = url
        self.data = data
        self.method = method
        self.log_success_fn = log_success_fn
        self.log_fail_fn = log_fail_fn

    def run(self):
        try:
            if self.method.lower() == 'get':
                r = requests.get(self.url, params=self.data)
            else:
                r = requests.post(self.url, data=self.data)

            if r.status_code == 200 and self.log_success_fn:
                self.log_success_fn('Successful call to ' + self.url)
            elif r.status_code != 200 and self.log_fail_fn:
                self.log_fail_fn('HTTP code %d returned from URL %s' % (r.status_code, self.url))

        except Exception as e:
            if self.log_fail_fn:
                self.log_fail_fn('Error calling URL %s: %s' % (self.url, str(e)))
