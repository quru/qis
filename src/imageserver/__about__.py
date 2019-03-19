# -*- coding: utf-8 -*-
#
# Quru Image Server
#
# Document:      __about__.py
# Date started:  05 Aug 2013
# By:            Alex Stapleton
# Purpose:       App packaging info and version
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

__tag__ = "QIS"
__title__ = "Quru Image Server"
__summary__ = "A high performance dynamic image server"
__description__ = ("To learn more about Quru Image Server, "
                   "please visit the project home page on GitHub or quru.com")
__uri__ = "https://www.quruimageserver.com/"
__source_uri__ = "https://github.com/quru/qis"
__platforms__ = ["Linux", "Unix", "Mac OSX"]

__version__ = "4.1.2"

__author__ = "Quru Ltd"
__email__ = "info@quru.com"

__license__ = "GNU Affero General Public License"
__copyright__ = "Copyright \xa9 2011 - 2019 Quru Ltd"


# Support running this from the command line to get version info
if __name__ == '__main__':
    import sys
    info = dict(vars())
    if len(sys.argv) == 1:
        ignore_list = [
            'sys', '__file__', '__builtins__', '__name__', '__doc__', '__package__',
            '__cached__', '__loader__', '__spec__'
        ]
        for k in info:
            if k not in ignore_list:
                print(k.strip('_') + ' = ' + str(info[k]))
    elif len(sys.argv) == 2 and sys.argv[1] == '--version':
        print(info['__version__'])
    else:
        print('Usage: python __about__.py [--version]')
