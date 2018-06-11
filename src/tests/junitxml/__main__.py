"""Command line functionality for junitxml.

:Author: Duncan Findlay <duncan@duncf.ca>
"""
import sys

from . import main

if __name__ == '__main__':
    if sys.argv[0].endswith('__main__.py'):
        sys.argv[0] = 'python -m junitxml'
    main.main()
