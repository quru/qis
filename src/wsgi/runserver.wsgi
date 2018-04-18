#
# Script to run the image server using Apache with mod_wsgi.
#
# Requires the relevant Apache conf file to set the mod_wsgi python-path
# for the image server code and its libraries. E.g.
# 
# WSGIDaemonProcess qis user=qis group=qis processes=4 threads=10
#                   python-path=/opt/qis/src:/opt/qis/lib/python3.5/site-packages
#

from imageserver.flask_app import app as application
