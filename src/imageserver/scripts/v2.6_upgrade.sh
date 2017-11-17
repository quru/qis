#!/bin/bash -e

if [[ "$QIS_HOME" == "" ]]; then
    echo "Please set QIS_HOME (e.g. export QIS_HOME=/opt/qis) and re-run this command"
    exit 1
fi

echo "Upgrading Javascript file names"

echo "Changing directory to $QIS_HOME/src/imageserver/static/js"
cd "$QIS_HOME/src/imageserver/static/js"

echo "Removing old Javascript files"
if [[ $(find . -name '*_yc.js') ]]; then
    rm `find . -name '*_yc.js'`
fi

read -p "Do you need to maintain compatibility of Javascript files with earlier versions of QIS? [y/n]" RESP

if [[ "$RESP" == "y" ]]; then
    echo "Creating compatibility symlinks"
    ln -s canvas_view.min.js canvas_view_yc.js
    ln -s gallery_view.min.js gallery_view_yc.js
    ln -s simple_view.min.js simple_view_yc.js
    ln -s slideshow_view.min.js slideshow_view_yc.js
    ln -s lib/mootools.min.js mootools_yc.js

    echo "The following symlinks can be deleted after your URLs and file references have been updated:"
    find . -name '*_yc.js'
fi

echo ""
echo "The Apache configuration has changed in this release. Please add the following lines to your Apache configuration files (into the VirtualHost sections for port 80 and port 443):"
echo ""
echo "    # Allow other domains to query the data API (required for canvas/zoom image viewer)"
echo "    Header set Access-Control-Allow-Origin \"*\""

echo ""
echo "Done"
echo ""
