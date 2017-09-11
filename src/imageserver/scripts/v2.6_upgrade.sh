#!/bin/bash -e

if [[ "$QIS_HOME" == "" ]]; then
    echo "Please set QIS_HOME (e.g. export QIS_HOME=/opt/qis) and re-run this command"
    exit 1
fi

echo "Upgrading Javascript file names"

echo "Changing directory to $QIS_HOME/src/imageserver/static/js"
cd "$QIS_HOME/src/imageserver/static/js"

echo "Removing old Javascript files"
rm `find . -name '*.min.js'`

read -p "Do you need to maintain compatibility of Javascript files with earlier versions of QIS? [y/n]" RESP

if [[ "$RESP" == "y" ]]; then
    echo "Creating compatibility symlinks"
    ln -s canvas_view.min.js canvas_view.min.js
    ln -s excanvas.min.js excanvas.min.js
    ln -s gallery_view.min.js gallery_view.min.js
    ln -s simple_view.min.js simple_view.min.js
    ln -s slideshow_view.min.js slideshow_view.min.js
    ln -s lib/mootools.min.js mootools.min.js
    
    echo "The following symlinks can be deleted after your URLs and file references have been updated:"
    find . -name '*.min.js'
fi

echo ""
echo "Done"
echo ""
