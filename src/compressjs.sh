#!/bin/bash -v

# TODO combine helpers with image viewers before minimising
# TODO move to .min.js (breaking change)
#
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/admin/static/js/admin_yc.js imageserver/admin/static/js/admin.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/reports/static/js/chart_yc.js imageserver/reports/static/js/chart.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/reports/static/js/lib/mooflot_yc.js imageserver/reports/static/js/lib/mooflot.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/reports/static/js/system_stats_yc.js imageserver/reports/static/js/system_stats.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/account_edit_yc.js imageserver/static/js/account_edit.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/base_yc.js imageserver/static/js/base.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/canvas_view_yc.js imageserver/static/js/canvas_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/details_yc.js imageserver/static/js/details.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/details_edit_yc.js imageserver/static/js/details_edit.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/excanvas_yc.js imageserver/static/js/excanvas.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/gallery_view_yc.js imageserver/static/js/gallery_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/lib/lassocrop_yc.js imageserver/static/js/lib/lassocrop.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/lib/picker_yc.js imageserver/static/js/lib/picker.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/list_yc.js imageserver/static/js/list.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/preview_popup_yc.js imageserver/static/js/preview_popup.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/publish_yc.js imageserver/static/js/publish.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/simple_view_yc.js imageserver/static/js/simple_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/slideshow_view_yc.js imageserver/static/js/slideshow_view.js
java -jar ../lib/yuicompressor-2.4.6.jar --preserve-semi --charset ISO-8859-1 --line-break 100 -o imageserver/static/js/upload_yc.js imageserver/static/js/upload.js
