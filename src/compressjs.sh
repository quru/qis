#!/bin/bash -e -v

# Who needs Webpack anyway...

BASE="$(pwd)"
YUI_JAR="$BASE/../lib/yuicompressor-2.4.6.jar"
COMPRESS="java -jar $YUI_JAR --preserve-semi --charset ISO-8859-1 --line-break 100"

# Viewers
cd imageserver/static/js
$COMPRESS -o common_view.min.js    common_view.js
$COMPRESS -o canvas_view.min.js    canvas_view.js
$COMPRESS -o gallery_view.min.js   gallery_view.js
$COMPRESS -o simple_view.min.js    simple_view.js
$COMPRESS -o slideshow_view.min.js slideshow_view.js
echo "" >> canvas_view.min.js    && cat common_view.min.js >> canvas_view.min.js
echo "" >> gallery_view.min.js   && cat common_view.min.js >> gallery_view.min.js
echo "" >> simple_view.min.js    && cat common_view.min.js >> simple_view.min.js
echo "" >> slideshow_view.min.js && cat common_view.min.js >> slideshow_view.min.js
cd "$BASE"

# UI
cd imageserver/static/js
$COMPRESS -o base.min.js          base.js
$COMPRESS -o account_edit.min.js  account_edit.js
$COMPRESS -o details.min.js       details.js
$COMPRESS -o details_edit.min.js  details_edit.js
$COMPRESS -o list.min.js          list.js
$COMPRESS -o preview_popup.min.js preview_popup.js
$COMPRESS -o publish.min.js       publish.js
$COMPRESS -o upload.min.js        upload.js
$COMPRESS -o lib/lassocrop.min.js lib/lassocrop.js
$COMPRESS -o lib/picker.min.js    lib/picker.js
cd "$BASE"

# Admin
cd imageserver/admin/static/js
$COMPRESS -o admin.min.js admin.js
cd "$BASE"

# Reports
cd imageserver/reports/static/js
$COMPRESS -o chart.min.js        chart.js
$COMPRESS -o system_stats.min.js system_stats.js
$COMPRESS -o lib/mooflot.min.js  lib/mooflot.js
cd "$BASE"
