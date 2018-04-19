#
# Script to run the image server using Apache with mod_wsgi.
#
# Requires the relevant Apache conf file to set the mod_wsgi python-path
# for the image server code and its libraries. E.g.
# 
# WSGIDaemonProcess qis user=qis group=qis processes=4 threads=10
#                   python-home=/opt/qis python-path=/opt/qis/src
#

from imageserver.flask_app import app as application
